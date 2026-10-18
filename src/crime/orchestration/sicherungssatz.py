"""Was von diesem Vorhaben gesichert werden *muss* - und nur das.

**Der Anlass, am 18.10.2026.** Die naechtliche Sicherung von `srv01` nach
Backblaze lief voll; der letzte erfolgreiche Lauf war der 24.9.2026. Gemessen
wurde dann, was sie ueberhaupt traegt: 7,3 GB je Nacht, davon 7,1 GB unsere -
der SeaweedFS-Datentraeger mit 6,3 GB und ein Elasticsearch-Index mit 810 MB.

Das Missverhaeltnis ist nicht die Zahl, sondern die **Art** der Daten. Ein
aktueller Stand kostet im Restic-Repository 1,743 GiB, und jeder Wochenlauf
schreibt neue Parquet-Dateien unter neuen Lauf-IDs: restic kann nichts
entdoppeln. Bei einer Aufbewahrung von sieben Tagen, vier Wochen und zwoelf
Monaten wuchert das. Wir haben woechentlich wechselnde **Rechenergebnisse**
in ein Archiv gelegt, das fuer Dinge gedacht ist, die man nicht nachrechnen
kann.

**Was wirklich nicht nachrechenbar ist**, gemessen am 18.10.2026:

* die **21 gepinnten Laeufe** - 127,8 MiB. Der eingefrorene Stand, auf den
  die LN1-Zahlen zeigen (``config/referenzstand.csv``). Geht er verloren,
  sind die Zahlen der Abgabe nicht mehr reproduzierbar, und *das* laesst sich
  durch kein Neuladen heilen: Die Portale liefern heute andere Daten als im
  September.
* die **zwei gepinnten Releases** - 80,7 MiB. Dieselbe Spalte des Registers
  traegt auch Release-Kennungen; sie sind keine Laeufe und waeren mir beim
  ersten Entwurf durchgefallen.
* das **aktuelle Release** - 173,6 MiB. Baubar, aber es ist der Beleg, auf
  den die Dokumente zeigen (``releases/AKTUELL.json``).

Zusammen **382,2 MiB in 114 Objekten**, am 18.10.2026 auf `srv01` gemessen -
und nichts davon fehlt oben.

Alles andere - raw, bronze, silver, gold, serving, aeltere Releases - ist
Rechenergebnis. Silver und Gold entstehen in 117 Sekunden neu.

**Was dieses Modul tut.** Es holt genau diesen Satz in ein **eigenes**
Verzeichnis (``--ziel``, vorgabemaessig ``sicherung``) und entfernt dort
alles, was nicht dazugehoert. Danach gilt: *Was in diesem Verzeichnis liegt,
ist der Sicherungssatz* - eine Zusage, die sich pruefen laesst.

**Warum nicht nach ``data``.** Zwei Gruende, und der zweite ist der
zwingende. Erstens ist ``data`` das Arbeitsverzeichnis der Strecke: Dort
entstehen Laeufe, dort raeumt ``arbeitskopien_entfernen`` auf, und ein Modul,
das dort loescht, was es nicht kennt, kaempft mit dem Lauf. Zweitens - am
18.10.2026 nachgesehen - ist ``/app/data`` im Container das benannte Volume
``urbancrime_arbeitsdaten``, und das steht **nicht** in ``backup.volumes``.
Der Satz waere dort gelandet und nie gesichert worden. Das eigene Volume
``urbancrime_sicherung`` traegt er stattdessen, und es steht in der Policy.

**Warum das restic nicht wachsen laesst.** ``Storage.hole`` schreibt nichts,
was identisch schon daliegt, und Laeufe wie Releases sind unveraenderlich.
Der Satz aendert sich also nur, wenn wir etwas pinnen oder ein Release
veroeffentlichen - dann um dessen Groesse und sonst nie.

**Warum derselbe Register wie beim Aufraeumen.** ``config/referenzstand.csv``
entscheidet schon, welcher Lauf das Aufraeumen ueberlebt. Ein zweites
Register daneben waere die Stelle, an der beide auseinanderlaufen - und dann
wird ein Lauf aufgehoben, aber nicht gesichert, oder umgekehrt. Es gibt
**ein** Register.

Vorgabemaessig wird nur **gezeigt**, wie bei ``aufraeumen``; geholt wird mit
``--holen``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from manifeste import MANIFEST
from storage import Storage, for_root, paths, release

from .aufraeumen import REFERENZSTAND_DATEI, gepinnte_laeufe

LOG = logging.getLogger("sicherungssatz")

#: Wo Laeufe liegen. Silver und Gold sind Rechenergebnis und gehoeren nicht
#: dazu - sie entstehen aus Bronze neu.
LAUFSCHICHTEN = ("raw", "bronze")

#: Beschreibt den Satz - liegt mit ihm im Archiv, damit eine
#: Wiederherstellung sagen kann, *was* sie in der Hand hat.
SATZ_MANIFEST = "sicherungssatz.json"

#: Wohin, wenn nichts gesagt wird. Im Abbild ist das ``/app/sicherung``, das
#: eigene Volume; ``SICHERUNG_ROOT`` ueberschreibt es.
VORGABE_ZIEL = "sicherung"


class Eintrag(NamedTuple):
    rel: str
    kennung: str
    grund: str
    objekte: int
    bytes: int
    vollstaendig_lokal: bool


def passt(kennung: str, verzeichnisname: str) -> bool:
    """Ob ein Verzeichnis diese Kennung traegt - **vier Formen**.

    Am 18.10.2026 auf `srv01` gemessen, und alle vier kommen wirklich vor:

    * ``run_20260905T174633859259Z`` - Chicago: der Verzeichnisname **ist**
      die Kennung, und so steht sie auch im Register.
    * ``run_1cca323d-5f8f-…`` - Detroit: ``run_`` **plus** die blanke UUID,
      und das Register fuehrt die UUID **ohne** das Praefix. Das war der
      Fehler der ersten Fassung: Zehn gepinnte Eintraege galten als
      verschwunden, darunter alle acht Detroit-Laeufe des LN1-Stands.
    * ``release=2026-09-21T12-55-05Z`` - ein gepinntes **Release**. Zwei
      stehen so im Register; die erste Fassung suchte nur in Raw und Bronze
      und haette sie nicht gesichert.
    * ``run=<Kennung>`` - die vierte Form, die ``aufraeumen.entscheide_releases``
      ebenfalls vergleicht. Hier bisher nicht gesehen, aber derselbe Satz:
      lieber eine Form zu viel erkennen als eine zu wenig.
    """
    return verzeichnisname in (kennung, f"run_{kennung}", f"run={kennung}",
                               f"release={kennung}")


def verzeichnisse_oben(ablage: Storage,
                       schichten: tuple[str, ...] = LAUFSCHICHTEN
                       ) -> dict[str, str]:
    """Verzeichnisname -> relativer Pfad, fuer jeden Lauf und jedes Release.

    Erkannt wird an seinem Manifest, wie in ``Storage.fehlende_laeufe``: ein
    Lauf am ``manifest.json``, ein Release an ``release.json``.
    """
    gefunden: dict[str, str] = {}
    if not ablage.config.remote:
        return gefunden
    fuer = [(schicht, MANIFEST) for schicht in schichten]
    fuer.append((release.RELEASES, release.RELEASE_MANIFEST))
    for schicht, manifest in fuer:
        for objekt in ablage.client.list(schicht + "/"):
            if not objekt.key.endswith("/" + manifest):
                continue
            rel_dir = objekt.key[: -len("/" + manifest)]
            if paths.versteckt(rel_dir):
                continue
            gefunden[rel_dir.rsplit("/", 1)[-1]] = rel_dir
    return gefunden


def _groesse(ablage: Storage, rel_dir: str) -> tuple[int, int]:
    objekte = [o for o in ablage.client.list(rel_dir + "/")
               if not paths.versteckt(o.key[len(rel_dir) + 1:])]
    return (len(objekte), sum(o.size for o in objekte))


def _liegt_ganz_hier(ablage: Storage, rel_dir: str, objekte: int) -> bool:
    hier = ablage.local_path(rel_dir)
    # Lokal mit Absicht: Gefragt ist, ob der Satz **auf dieser Platte** liegt -
    # das ist der Gegenstand, nicht der Inhalt der Ablage. Die Sicherung liest
    # Dateien, keine Objekte.
    if not hier.is_dir():
        return False
    return sum(1 for p in hier.rglob("*") if p.is_file()
               and not paths.versteckt(p.name)) >= objekte


def satz(ablage: Storage,
         config_root: Path | None = None) -> tuple[list[Eintrag], list[str]]:
    """Der Satz und die gepinnten Kennungen, die oben **fehlen**.

    Eine fehlende Kennung ist kein Schoenheitsfehler: Sie heisst, dass ein
    Lauf gepinnt ist, den es nicht mehr gibt - dann zeigt das Register auf
    etwas, das keine Sicherung retten kann.
    """
    gepinnt = gepinnte_laeufe(config_root) if config_root else {}
    oben = verzeichnisse_oben(ablage)
    eintraege: list[Eintrag] = []
    fehlend: list[str] = []
    gesehen: set[str] = set()

    for kennung in sorted(gepinnt):
        treffer = [rel for name, rel in oben.items() if passt(kennung, name)]
        if not treffer:
            fehlend.append(kennung)
            continue
        for rel_dir in sorted(treffer):
            if rel_dir in gesehen:
                continue
            gesehen.add(rel_dir)
            objekte, bytes_ = _groesse(ablage, rel_dir)
            eintraege.append(Eintrag(
                rel_dir, kennung, f"gepinnt: {gepinnt[kennung]}", objekte,
                bytes_, _liegt_ganz_hier(ablage, rel_dir, objekte)))

    zeiger = release.aktuell(ablage) if ablage.config.remote else None
    if zeiger:
        kennung = str(zeiger.get("release_id") or "")
        rel_dir = release.relativ(kennung)
        objekte, bytes_ = _groesse(ablage, rel_dir)
        if rel_dir in gesehen:
            # Das aktuelle Release ist zugleich gepinnt - einmal genuegt.
            pass
        elif objekte:
            eintraege.append(Eintrag(
                rel_dir, kennung, "aktuelles Release", objekte, bytes_,
                _liegt_ganz_hier(ablage, rel_dir, objekte)))
        else:
            fehlend.append(f"{kennung} (Release, aber oben leer)")
    elif ablage.config.remote:
        fehlend.append(f"kein {release.AKTUELL} - der Zeiger fehlt")

    return eintraege, fehlend


def hole(ablage: Storage, eintraege: list[Eintrag]) -> list[str]:
    """Holt, was fehlt. Was identisch daliegt, wird nicht angefasst.

    Die zweite Haelfte der Zusage steht in ``entferne_fremdes``: Holen allein
    liesse das Verzeichnis wachsen, und jedes Release, das einmal aktuell war,
    blieb fuer immer in der Sicherung - 174 MB je Woche.
    """
    geholt: list[str] = []
    for e in eintraege:
        if e.vollstaendig_lokal:
            continue
        ablage.hole_lauf(e.rel)
        LOG.info("in den Sicherungssatz geholt: %s (%d Objekte, %.1f MB)",
                 e.rel, e.objekte, e.bytes / 1e6)
        geholt.append(e.rel)
    return geholt


def entferne_fremdes(ablage: Storage, eintraege: list[Eintrag]) -> list[str]:
    """Was im Zielverzeichnis liegt und nicht zum Satz gehoert, geht weg.

    **Ohne das waechst die Sicherung unbegrenzt.** Jede Woche wird ein neues
    Release aktuell; das vorige gehoert dann nicht mehr dazu, lag aber schon
    hier. Nach einem Jahr waeren das 9 GB - genau die Groesse, an der das
    Backblaze-Kontingent heute haengt.

    Entfernt wird **nur** innerhalb des Zielverzeichnisses, und nur ein
    ganzes Lauf- oder Releaseverzeichnis. Das ist derselbe Satz wie bei
    Releases im Aufraeumen: ein ganzes oder keines.
    """
    wurzel = ablage.local_root
    # Lokal mit Absicht: Gegenstand ist dieses Verzeichnis auf dieser Platte.
    # Es ist nicht die Ablage, sondern das, was die Serversicherung liest.
    if not wurzel.is_dir():
        return []
    behalten = {e.rel for e in eintraege}
    weg: list[str] = []
    # Ein Verzeichnis ist ein Lauf oder ein Release, wenn es Dateien traegt.
    # Von unten nach oben, damit leere Elternverzeichnisse danach mitgehen.
    for pfad in sorted((p for p in wurzel.rglob("*") if p.is_dir()),
                       key=lambda p: -len(p.parts)):
        rel = pfad.relative_to(wurzel).as_posix()
        # Drei Faelle bleiben: der Eintrag selbst, ein Elternverzeichnis
        # davon - und **der Inhalt**. Der dritte fehlte in der ersten
        # Fassung, und damit waere ``releases/release=X/gold`` geloescht
        # worden: das Release noch da, nur ausgeweidet. Ein Test hat es
        # gefangen, bevor es auf `srv01` lief.
        if any(rel == b or b.startswith(rel + "/") or rel.startswith(b + "/")
               for b in behalten):
            continue
        if any(p.is_file() for p in pfad.iterdir()) or not any(pfad.iterdir()):
            shutil.rmtree(pfad)
            LOG.info("nicht mehr im Sicherungssatz, entfernt: %s", rel)
            weg.append(rel)
    return weg


def schreibe_manifest(ablage: Storage, eintraege: list[Eintrag],
                      fehlend: list[str]) -> Path:
    """Beschreibt den Satz neben den Daten - fuer den Tag der Wiederherstellung.

    Wer ein Archiv auspackt, muss ohne dieses Repository erkennen koennen,
    *was* er in der Hand hat. Deshalb steht hier die Begruendung je Eintrag
    und nicht nur eine Liste von Pfaden.
    """
    ziel = ablage.local_path(SATZ_MANIFEST)
    inhalt = {
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grundsatz": ("Gesichert wird, was sich nicht nachrechnen laesst: die "
                      "gepinnten Laeufe und das aktuelle Release. Silver, Gold "
                      "und Serving entstehen daraus neu."),
        "register": REFERENZSTAND_DATEI,
        "objekte": sum(e.objekte for e in eintraege),
        "bytes": sum(e.bytes for e in eintraege),
        "eintraege": [{"pfad": e.rel, "kennung": e.kennung, "grund": e.grund,
                       "objekte": e.objekte, "bytes": e.bytes}
                      for e in eintraege],
        "fehlend": fehlend,
    }
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(inhalt, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return ziel


def zeige(eintraege: list[Eintrag], fehlend: list[str]) -> None:
    print("\nSicherungssatz - was sich nicht nachrechnen laesst")
    if not eintraege:
        print("  (leer)")
    for e in eintraege:
        zeichen = "hier" if e.vollstaendig_lokal else "FEHLT"
        print(f"  {e.kennung[:34]:<35} {e.objekte:>4} Obj "
              f"{e.bytes / 1e6:>8.1f} MB  {zeichen:5}  {e.grund}")
    print(f"\n{len(eintraege)} Eintraege, "
          f"{sum(e.bytes for e in eintraege) / 1e6:.1f} MB. "
          f"{sum(1 for e in eintraege if not e.vollstaendig_lokal)} davon "
          f"liegen noch nicht hier.")
    if fehlend:
        print("\nGepinnt, aber oben nicht da - das Register zeigt ins Leere:")
        for k in fehlend:
            print(f"  {k}")


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Den Sicherungssatz zeigen und holen: gepinnte Laeufe "
                    "und das aktuelle Release.")
    p.add_argument("--ziel", type=Path,
                   default=Path(os.environ.get("SICHERUNG_ROOT") or VORGABE_ZIEL),
                   help=f"wohin der Satz kommt (Vorgabe: SICHERUNG_ROOT oder "
                        f"{VORGABE_ZIEL}). Dieses Verzeichnis gehoert dem "
                        f"Satz allein - was nicht dazugehoert, wird entfernt")
    p.add_argument("--config-root", type=Path, default=Path("config"),
                   help="wo referenzstand.csv liegt (Vorgabe: config)")
    p.add_argument("--holen", action="store_true",
                   help="fehlende Eintraege wirklich holen und das Manifest "
                        "schreiben. Ohne das wird nur gezeigt")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = arguments()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    # **Eine Ablage mit dem Ziel als Wurzel.** Dann schreibt ``hole_lauf``
    # dorthin - samt Pruefsumme, ``.part``-Datei und dem Ueberspringen von
    # allem, was identisch schon daliegt. Nichts davon muss hier neu
    # geschrieben werden, und das Zielverzeichnis bleibt sauber getrennt von
    # ``data``.
    ablage = for_root(args.ziel)
    if not ablage.config.remote:
        print(f"STORAGE_BACKEND={ablage.backend} kennt kein S3 - der "
              f"Sicherungssatz wird von dort geholt. Nichts zu tun.")
        return 0

    eintraege, fehlend = satz(ablage, args.config_root)
    zeige(eintraege, fehlend)

    if not args.holen:
        offen = [e for e in eintraege if not e.vollstaendig_lokal]
        if offen:
            print("\nNichts geholt. Mit --holen kommen die fehlenden "
                  "Eintraege herunter, Fremdes geht weg, und das Manifest "
                  "wird geschrieben.")
        return 1 if fehlend else 0

    geholt = hole(ablage, eintraege)
    weg = entferne_fremdes(ablage, eintraege)
    manifest = schreibe_manifest(ablage, eintraege, fehlend)
    print(f"\n{len(geholt)} Eintrag/Eintraege geholt, {len(weg)} entfernt. "
          f"Satz beschrieben in {manifest}.")
    # Ein Register, das ins Leere zeigt, ist ein Fehler und kein Hinweis: Die
    # Sicherung waere dann vollstaendig *und* unbrauchbar.
    return 1 if fehlend else 0


if __name__ == "__main__":
    raise SystemExit(main())
