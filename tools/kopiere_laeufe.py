#!/usr/bin/env python3
"""FR-47: Die Laeufe, auf denen ein Release ruht, in einen zweiten Eimer kopieren.

    python tools/kopiere_laeufe.py --release 2026-11-14T09-09-47Z
    python tools/kopiere_laeufe.py --release aktuell \\
        --von ~/.config/urbancrime-probe/quelle.env \\
        --nach ~/.config/urbancrime-probe/hmac.env --trocken

**Zweck.** Der Beleg fuer FR-47 baut in Google Cloud nur ab (``run_all
--ohne-ingestion``) und vergleicht das Release dann mit dem von ``srv01``
(``tools/vergleiche_releases.py``). Gleich sein koennen die beiden nur, wenn
die Probe **genau** auf den Bronze-Laeufen baut, auf denen das srv01-Release
ruht (Plan, Decisions). Alle Laeufe zu kopieren hiesse, einen anderen Bestand
zu bauen (AGENTS.md: "Den Bestand aus Bronze zu lesen heisst, alle Laeufe zu
lesen").

**Welche Laeufe.** Gelesen wird ``releases/release=<id>/release.json`` und
jedes ``manifest.json`` im Release (Gold, Serving, die Karte). In deren
Herkunft (``derived_from``, beliebig tief) stehen die Laeufe auf zwei Arten:
Listen unter ``<stadt>_bronze_runs`` (oder ``_raw_runs``) und Eintraege mit
``run_id`` und ``layer``. Ein Lauf ohne ``layer`` gilt als Bronze. Raw wird
nur kopiert, wenn die Herkunft es nennt.

**Was das Release nicht nennt, der Lauf aber braucht.** Gold nennt nur die
Bronze-Laeufe, auf denen es ruht - ``tiger_place`` etwa nur Vintage 2024
(``RATENJAHR``). ``run_all --ohne-ingestion`` baut Silver aber fuer jeden
Vintage und brach in der ersten Probe (15.11.2026) bei ``silver · place_2021``
ab, weil die Laeufe fuer 2021-2023 fehlten. Deshalb kommt fuer jede Partition
einer Referenzquelle (``bronze/dataset=.../<partition>/run_<id>``), zu der das
Release **keinen** Lauf nennt, der juengste fertige Lauf mit - genau einer.
Die Stadtdaten (``bronze/city=...``) sind nach Ladedatum oder Jahr
partitioniert und jede Partition ist ein eigener Lauf; dort ergaenzte die
Regel alte Laeufe, die Silver nie liest, und gilt deshalb nicht.

**Wo sie liegen.** Die Ablage hat je Quelle ein anderes Muster
(``bronze/city=chicago/ingest_date=.../run_<id>/``,
``bronze/city=detroit/full/year=.../run_<id>/``,
``bronze/dataset=tiger_tract/vintage=.../state=.../run_<id>/``). Das Werkzeug
raet es nicht nach, sondern listet ``bronze/`` (und ``raw/``) im Quelleimer
und nimmt jedes Verzeichnis, dessen Name ``run_<id>`` ist.

**Wie kopiert wird.** Je Lauf alle Objekte, ``manifest.json`` zuletzt - wie
``Storage.publish_files``: Ein Manifest oben ist das Zeichen, dass der Lauf
vollstaendig ist. Ein Objekt, das im Ziel schon mit denselben Bytes liegt,
wird uebersprungen; liegt es dort **anders**, bricht das Werkzeug ab - Laeufe
sind unveraenderlich, und ueberschrieben wird nie. Geloescht wird nichts.
Quelle und Ziel im selben Eimer lehnt es ab.

**Die Schluessel** stehen in zwei ``.env``-Dateien unter
``~/.config/urbancrime-probe/`` (Modus 600, nie im Repository-Verzeichnis;
Entscheid vom 15.11.2026). Die Umgebung des Aufrufs gilt nicht.

Exit 0, wenn jeder genannte Lauf vollstaendig im Ziel liegt; 1, wenn ein Lauf
in der Quelle fehlt, ein Objekt im Ziel abweicht oder die Konfiguration
nicht reicht.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

WERKZEUGE = Path(__file__).resolve().parent
sys.path.insert(0, str(WERKZEUGE))

from vergleiche_releases import (  # noqa: E402
    ZUSTAND, VergleichsFehler, ablage, json_oben, lies_env, lies_release, ort)
from manifeste import MANIFEST  # noqa: E402
from storage import Storage, StorageError  # noqa: E402
from storage import release as releases  # noqa: E402

VORGABE_VON = ZUSTAND / "quelle.env"
VORGABE_NACH = ZUSTAND / "hmac.env"
#: Die Schichten, aus denen Laeufe kopiert werden duerfen.
SCHICHTEN = ("bronze", "raw")
LAUFLISTE = re.compile(r"^\w+_(bronze|raw)_runs$")


class KopierFehler(RuntimeError):
    """Die Kopie laesst sich nicht (vollstaendig) fuehren - mit Grund."""


# ---------------------------------------------------------------------------
# Welche Laeufe nennt das Release?
# ---------------------------------------------------------------------------


def laufname(kennung: str) -> str:
    """``run_<id>``, wie das Verzeichnis heisst - Detroit nennt nur die UUID."""
    return kennung if kennung.startswith("run_") else f"run_{kennung}"


def laeufe_in(herkunft: Any) -> set[tuple[str, str]]:
    """(Schicht, ``run_<id>``) fuer jeden Lauf, den eine Herkunft nennt."""
    gefunden: set[tuple[str, str]] = set()
    if isinstance(herkunft, dict):
        if herkunft.get("run_id") and herkunft.get("layer", "bronze") in SCHICHTEN:
            gefunden.add((herkunft.get("layer", "bronze"), laufname(str(herkunft["run_id"]))))
        for schluessel, wert in herkunft.items():
            treffer = LAUFLISTE.match(str(schluessel))
            if treffer and isinstance(wert, list):
                gefunden |= {(treffer.group(1), laufname(str(k))) for k in wert if k}
            else:
                gefunden |= laeufe_in(wert)
    elif isinstance(herkunft, list):
        for wert in herkunft:
            gefunden |= laeufe_in(wert)
    return gefunden


def laeufe_des_release(storage: Storage, manifest: dict[str, Any]) -> set[tuple[str, str]]:
    """Aus ``release.json`` und jedem Manifest im Release."""
    gefunden = laeufe_in(manifest.get("derived_from"))
    rel = releases.relativ(manifest["release_id"])
    for pfad in sorted(manifest.get("files") or {}):
        if pfad.endswith(MANIFEST):
            gefunden |= laeufe_in(json_oben(storage, f"{rel}/{pfad}").get("derived_from"))
    if not gefunden:
        raise KopierFehler(f"Release {manifest['release_id']} nennt keinen Lauf")
    return gefunden


# ---------------------------------------------------------------------------
# Wo liegen sie, und wie kommen sie hinueber?
# ---------------------------------------------------------------------------


def verzeichnisse(storage: Storage, laeufe: set[tuple[str, str]]) -> dict[str, list[str]]:
    """Je Laufverzeichnis (``bronze/.../run_<id>``) seine Objekte in der Quelle."""
    gefunden: dict[str, list[str]] = {}
    for schicht in sorted({s for s, _ in laeufe}):
        namen = {n for s, n in laeufe if s == schicht}
        for objekt in storage.client.list(schicht + "/"):
            teile = objekt.key.split("/")
            for i, teil in enumerate(teile[:-1]):
                if teil in namen:
                    gefunden.setdefault("/".join(teile[:i + 1]), []).append(objekt.key)
                    break
    return gefunden


#: Die Schichtpraefixe, deren Partitionen ergaenzt werden (Docstring oben).
REFERENZQUELLEN = "bronze/dataset="


def ergaenzungen(storage: Storage, gefunden: dict[str, list[str]]) -> dict[str, list[str]]:
    """Je Referenz-Partition ohne genannten Lauf der juengste fertige Lauf.

    Die Laufkennungen beginnen mit dem UTC-Zeitstempel
    (``run_20261004T165012171437Z``); der groesste Name ist der juengste.
    """
    gedeckt = {v.rsplit("/", 1)[0] for v in gefunden}
    je_partition: dict[str, dict[str, list[str]]] = {}
    for objekt in storage.client.list(REFERENZQUELLEN):
        teile = objekt.key.split("/")
        for i, teil in enumerate(teile[:-1]):
            if teil.startswith("run_"):
                partition = "/".join(teile[:i])
                if partition not in gedeckt:
                    (je_partition.setdefault(partition, {})
                     .setdefault("/".join(teile[:i + 1]), []).append(objekt.key))
                break
    ergaenzt: dict[str, list[str]] = {}
    for laeufe in je_partition.values():
        fertig = [v for v, schluessel in laeufe.items()
                  if any(k.rsplit("/", 1)[-1] == MANIFEST for k in schluessel)]
        if fertig:
            juengster = max(fertig)
            ergaenzt[juengster] = laeufe[juengster]
    return ergaenzt


def reihenfolge(schluessel: list[str]) -> list[str]:
    """Alles vor ``manifest.json`` - ein Manifest oben heisst: Lauf vollstaendig."""
    return sorted(schluessel, key=lambda k: (k.rsplit("/", 1)[-1] == MANIFEST, k))


def sha(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def kopiere_lauf(von: Storage, nach: Storage, schluessel: list[str], *,
                 trocken: bool = False) -> tuple[int, int]:
    """(kopiert, uebersprungen). Weicht ein Objekt im Ziel ab: KopierFehler."""
    kopiert = gleich = 0
    for key in reihenfolge(schluessel):
        daten = von.client.get(key)
        if nach.client.head(key) is not None:
            if sha(nach.client.get(key)) != sha(daten):
                raise KopierFehler(
                    f"{ort(nach)}/{key} liegt schon - mit anderen Bytes. Laeufe sind "
                    "unveraenderlich; nichts ueberschrieben")
            gleich += 1
            continue
        if not trocken:
            nach.client.put(key, daten)
        kopiert += 1
    return kopiert, gleich


def ausfuehren(von: Storage, nach: Storage, *, release: str = "aktuell",
               trocken: bool = False, aus: Callable[[str], None] = print) -> int:
    if ort(von) == ort(nach):
        raise KopierFehler(f"Quelle und Ziel sind derselbe Eimer ({ort(von)})")
    manifest = lies_release(von, release)
    laeufe = laeufe_des_release(von, manifest)
    gefunden = verzeichnisse(von, laeufe)
    ergaenzt = ergaenzungen(von, gefunden)
    aus(f"Release {manifest['release_id']} aus {ort(von)}: {len(laeufe)} Laeufe genannt, "
        f"{len(gefunden)} Laufverzeichnisse gefunden, {len(ergaenzt)} ergaenzt "
        f"-> {ort(nach)}" + ("  [trocken]" if trocken else ""))

    namen_gefunden = {v.rsplit("/", 1)[-1] for v in gefunden}
    gefunden = {**gefunden, **ergaenzt}
    fehlend = sorted(f"{s}/{n}" for s, n in laeufe if n not in namen_gefunden)
    summe_kopiert = summe_gleich = 0
    for verzeichnis, schluessel in sorted(gefunden.items()):
        if not any(k.rsplit("/", 1)[-1] == MANIFEST for k in schluessel):
            fehlend.append(f"{verzeichnis} (ohne {MANIFEST} - kein fertiger Lauf)")
            continue
        kopiert, gleich = kopiere_lauf(von, nach, schluessel, trocken=trocken)
        summe_kopiert += kopiert
        summe_gleich += gleich
        aus(f"  {verzeichnis}: {kopiert} kopiert, {gleich} schon gleich"
            + ("  (ergaenzt, im Release nicht genannt)" if verzeichnis in ergaenzt else ""))
    aus(f"{summe_kopiert} Objekte {'zu kopieren' if trocken else 'kopiert'}, "
        f"{summe_gleich} schon gleich.")
    if fehlend:
        aus("In der Quelle nicht (vollstaendig) gefunden:")
        for eintrag in sorted(fehlend):
            aus(f"  {eintrag}")
        return 1
    return 0


def main(argv: list[str] | None = None, *, von: Storage | None = None,
         nach: Storage | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", required=True,
                        help="Release-Kennung in der Quelle oder 'aktuell'")
    parser.add_argument("--von", type=Path, default=VORGABE_VON,
                        help=f".env des Quelleimers, nur gelesen (Vorgabe: {VORGABE_VON})")
    parser.add_argument("--nach", type=Path, default=VORGABE_NACH,
                        help=f".env des Zieleimers (Vorgabe: {VORGABE_NACH})")
    parser.add_argument("--trocken", action="store_true",
                        help="nur zeigen, was kopiert wuerde")
    args = parser.parse_args(argv)
    try:
        if von is None:
            von = ablage(lies_env(args.von), "von")
        if nach is None:
            nach = ablage(lies_env(args.nach), "nach")
        return ausfuehren(von, nach, release=args.release, trocken=args.trocken)
    except (KopierFehler, VergleichsFehler, StorageError) as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
