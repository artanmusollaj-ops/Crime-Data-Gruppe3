"""Faehrt die ganze Strecke in der richtigen Reihenfolge.

    python -m orchestration.run_all                  # alles, inklusive Ingestion
    python -m orchestration.run_all --ohne-ingestion # nur neu ableiten
    python -m orchestration.run_all --bis silver     # bis zu einer Stufe
    python -m orchestration.run_all --trocken        # nur zeigen, was liefe

Am Ende steht ``data/pipeline_run.json``: welche Stufen liefen, wie lange, auf
**welchen Bronze-Laeufen** das Ergebnis ruht, und ein Fingerabdruck darueber.
Zwei Laeufe auf denselben Eingaben tragen denselben Fingerabdruck - damit
laesst sich eine Zahl einem Stand zuordnen, statt ihn zu vermuten.

Warum die Stufen als Unterprozesse laufen: Ihre Kommandozeile **ist** die
Schnittstelle, und sie ist getestet. Sie zu importieren und die ``main`` zu
rufen waere ein zweiter Weg in denselben Code - und der zweite Weg ist der, der
irgendwann anders funktioniert als der erste.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from orchestration import FERTIG, LAUF_MANIFEST


LOG = logging.getLogger("run_all")


class Stufe(NamedTuple):
    """Ein Aufruf, der genau eine Sache tut."""

    gruppe: str          # ingestion | silver | gold | serving
    name: str
    modul: str
    argumente: tuple[str, ...] = ()

    @property
    def befehl(self) -> list[str]:
        return [sys.executable, "-m", self.modul, *self.argumente]


# Die Reihenfolge ist die Aussage dieses Moduls. Alles andere ist Buchhaltung.
#
# Zwei Stellen darin sind nicht offensichtlich und haben schon Zeit gekostet:
#   * TIGER braucht **zwei** Aufrufe. Ohne ``place`` bekommt dim_tract keine
#     Stadtzuordnung - und der Bau scheitert dabei nicht.
#   * ``build_crime_offense`` liest ``silver/tract``, muss also nach ihm laufen.
STUFEN: tuple[Stufe, ...] = (
    Stufe("ingestion", "chicago", "chicago_pipeline.download_chicago"),
    Stufe("ingestion", "detroit", "detroit_pipeline.extract_detroit",
          ("--mode", "full", "--years", "2024")),
    Stufe("ingestion", "tiger_tract", "census_pipeline.download_tiger",
          ("--auslieferung", "tract")),
    Stufe("ingestion", "tiger_place", "census_pipeline.download_tiger",
          ("--auslieferung", "place")),
    Stufe("ingestion", "acs", "census_pipeline.download_acs"),
    Stufe("ingestion", "noaa", "weather_pipeline.download_noaa"),

    Stufe("silver", "tract", "silver_pipeline.build_tract"),
    Stufe("silver", "place", "silver_pipeline.build_place"),
    Stufe("silver", "weather_day", "silver_pipeline.build_weather_day"),
    Stufe("silver", "crime_offense", "silver_pipeline.build_crime_offense"),

    Stufe("gold", "gold", "gold_pipeline.build_gold"),

    Stufe("serving", "analyse_db", "serving.build_analysis_db"),
    Stufe("serving", "tracts_geojson", "serving.export_geojson"),
)

GRUPPEN = ("ingestion", "silver", "gold", "serving")


# ---------------------------------------------------------------------------
# Herkunft
# ---------------------------------------------------------------------------


def bronze_laeufe(data_root: Path) -> dict[str, list[str]]:
    """Jeder fertige Bronze-Lauf, nach Quelle geordnet.

    Das ist die Antwort auf *"auf welchem Stand beruht diese Zahl?"*. Gelesen
    werden die Manifeste selbst und nicht die Verzeichnisnamen: Ein Lauf, der
    unterwegs abgebrochen ist, liegt zwar da, gilt aber nicht.
    """
    gefunden: dict[str, list[str]] = {}
    wurzel = data_root / "bronze"
    if not wurzel.exists():
        return gefunden
    for pfad in sorted(wurzel.glob("**/manifest.json")):
        if any(teil.startswith(".") for teil in pfad.parts):
            continue
        try:
            m = json.loads(pfad.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOG.warning("Manifest nicht lesbar: %s", pfad)
            continue
        if str(m.get("status", "")).lower() not in FERTIG:
            continue
        # Der erste Pfadteil unter bronze/ benennt die Quelle:
        # city=chicago, dataset=tiger_tract, dataset=noaa_ghcnd ...
        quelle = pfad.relative_to(wurzel).parts[0]
        lauf = str(
            m.get("run_id") or m.get("pipeline_run_id") or pfad.parent.name
        )
        gefunden.setdefault(quelle, []).append(lauf)
    return {k: sorted(set(v)) for k, v in sorted(gefunden.items())}


def fingerabdruck(laeufe: dict[str, list[str]]) -> str:
    """Ein Hash ueber die Eingaben - zwei Laeufe darauf sind derselbe Stand."""
    roh = json.dumps(laeufe, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


def aktualitaet(data_root: Path) -> dict[str, str]:
    """Wann jede Quelle zuletzt geladen wurde.

    Keine Alarmierung - nur die Zahl, ohne die man sie nicht bauen kann. Wer
    sehen will, ob eine Quelle veraltet, sieht hier nach.
    """
    juengste: dict[str, str] = {}
    wurzel = data_root / "bronze"
    if not wurzel.exists():
        return juengste
    for pfad in sorted(wurzel.glob("**/manifest.json")):
        if any(teil.startswith(".") for teil in pfad.parts):
            continue
        try:
            m = json.loads(pfad.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if str(m.get("status", "")).lower() not in FERTIG:
            continue
        quelle = pfad.relative_to(wurzel).parts[0]
        # Acht Module schreiben completed_at_utc, Detroit finished_at. Wie
        # beim Status: beide nehmen ist billiger, als jedes geschriebene
        # Manifest ungueltig zu machen.
        wann = str(m.get("completed_at_utc") or m.get("finished_at")
                   or m.get("built_at_utc") or "")
        if wann and wann > juengste.get(quelle, ""):
            juengste[quelle] = wann
    return dict(sorted(juengste.items()))


def zeilenzahlen(data_root: Path) -> dict[str, int]:
    """Was am Ende dasteht - je Tabelle eine Zahl aus ihrem Manifest."""
    ergebnis: dict[str, int] = {}
    for schicht in ("silver", "gold"):
        for pfad in sorted((data_root / schicht).glob("dataset=*/**/manifest.json")):
            if any(teil.startswith(".") for teil in pfad.parts):
                continue
            m = json.loads(pfad.read_text(encoding="utf-8"))
            name = next(t for t in pfad.parts if t.startswith("dataset=")
                        ).removeprefix("dataset=")
            zahl = m.get("row_count") or m.get("rows")
            if zahl is not None:
                ergebnis[f"{schicht}/{name}"] = int(zahl)
    return dict(sorted(ergebnis.items()))


# ---------------------------------------------------------------------------
# Der Lauf
# ---------------------------------------------------------------------------


def auswahl(ohne_ingestion: bool, bis: str | None) -> list[Stufe]:
    stufen = [s for s in STUFEN
              if not (ohne_ingestion and s.gruppe == "ingestion")]
    if bis:
        grenze = GRUPPEN.index(bis)
        stufen = [s for s in stufen if GRUPPEN.index(s.gruppe) <= grenze]
    return stufen


def fahre(stufen: list[Stufe], projekt_root: Path) -> list[dict]:
    """Eine Stufe nach der anderen. Beim ersten Fehler ist Schluss.

    Weiterzulaufen waere schlimmer als abzubrechen: Die naechste Stufe baute
    auf einem halben Stand und meldete Erfolg.
    """
    protokoll: list[dict] = []
    for i, stufe in enumerate(stufen, 1):
        LOG.info("[%d/%d] %s · %s", i, len(stufen), stufe.gruppe, stufe.name)
        start = time.perf_counter()
        fertig = subprocess.run(stufe.befehl, cwd=projekt_root)
        dauer = round(time.perf_counter() - start, 1)
        protokoll.append({
            "gruppe": stufe.gruppe,
            "name": stufe.name,
            "befehl": " ".join(stufe.befehl[1:]),
            "sekunden": dauer,
            "exit": fertig.returncode,
        })
        if fertig.returncode != 0:
            LOG.error(
                "%s · %s ist mit %d gescheitert. Abgebrochen - jede weitere "
                "Stufe baute sonst auf einem halben Stand.",
                stufe.gruppe, stufe.name, fertig.returncode,
            )
            break
        LOG.info("      fertig in %.1f s", dauer)
    return protokoll


def schreibe_manifest(data_root: Path, manifest: dict) -> Path:
    ziel = data_root / LAUF_MANIFEST
    ziel.parent.mkdir(parents=True, exist_ok=True)
    arbeit = ziel.with_name(f".{ziel.name}.part")
    arbeit.write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    arbeit.replace(ziel)
    return ziel


def lauf(data_root: Path, projekt_root: Path, *,
         ohne_ingestion: bool = False, bis: str | None = None) -> dict:
    stufen = auswahl(ohne_ingestion, bis)
    begonnen = datetime.now(timezone.utc)
    protokoll = fahre(stufen, projekt_root)
    geschafft = all(s["exit"] == 0 for s in protokoll) and len(protokoll) == len(stufen)

    laeufe = bronze_laeufe(data_root)
    manifest = {
        "status": "complete" if geschafft else "failed",
        "started_at_utc": begonnen.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "stages": protokoll,
        "input_bronze_runs": laeufe,
        "input_fingerprint": fingerabdruck(laeufe),
        "source_freshness": aktualitaet(data_root),
        "output_rows": zeilenzahlen(data_root) if geschafft else {},
    }
    schreibe_manifest(data_root, manifest)
    return manifest


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Faehrt Ingestion, Silver, Gold und Serving in der "
                    "richtigen Reihenfolge."
    )
    p.add_argument("--data-root", type=Path, default=Path("data"))
    p.add_argument("--ohne-ingestion", action="store_true",
                   help="nur neu ableiten, ohne die Quellen anzufassen")
    p.add_argument("--bis", choices=GRUPPEN,
                   help="nach dieser Gruppe aufhoeren")
    p.add_argument("--trocken", action="store_true",
                   help="nur zeigen, was liefe")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    projekt_root = Path(__file__).resolve().parents[3]

    stufen = auswahl(args.ohne_ingestion, args.bis)
    if args.trocken:
        print(f"{len(stufen)} Stufen, in dieser Reihenfolge:\n")
        for i, s in enumerate(stufen, 1):
            print(f"  {i:>2}. {s.gruppe:<10} {s.name:<16} "
                  f"python -m {s.modul} {' '.join(s.argumente)}".rstrip())
        return 0

    manifest = lauf(args.data_root, projekt_root,
                    ohne_ingestion=args.ohne_ingestion, bis=args.bis)

    print()
    if manifest["status"] != "complete":
        gescheitert = next(s for s in manifest["stages"] if s["exit"] != 0)
        print(f"Abgebrochen bei {gescheitert['gruppe']} · {gescheitert['name']}.")
        return 1
    gesamt = sum(s["sekunden"] for s in manifest["stages"])
    print(f"{len(manifest['stages'])} Stufen in {gesamt:.0f} s.")
    print(f"Fingerabdruck der Eingaben: {manifest['input_fingerprint'][:16]}")
    print(f"Protokoll: {args.data_root / LAUF_MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
