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
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterable
from typing import NamedTuple

from manifeste import fingerabdruck as manifeste_fingerabdruck
from orchestration import LAUF_MANIFEST
from storage import for_root


LOG = logging.getLogger("run_all")


class Stufe(NamedTuple):
    """Ein Aufruf, der genau eine Sache tut."""

    gruppe: str          # ingestion | silver | gold | serving
    name: str
    modul: str
    argumente: tuple[str, ...] = ()
    # Welchen Bronze-Bestand diese Stufe fuellt, so wie ``aktualitaet`` ihn
    # benennt. Nur Ingestion-Stufen haben einen. Damit ist die Liste der
    # *erwarteten* Quellen abgeleitet statt gepflegt - und eine Quelle, die
    # gar nicht da ist, faellt auf. Vorher wurde nur geprueft, was schon
    # existierte: Ein leerer Bestand galt als frisch.
    quelle: str = ""

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
    Stufe("ingestion", "chicago", "chicago_pipeline.download_chicago",
          quelle="city=chicago"),
    Stufe("ingestion", "detroit", "detroit_pipeline.extract_detroit",
          ("--mode", "full", "--years", "2024"), quelle="city=detroit"),
    Stufe("ingestion", "tiger_tract", "census_pipeline.download_tiger",
          ("--auslieferung", "tract"), quelle="dataset=tiger_tract"),
    Stufe("ingestion", "tiger_place", "census_pipeline.download_tiger",
          ("--auslieferung", "place"), quelle="dataset=tiger_place"),
    Stufe("ingestion", "acs", "census_pipeline.download_acs",
          quelle="dataset=acs5_tract"),
    Stufe("ingestion", "noaa", "weather_pipeline.download_noaa",
          quelle="dataset=noaa_ghcnd"),

    Stufe("silver", "tract", "silver_pipeline.build_tract"),
    Stufe("silver", "place", "silver_pipeline.build_place"),
    Stufe("silver", "weather_day", "silver_pipeline.build_weather_day"),
    Stufe("silver", "crime_offense", "silver_pipeline.build_crime_offense"),

    Stufe("gold", "gold", "gold_pipeline.build_gold"),

    Stufe("serving", "analyse_db", "serving.build_analysis_db"),
    Stufe("serving", "tracts_geojson", "serving.export_geojson"),
)

GRUPPEN = ("ingestion", "silver", "gold", "serving")

# Die Bestaende, die nach einer vollstaendigen Ingestion dasein muessen.
ERWARTETE_QUELLEN: tuple[str, ...] = tuple(
    sorted(s.quelle for s in STUFEN if s.quelle)
)


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
    for lauf in for_root(data_root).laeufe("bronze", "**/manifest.json"):
        # Der erste Pfadteil unter bronze/ benennt die Quelle:
        # city=chicago, dataset=tiger_tract, dataset=noaa_ghcnd ...
        quelle = lauf.relativ.split("/")[1]
        gefunden.setdefault(quelle, []).append(lauf.run_id)
    return {k: sorted(set(v)) for k, v in sorted(gefunden.items())}


# Derselbe Abdruck wie in den Tabellenmanifesten - er kommt aus manifeste,
# damit "derselbe Stand" ueberall dasselbe heisst.
fingerabdruck = manifeste_fingerabdruck


def aktualitaet(data_root: Path) -> dict[str, str]:
    """Wann jede Quelle zuletzt geladen wurde.

    Keine Alarmierung - nur die Zahl, ohne die man sie nicht bauen kann. Wer
    sehen will, ob eine Quelle veraltet, sieht hier nach.
    """
    juengste: dict[str, str] = {}
    for lauf in for_root(data_root).laeufe("bronze", "**/manifest.json"):
        quelle = lauf.relativ.split("/")[1]
        wann = lauf.abgeschlossen_um
        if wann and wann > juengste.get(quelle, ""):
            juengste[quelle] = wann
    return dict(sorted(juengste.items()))


def veraltete_quellen(
    data_root: Path, maximal_alter_tage: float, *, jetzt: datetime | None = None,
    erwartet: Iterable[str] | None = None,
) -> dict[str, float | None]:
    """Quellen, die zu alt sind oder ganz fehlen - mit ihrem Alter in Tagen.

    Bis hierher wurde die Aktualitaet nur **aufgezeichnet**: Das Gesamtmanifest
    nannte je Quelle den juengsten Lauf, und niemand las es. Eine Zahl, die
    niemand gegen etwas haelt, ist keine Kontrolle. Hier wird sie gegen eine
    Schwelle gehalten.

    Eine Quelle ohne einzigen fertigen Lauf steht mit ``None`` da - sie ist
    nicht "frisch", sie ist nicht da. Der Docstring sagte das schon, der Code
    tat es nicht: Geprueft wurde nur, was ``aktualitaet`` gefunden hatte, und
    das sind genau die vorhandenen Quellen. Bei leerem Bestand kam ``{}``
    heraus, also "alles in Ordnung". Eine externe Pruefung hat das am
    15.9.2026 vorgerechnet.

    ``erwartet`` kommt aus ``ERWARTETE_QUELLEN`` und damit aus den Stufen
    selbst. Eine sechste Quelle taucht hier auf, sobald sie eine Stufe hat.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    erwartet = ERWARTETE_QUELLEN if erwartet is None else erwartet
    vorhanden = aktualitaet(data_root)
    zu_alt: dict[str, float | None] = {}
    for quelle in sorted(set(erwartet) | set(vorhanden)):
        wann = vorhanden.get(quelle)
        if wann is None:
            zu_alt[quelle] = None
            continue
        stempel = datetime.fromisoformat(wann.replace("Z", "+00:00"))
        if stempel.tzinfo is None:
            stempel = stempel.replace(tzinfo=timezone.utc)
        alter = (jetzt - stempel) / timedelta(days=1)
        if alter > maximal_alter_tage:
            zu_alt[quelle] = round(alter, 1)
    return zu_alt


def alterssatz(quelle: str, tage: float | None, schwelle: float) -> str:
    """Eine Zeile fuer Log und Zusammenfassung - fehlend liest sich anders als alt."""
    if tage is None:
        return f"{quelle}: kein fertiger Lauf vorhanden"
    return f"{quelle}: {tage:.1f} Tage alt, erlaubt sind {schwelle}"


def zeilenzahlen(data_root: Path) -> dict[str, int]:
    """Was am Ende dasteht - je Tabelle eine Zahl aus ihrem Manifest."""
    return {
        f"{t.schicht}/{t.name}": t.zeilen
        for t in for_root(data_root).tabellen()
        if t.zeilen is not None
    }


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
         ohne_ingestion: bool = False, bis: str | None = None,
         maximal_alter_tage: float | None = None) -> dict:
    stufen = auswahl(ohne_ingestion, bis)
    begonnen = datetime.now(timezone.utc)
    zu_alt: dict[str, float | None] = {}

    # Ohne Ingestion werden die Daten nicht frischer. Sind sie schon zu alt,
    # lohnt sich keine Stufe - und ein Gold auf veraltetem Bronze waere genau
    # die Zahl, die dann auf einer Folie landet.
    if maximal_alter_tage is not None and ohne_ingestion:
        zu_alt = veraltete_quellen(data_root, maximal_alter_tage)
        for quelle, tage in zu_alt.items():
            LOG.error("%s. Nichts gebaut.",
                      alterssatz(quelle, tage, maximal_alter_tage))

    # Mit Ingestion in zwei Schritten: erst laden, dann pruefen, dann ableiten.
    #
    # Bis zum 15.9.2026 lief die Pruefung nach **allen** dreizehn Stufen. Der
    # Lauf endete dann zwar mit "failed", aber Gold und Serving waren gebaut -
    # aus Daten, die der Lauf selbst als zu alt erkannt hatte. Eine externe
    # Pruefung hat genau das vorgefuehrt. Eine Kontrolle, die erst nach der
    # Veroeffentlichung greift, ist ein Protokoll, keine Kontrolle.
    geladen = [s for s in stufen if s.gruppe == "ingestion"]
    abgeleitet = [s for s in stufen if s.gruppe != "ingestion"]

    protokoll: list[dict] = []
    if not zu_alt:
        protokoll = fahre(geladen, projekt_root)
        ingestion_ok = (all(s["exit"] == 0 for s in protokoll)
                        and len(protokoll) == len(geladen))

        if maximal_alter_tage is not None and not ohne_ingestion and ingestion_ok:
            zu_alt = veraltete_quellen(data_root, maximal_alter_tage)
            for quelle, tage in zu_alt.items():
                LOG.error("%s. Nichts abgeleitet.",
                          alterssatz(quelle, tage, maximal_alter_tage))

        if ingestion_ok and not zu_alt:
            protokoll += fahre(abgeleitet, projekt_root)

    gelaufen = all(s["exit"] == 0 for s in protokoll) and len(protokoll) == len(stufen)

    geschafft = gelaufen and not zu_alt
    laeufe = bronze_laeufe(data_root)
    manifest = {
        "status": "complete" if geschafft else "failed",
        "started_at_utc": begonnen.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "stages": protokoll,
        "input_bronze_runs": laeufe,
        "input_fingerprint": fingerabdruck(laeufe),
        "source_freshness": aktualitaet(data_root),
        "freshness_check": {
            "max_age_days": maximal_alter_tage,
            "stale": zu_alt,
        },
        "output_rows": zeilenzahlen(data_root) if geschafft else {},
    }
    schreibe_manifest(data_root, manifest)
    return manifest


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Faehrt Ingestion, Silver, Gold und Serving in der "
                    "richtigen Reihenfolge."
    )
    p.add_argument("--data-root", type=Path, default=None,
                   help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    p.add_argument("--ohne-ingestion", action="store_true",
                   help="nur neu ableiten, ohne die Quellen anzufassen")
    p.add_argument("--bis", choices=GRUPPEN,
                   help="nach dieser Gruppe aufhoeren")
    p.add_argument("--trocken", action="store_true",
                   help="nur zeigen, was liefe")
    p.add_argument("--maximal-alter-tage", type=float, default=None, metavar="TAGE",
                   help="scheitern, wenn der juengste Lauf einer Quelle aelter ist "
                        "(ohne Angabe wird die Aktualitaet nur aufgezeichnet)")
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

    manifest = lauf(for_root(args.data_root).local_root, projekt_root,
                    ohne_ingestion=args.ohne_ingestion, bis=args.bis,
                    maximal_alter_tage=args.maximal_alter_tage)

    print()
    if manifest["status"] != "complete":
        zu_alt = manifest["freshness_check"]["stale"]
        if zu_alt:
            alt_ = ", ".join(
                f"{q} (fehlt)" if t is None else f"{q} ({t} Tage)"
                for q, t in zu_alt.items()
            )
            print(f"Zu alt: {alt_}. Erlaubt: {args.maximal_alter_tage} Tage.")
        else:
            gescheitert = next(s for s in manifest["stages"] if s["exit"] != 0)
            print(f"Abgebrochen bei {gescheitert['gruppe']} · {gescheitert['name']}.")
        return 1
    gesamt = sum(s["sekunden"] for s in manifest["stages"])
    print(f"{len(manifest['stages'])} Stufen in {gesamt:.0f} s.")
    print(f"Fingerabdruck der Eingaben: {manifest['input_fingerprint'][:16]}")
    print(f"Protokoll: {for_root(args.data_root).local_root / LAUF_MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
