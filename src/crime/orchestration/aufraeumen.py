"""Was von Raw und Bronze bleiben muss - und was weg darf.

    python -m orchestration.aufraeumen              # zeigen, nichts loeschen
    python -m orchestration.aufraeumen --loeschen   # entbehrliche Laeufe loeschen
    python -m orchestration.aufraeumen --pinnen LN1 # den heutigen Stand festhalten

Raw und Bronze wachsen mit jedem Lauf, und bis hierher sagte nichts, wann
etwas weg darf. Die Regel, je Quelle (``city=chicago``, ``dataset=noaa_ghcnd``,
...), juengster Lauf zuerst:

0. **Gepinnt bleibt.** Ein Lauf, auf den sich eine veroeffentlichte Zahl
   bezieht - eine Abgabe, eine Folie, ein Referenzstand -, steht in
   ``config/referenzstand.csv`` und wird nie aufgeraeumt. Diese Regel kam am
   14.9.2026 dazu, weil die drei folgenden der Historisierung im Weg stehen:
   Regel 2 haelt nur, was das **aktuelle** Silver nennt - nach einem Neubau
   werden die Laeufe des vorigen Stands entbehrlich, und eine Zahl von
   letzter Woche waere nicht mehr nachzubauen.
1. **Der juengste Lauf und der davor** bleiben. Der zweite ist der vorherige
   Schnappschuss - die einzige Moeglichkeit, eine Quelle gegen sich selbst zu
   pruefen. Detroit aendert abgeschlossene Faelle nachtraeglich (Notebook 13,
   Schritt 3), und das sieht man nur mit zwei Staenden.
2. **Von Silver genannt** bleibt. Jedes Silver-Manifest nennt unter
   ``derived_from`` die Laeufe, auf denen es ruht. Sie zu loeschen hiesse, den
   Stand nicht mehr erklaeren zu koennen.
4. **Dessen Unterschied noch nicht gezogen ist, bleibt.** Ein
   Vollschnappschuss traegt mehr als seinen Inhalt: Gegen seinen Vorgaenger
   gehalten sagt er, *was die Quelle geaendert hat*. Das zieht
   ``silver_pipeline.build_source_change`` heraus; bis dahin ist der Lauf
   unersetzlich. Danach genuegt die schmale Aenderungstabelle - 31,9 MB
   Schnappschuesse fuer 102 geaenderte Zeilen war das Verhaeltnis, das
   ``docs/intern/datenhistorie.md`` ausgerechnet hat. Diese Regel kam am
   1.10.2026 dazu, zusammen mit der Tabelle. Sie steht **zuletzt**, weil sie
   die einzige ist, die von allein vergeht: Ein Lauf, den sie haelt, wird
   durch einen Befehl frei.
3. **Die Basis eines Delta-Laufs** bleibt. Beide Staedte laden seit dem ersten
   vollen Schnappschuss nur Aenderungen - Chicago als ``mode: delta``, Detroit
   seit dem 18.9.2026 als ``extraction_mode: DELTA``; ohne den Schnappschuss
   darunter sind die Deltas wertlos. Ein Delta, das bleibt, haelt alles bis zum
   naechsten vollen Lauf fest.
5. Alles andere ist **entbehrlich**. Gezeigt wird es immer; geloescht nur mit
   ``--loeschen``, und dann Raw und Bronze zusammen - ein Bronze ohne sein Raw
   waere ein Ergebnis ohne Beweisstueck, ein Raw ohne Bronze ein Beweis ohne
   Ergebnis.

Ein Lauf gilt als Einheit: Ein ACS-Lauf liegt in zwei Verzeichnissen
(``state=17`` und ``state=26``), ein NOAA-Lauf in zwei Stationen. Sie kommen
und gehen zusammen.

Was die Regel bewusst nicht tut: von allein laufen. ``data/`` ist nicht
versioniert, die Regel gilt je Rechner, und Loeschen ist ein Handgriff, den
man sieht. In GitHub Actions laeuft jeder Datenlauf auf einer frischen
Maschine und braucht sie nicht.
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

from manifeste import fertige_laeufe, tabellen
from storage import for_root


LOG = logging.getLogger("aufraeumen")

SCHNAPPSCHUESSE = 2   # der juengste Lauf und der davor
DELTA_MODI = frozenset({"delta", "incremental"})

REFERENZSTAND_DATEI = "referenzstand.csv"
SPALTEN = ("run_id", "quelle", "grund", "seit")

GEPINNT = "Referenzstand"
JUENGSTER = "juengster Lauf"
VORHERIGER = "vorheriger Schnappschuss"
GENANNT = "von Silver genannt"
BASIS = "Basis eines Delta-Laufs"
UNGEZOGEN = "Unterschied nicht gezogen"


class Bestand(NamedTuple):
    """Ein Bronze-Lauf mit seinem Raw-Gegenstueck, ueber alle Partitionen."""

    quelle: str
    run_id: str
    abgeschlossen: str
    delta: bool
    bronze: tuple[Path, ...]
    raw: tuple[Path, ...]
    zeilen: int

    @property
    def ohne_raw(self) -> bool:
        return not self.raw

    @property
    def bytes(self) -> int:
        return sum(
            f.stat().st_size
            for verzeichnis in self.bronze + self.raw
            for f in verzeichnis.rglob("*") if f.is_file()
        )


class Entscheid(NamedTuple):
    bestand: Bestand
    grund: str | None   # None heisst: entbehrlich

    @property
    def bleibt(self) -> bool:
        return self.grund is not None


def ist_delta(manifest: dict[str, Any]) -> bool:
    # Chicago: mode = full_snapshot | delta.
    # Detroit: extraction_mode = FULL | DELTA | INCREMENTAL.
    modus = str(manifest.get("mode") or manifest.get("extraction_mode") or "")
    return modus.lower() in DELTA_MODI


def bestaende(data_root: Path) -> dict[str, list[Bestand]]:
    """Alle fertigen Bronze-Laeufe, je Quelle, juengster zuerst.

    Die Quelle ist der erste Pfadteil unter ``bronze/`` - dieselbe Einteilung
    wie im Gesamtmanifest von ``run_all``. Das Raw-Gegenstueck ist das
    Verzeichnis mit demselben relativen Pfad unter ``raw/``; fehlt es, ist der
    Lauf ``ohne_raw``.
    """
    bronze = data_root / "bronze"
    raw = data_root / "raw"
    gruppen: dict[tuple[str, str], dict[str, Any]] = {}
    for lauf in fertige_laeufe(bronze, streng=False):
        relativ = lauf.verzeichnis.relative_to(bronze)
        eintrag = gruppen.setdefault((relativ.parts[0], lauf.run_id), {
            "abgeschlossen": "", "delta": ist_delta(lauf.manifest),
            "bronze": [], "raw": [], "zeilen": 0,
        })
        eintrag["abgeschlossen"] = max(eintrag["abgeschlossen"], lauf.abgeschlossen_um)
        eintrag["bronze"].append(lauf.verzeichnis)
        if (raw / relativ).is_dir():
            eintrag["raw"].append(raw / relativ)
        eintrag["zeilen"] += lauf.zeilen

    je_quelle: dict[str, list[Bestand]] = {}
    for (quelle, run_id), e in gruppen.items():
        je_quelle.setdefault(quelle, []).append(Bestand(
            quelle, run_id, e["abgeschlossen"], e["delta"],
            tuple(e["bronze"]), tuple(e["raw"]), e["zeilen"],
        ))
    for laeufe in je_quelle.values():
        laeufe.sort(key=lambda b: (b.abgeschlossen, b.run_id), reverse=True)
    return dict(sorted(je_quelle.items()))


def genannt_in_silver(data_root: Path) -> set[str]:
    """Jede Kennung, die ein Silver-Manifest unter ``derived_from`` nennt.

    Die Form ist je Tabelle anders - ``crime_offense`` fuehrt Listen je Stadt,
    die uebrigen eine Liste von Eintraegen mit ``run_id``. Gesammelt wird
    deshalb jede Zeichenkette darin; verglichen wird gegen Kennung und
    Verzeichnisnamen des Laufs, weil Chicago ``run_<Zeit>`` schreibt und
    Detroit die nackte UUID.
    """
    kennungen: set[str] = set()

    def sammle(wert: Any) -> None:
        if isinstance(wert, str):
            kennungen.add(wert)
        elif isinstance(wert, dict):
            for v in wert.values():
                sammle(v)
        elif isinstance(wert, list):
            for v in wert:
                sammle(v)

    for tabelle in tabellen(data_root, ("silver",)):
        sammle(tabelle.manifest.get("derived_from"))
    return kennungen


def kennungen_aus(data_root: Path, schichten: tuple[str, ...]) -> set[str]:
    """Jede Zeichenkette unter ``derived_from`` der genannten Schichten."""
    kennungen: set[str] = set()

    def sammle(wert: Any) -> None:
        if isinstance(wert, str):
            kennungen.add(wert)
        elif isinstance(wert, dict):
            for v in wert.values():
                sammle(v)
        elif isinstance(wert, list):
            for v in wert:
                sammle(v)

    for tabelle in tabellen(data_root, schichten):
        sammle(tabelle.manifest.get("derived_from"))
    return kennungen


def gepinnte_laeufe(config_root: Path) -> dict[str, str]:
    """Das Register: Lauf-Kennung -> Grund. Leer, wenn es die Datei nicht gibt.

    Die Datei ist **versioniert**, anders als ``data/``: Ein Referenzstand ist
    eine Verabredung des Teams, kein Zustand eines Rechners. Seit die Laeufe
    auf SeaweedFS liegen, gelten die Kennungen fuer beide.
    """
    pfad = config_root / REFERENZSTAND_DATEI
    if not pfad.exists():
        return {}
    with pfad.open(encoding="utf-8", newline="") as datei:
        return {
            zeile["run_id"]: zeile.get("grund", "")
            for zeile in csv.DictReader(datei)
            if zeile.get("run_id")
        }


def stand_der_auswertung(data_root: Path) -> set[str]:
    """Jede Lauf-Kennung, auf der das gebaute Gold ruht.

    Das ist der Ertrag der geschlossenen Herkunftskette (#77): Ein
    Gold-Manifest nennt seine Silver-Quelle samt deren eigener Herkunft, und
    darin stehen die Bronze-Laeufe. Der Referenzstand laesst sich damit
    **ableiten** statt von Hand pflegen - und er beschreibt genau das, worauf
    die veroeffentlichten Zahlen beruhen.
    """
    return kennungen_aus(data_root, ("gold",))


def entscheide(laeufe: list[Bestand], genannt: set[str],
               gepinnt: dict[str, str] | None = None,
               ungezogen: set[str] | None = None) -> list[Entscheid]:
    """Die Regel, angewandt auf eine Quelle. ``laeufe`` juengster zuerst."""
    gepinnt = gepinnt or {}
    ungezogen = ungezogen or set()

    def ist_gepinnt(b: Bestand) -> bool:
        return b.run_id in gepinnt or any(v.name in gepinnt for v in b.bronze)

    gruende: list[str | None] = []
    for i, b in enumerate(laeufe):
        if ist_gepinnt(b):
            gruende.append(GEPINNT)
        elif i == 0:
            gruende.append(JUENGSTER)
        elif i < SCHNAPPSCHUESSE:
            gruende.append(VORHERIGER)
        elif b.run_id in genannt or any(v.name in genannt for v in b.bronze):
            gruende.append(GENANNT)
        else:
            gruende.append(None)

    # Ein Delta, das bleibt, braucht alles Aeltere bis zum naechsten vollen
    # Lauf. Ein Delta, das geht, braucht nichts mehr.
    braucht_basis = False
    for i, b in enumerate(laeufe):
        if gruende[i] is None and braucht_basis:
            gruende[i] = BASIS
        if gruende[i] is not None:
            braucht_basis = b.delta

    # Zuletzt, und das ist Absicht: ``UNGEZOGEN`` ist der **schwaechste**
    # Grund. Er geht weg, sobald jemand build_source_change laufen laesst;
    # ``BASIS`` und die uebrigen sind strukturell. Stuende er weiter vorn,
    # verdeckte eine voruebergehende Bedingung die dauerhafte, und der
    # Bericht saehe nach "einmal ziehen, dann darf es weg" aus, wo in
    # Wahrheit ein Delta darueber haengt.
    for i, b in enumerate(laeufe):
        if gruende[i] is None and (
                b.run_id in ungezogen
                or any(v.name in ungezogen for v in b.bronze)):
            gruende[i] = UNGEZOGEN
    return [Entscheid(b, g) for b, g in zip(laeufe, gruende)]


def ungezogen_laut_tabelle(data_root: Path) -> set[str]:
    """Spaet importiert, damit ``aufraeumen`` ohne Silver-Code lauffaehig bleibt.

    Fehlt das Modul oder scheitert die Auskunft, gibt es **keine** Freigabe,
    sondern eine leere Menge: Diese Regel darf nur zusaetzlich halten, nie
    zusaetzlich loeschen.
    """
    try:
        from silver_pipeline.build_source_change import ungezogene_laeufe

        return ungezogene_laeufe(data_root)
    except Exception as fehler:          # noqa: BLE001 - Auskunft, kein Zwang
        LOG.warning("Aenderungstabelle nicht lesbar (%s) - Regel 2a greift "
                    "nicht. Die uebrigen Regeln gelten unveraendert.", fehler)
        return set()


def bericht(data_root: Path, config_root: Path | None = None) -> list[Entscheid]:
    genannt = genannt_in_silver(data_root)
    gepinnt = gepinnte_laeufe(config_root) if config_root else {}
    ungezogen = ungezogen_laut_tabelle(data_root)
    alle: list[Entscheid] = []
    for laeufe in bestaende(data_root).values():
        alle.extend(entscheide(laeufe, genannt, gepinnt, ungezogen))
    return alle


def pinne(data_root: Path, config_root: Path, grund: str, *,
          jetzt: date | None = None) -> list[str]:
    """Haelt den Stand fest, auf dem die gebauten Gold-Tabellen ruhen.

    Abgeleitet, nicht getippt: Welche Laeufe das sind, steht in den
    Manifesten. Wer eine Zahl in eine Abgabe uebernimmt, pinnt danach - und
    die Laeufe dahinter ueberleben jedes Aufraeumen.

    Bereits gepinnte Laeufe bleiben unveraendert; ihr erster Grund zaehlt.
    """
    vorhanden = gepinnte_laeufe(config_root)
    quelle_von = {
        b.run_id: b.quelle
        for laeufe in bestaende(data_root).values() for b in laeufe
    }
    quelle_von.update({
        v.name: b.quelle
        for laeufe in bestaende(data_root).values() for b in laeufe for v in b.bronze
    })
    neu = sorted(k for k in stand_der_auswertung(data_root)
                 if k in quelle_von and k not in vorhanden)
    if not neu:
        return []

    pfad = config_root / REFERENZSTAND_DATEI
    pfad.parent.mkdir(parents=True, exist_ok=True)
    frisch = not pfad.exists()
    tag = (jetzt or date.today()).isoformat()
    with pfad.open("a", encoding="utf-8", newline="") as datei:
        schreiber = csv.writer(datei, lineterminator="\n")
        if frisch:
            schreiber.writerow(SPALTEN)
        for kennung in neu:
            schreiber.writerow([kennung, quelle_von[kennung], grund, tag])
    return neu


def zeige(entscheide: list[Entscheid]) -> None:
    quelle = None
    for e in entscheide:
        b = e.bestand
        if b.quelle != quelle:
            quelle = b.quelle
            print(f"\n{quelle}")
        vermerk = e.grund or "ENTBEHRLICH"
        if b.ohne_raw:
            vermerk += " · ohne Raw"
        if b.delta:
            vermerk += " · Delta"
        print(f"  {b.run_id[:28]:<29} {b.abgeschlossen[:16]:<17} "
              f"{b.zeilen:>9,} Zeilen {b.bytes / 1e6:>7.1f} MB  {vermerk}")
    entbehrlich = [e for e in entscheide if not e.bleibt]
    print(f"\n{len(entscheide)} Laeufe, {len(entbehrlich)} entbehrlich, "
          f"{sum(e.bestand.bytes for e in entbehrlich) / 1e6:.1f} MB frei.")


def loesche(entscheide: list[Entscheid], data_root: Path) -> list[Path]:
    """Loescht, was entbehrlich ist - Raw und Bronze zusammen.

    Leer gewordene Partitionsverzeichnisse (``ingest_date=...``) gehen mit;
    die Schichtwurzeln ``raw/`` und ``bronze/`` bleiben.
    """
    geloescht: list[Path] = []
    for e in entscheide:
        if e.bleibt:
            continue
        for verzeichnis in e.bestand.bronze + e.bestand.raw:
            shutil.rmtree(verzeichnis)
            geloescht.append(verzeichnis)
            LOG.info("geloescht: %s", verzeichnis)
            schicht = data_root / verzeichnis.relative_to(data_root).parts[0]
            eltern = verzeichnis.parent
            while eltern != schicht and eltern.is_dir() and not any(eltern.iterdir()):
                eltern.rmdir()
                eltern = eltern.parent
    return geloescht


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Zeigt, welche Raw- und Bronze-Laeufe bleiben muessen und "
                    "welche entbehrlich sind. Loescht nur auf Wunsch."
    )
    p.add_argument("--data-root", type=Path, default=None,
                   help="lokale Wurzel (Vorgabe: LOCAL_DATA_ROOT oder data). Aufgeraeumt wird nur lokal")
    p.add_argument("--config-root", type=Path, default=Path("config"),
                   help="wo das Register referenzstand.csv liegt (Vorgabe: config)")
    p.add_argument("--loeschen", action="store_true",
                   help="entbehrliche Laeufe wirklich loeschen, Raw und Bronze zusammen")
    p.add_argument("--pinnen", metavar="GRUND",
                   help="den Stand, auf dem das gebaute Gold ruht, ins Register "
                        "aufnehmen - er ueberlebt danach jedes Aufraeumen")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    data_root = for_root(args.data_root).local_root
    if args.pinnen:
        neu = pinne(data_root, args.config_root, args.pinnen)
        ziel = args.config_root / REFERENZSTAND_DATEI
        if neu:
            print(f"{len(neu)} Lauf/Laeufe als '{args.pinnen}' festgehalten in {ziel}:")
            for kennung in neu:
                print(f"  {kennung}")
            print("\nDie Datei ist versioniert - bitte mit committen.")
        else:
            print(f"Nichts hinzugefuegt: Der Stand steht schon in {ziel}.")
        print()

    alle = bericht(data_root, args.config_root)
    zeige(alle)
    entbehrlich = [e for e in alle if not e.bleibt]
    if not entbehrlich:
        return 0
    if not args.loeschen:
        print("Nichts geloescht. Mit --loeschen gehen die entbehrlichen Laeufe weg.")
        return 0
    frei = sum(e.bestand.bytes for e in entbehrlich)
    geloescht = loesche(alle, data_root)
    print(f"{len(geloescht)} Verzeichnisse geloescht, {frei / 1e6:.1f} MB frei.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
