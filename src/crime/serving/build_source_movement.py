"""Die Bewegung der Quellen, fuer das Brett »Quellbewegung« - aus Silver.

    python -m serving.build_source_movement [--data-root data] [--config-root config]

Was die beiden Quellen zwischen zwei Vollabzuegen geaendert, angefasst,
hinzugefuegt und entfernt haben: eine Zeile je bewegtem Feld, je neuer und je
verschwundener Zeile, und je ruhigem Paar eine Markierungszeile. Die Tatsachen
stehen in ``silver/source_change``; diese Tabelle bringt sie ins Release, wo
das Dashboard liest, und setzt die zwei Deutungen, die ein Vergleich beider
Staedte braucht.

**Warum Serving und nicht Gold.** Gold ist der Stern der *Taten*; diese
Tabelle beschreibt die *Quelle*. Eine Zeile hier ist keine Tat, sondern eine
Beobachtung ueber einen Abzug - sie haengt an keinem Tag und keinem Tract des
Sterns. Sie liegt deshalb neben den Vergleichstabellen und wird, wie diese,
nur als Teil eines Release veroeffentlicht. Dass Serving hier ausnahmsweise aus
Silver liest und nicht aus Gold, ist die Folge: Im Stern steht sie nicht.

**Die zwei Deutungen.**

``nibrs_code``
    Die Deliktsart der Zeile auf dem gemeinsamen Vokabular. Chicago nennt
    ``THEFT``, Detroit ``LARCENY`` - verglichen werden kann erst nach dem
    Crosswalk. Es gilt derselbe wie fuer die Falldaten
    (``build_crime_offense.wirksame_zuordnung``, Override vor Crosswalk), und
    zwar der **heutige**: Wird eine Zuordnung korrigiert, folgt die
    Quellbewegung mit, genau wie ``fact_offense``.
``is_stamp``
    Ob das Feld ein Zeitstempel der Quelle ist (``build_source_change.QUELLEN``,
    ``stempel``). Ein bewegter Stempel ist keine Inhaltsaenderung - aber er
    steht in der Feldstatistik, und wer sie liest, muss die beiden trennen
    koennen.

**Eine leere Tabelle ist eine Aussage.** Gibt es noch kein Paar - in einer
frischen Umgebung mit einem einzigen Abzug je Jahrgang -, steht ``silver/
source_change`` nicht da. Gebaut wird dann trotzdem, mit null Zeilen und dem
Vermerk im Manifest: Ein Release ohne die Tabelle hiesse unvollstaendig, eines
mit ihr sagt, dass noch nichts zu vergleichen war.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from manifeste import code_stand, eingabe_abdruck, referenz, referenzdatei
from serving import SERVING_LAYER
from silver_pipeline import (
    PARQUET_FILE,
    SILVER_LAYER,
    TransformError,
    connect,
    publish,
    schema_of,
)
from silver_pipeline.build_crime_offense import (
    CONFIG_DIR,
    IUCR_MAPPING,
    MAPPING_OVERRIDES,
    MICR_MAPPING,
    pruefe_overrides,
    wirksame_zuordnung,
)
from silver_pipeline.build_source_change import QUELLEN
from silver_pipeline.build_source_change import TABLE as SILVER_TABELLE
from storage import for_root

LOG = logging.getLogger("build_source_movement")

TABELLE = "source_movement"
TABELLEN = (TABELLE,)

#: Der Deutungsvertrag. Jede Erhoehung gehoert in AENDERUNGEN.md.
CONTRACT_VERSION = 1

#: Die Arten aus Silver und wie sie hier heissen. Eine Art, die hier fehlt,
#: bricht den Bau ab - eine stillschweigend leere ``change_type`` saehe aus
#: wie eine Zeile, die zu keiner Art gehoert.
ARTEN = {
    "geaendert": "changed",
    "beruehrt": "touched",
    "neu": "added",
    "verschwunden": "removed",
    "unveraendert": "unchanged",
}

SPALTEN = (
    "city", "offense_id", "previous_run_id", "run_id",
    "previous_snapshot_at", "snapshot_at", "change_type", "field",
    "is_stamp", "value_old", "value_new", "source_offense_code",
    "source_offense_category", "nibrs_code", "previous_rows", "snapshot_rows",
    "event_year",
)

GRANULARITAET = (
    "ein bewegtes Feld einer Zeile zwischen zwei Vollabzuegen; je neuer und "
    "je verschwundener Zeile eine Zeile ohne Feld; je ruhigem Paar eine "
    "Markierungszeile ohne offense_id")

NOTIZEN = {
    "zaehlen": (
        "Eintraege zaehlt man ueber DISTINCT (city, previous_run_id, run_id, "
        "offense_id), nicht ueber Zeilen: Eine geaenderte Zeile steht hier "
        "so oft, wie sich Felder bewegt haben"),
    "jahrgang": (
        "event_year ist der Tatjahrgang des Paares; beide Abzuege tragen "
        "denselben. Leer bei Abzuegen ohne Jahrgang im Manifest"),
    "rate": (
        "previous_rows ist der Nenner: die Schluessel im aelteren Abzug. Je "
        "Paar einmal zaehlen, nicht je Zeile"),
    "stempel": (
        "is_stamp markiert Zeitstempel der Quelle. change_type = touched heisst: "
        "nur Stempel haben sich bewegt"),
    "nibrs_code": (
        "aus source_offense_code ueber den heute gueltigen Crosswalk samt "
        "Overrides - derselbe wie fuer fact_offense"),
    "leer": (
        "keine Zeile heisst: noch kein Paar zweier Vollabzuege desselben "
        "Jahrgangs, nicht: keine Bewegung. Ein ruhiges Paar hat eine "
        "Markierungszeile"),
}


def table_dir(data_root: Path) -> Path:
    return data_root / SERVING_LAYER / f"dataset={TABELLE}"


def silver_quelle(data_root: Path) -> tuple[str, dict[str, Any]] | None:
    """Lesepfad und Manifest von ``silver/source_change`` - oder ``None``."""
    ablage = for_root(data_root)
    rel = f"{SILVER_LAYER}/dataset={SILVER_TABELLE}"
    if not ablage.exists(rel, PARQUET_FILE):
        return None
    manifest = json.loads(ablage.read_text(rel, "manifest.json"))
    return ablage.resolve_read_path(rel, PARQUET_FILE), manifest


def stempel_sql() -> str:
    """Je Stadt die Stempelfelder, als Relation (city, field)."""
    paare = [f"('{q.stadt}', '{f}')" for q in QUELLEN for f in sorted(q.stempel)]
    return (f"SELECT * FROM (VALUES {', '.join(paare)}) AS t(city, field)" if paare
            else "SELECT NULL::VARCHAR AS city, NULL::VARCHAR AS field WHERE false")


def abfrage(silver: str, config_root: Path) -> str:
    arten = " ".join(f"WHEN '{a}' THEN '{e}'" for a, e in ARTEN.items())
    return f"""
        SELECT s.city, s.offense_id,
               s.vorher_run_id AS previous_run_id, s.run_id,
               s.vorher_am AS previous_snapshot_at, s.beobachtet_am AS snapshot_at,
               CASE s.art {arten}
                    ELSE error('unbekannte Art in silver/source_change: ' || s.art)
               END AS change_type,
               s.feld AS field,
               CASE WHEN s.feld IS NULL THEN NULL
                    ELSE st.field IS NOT NULL END AS is_stamp,
               s.wert_alt AS value_old, s.wert_neu AS value_new,
               s.quellcode AS source_offense_code,
               s.quellkategorie AS source_offense_category,
               z.nibrs_code,
               s.bestand_vorher AS previous_rows, s.bestand_nachher AS snapshot_rows,
               s.jahrgang AS event_year
        FROM read_parquet('{silver}', hive_partitioning = false) s
        LEFT JOIN ({stempel_sql()}) st ON st.city = s.city AND st.field = s.feld
        LEFT JOIN ({wirksame_zuordnung(config_root)}) z
          ON z.city = s.city AND z.quellcode = s.quellcode
    """


def leer_sql() -> str:
    """Dieselben Spalten, keine Zeile."""
    typen = {"previous_snapshot_at": "TIMESTAMP", "snapshot_at": "TIMESTAMP",
             "is_stamp": "BOOLEAN", "previous_rows": "BIGINT", "snapshot_rows": "BIGINT",
             "event_year": "INTEGER"}
    return "SELECT " + ", ".join(
        f"CAST(NULL AS {typen.get(s, 'VARCHAR')}) AS {s}" for s in SPALTEN) + " WHERE false"


def pruefe(con: Any, quelle: dict[str, Any] | None) -> dict[str, Any]:
    """Die Gegenprobe: so viele Zeilen und Arten wie Silver, kein Schluessel doppelt zugeordnet."""
    zeilen = con.execute(f"SELECT count(*) FROM {TABELLE}").fetchone()[0]
    if quelle is not None and zeilen != quelle.get("row_count", zeilen):
        raise TransformError(
            f"{TABELLE} hat {zeilen} Zeilen, silver/{SILVER_TABELLE} nennt "
            f"{quelle['row_count']} - der Crosswalk hat Zeilen verdoppelt")
    arten = dict(con.execute(
        f"SELECT change_type, count(*) FROM {TABELLE} GROUP BY 1 ORDER BY 1").fetchall())
    ohne_zuordnung = con.execute(f"""
        SELECT count(*) FROM {TABELLE}
        WHERE source_offense_code IS NOT NULL AND nibrs_code IS NULL""").fetchone()[0]
    return {"rows": zeilen, "change_types": arten,
            "code_without_nibrs": ohne_zuordnung}


def build(data_root: Path, config_root: Path) -> dict[str, Path]:
    """Baut die Tabelle und legt sie lokal ab. Hinauf geht sie nur im Release."""
    begonnen = datetime.now(timezone.utc)
    quelle = silver_quelle(data_root)
    pruefe_overrides(config_root)
    herkunft: dict[str, Any] = {
        "crosswalks": [referenzdatei(config_root / n)
                       for n in (IUCR_MAPPING, MICR_MAPPING, MAPPING_OVERRIDES)],
    }
    if quelle is not None:
        herkunft[f"silver_{SILVER_TABELLE}"] = referenz(quelle[0], quelle[1])

    con = connect()
    try:
        from storage import duckdb as storage_duckdb
        ablage = for_root(data_root)
        if ablage.config.remote:
            storage_duckdb.s3_einrichten(con, ablage.config)
        sql = abfrage(quelle[0], config_root) if quelle is not None else leer_sql()
        con.execute(f"CREATE TABLE {TABELLE} AS {sql}")
        nachweis = pruefe(con, quelle[1] if quelle is not None else None)
        manifest = {
            "status": "complete",
            "contract_version": CONTRACT_VERSION,
            "code_version": code_stand(),
            "table": TABELLE,
            "layer": SERVING_LAYER,
            "row_count": nachweis["rows"],
            "grain": GRANULARITAET,
            "built_at_utc": begonnen.isoformat(),
            "derived_from": herkunft,
            "input_fingerprint": eingabe_abdruck(herkunft),
            "notes": NOTIZEN | ({} if quelle is not None else {
                "keine_quelle": f"silver/{SILVER_TABELLE} fehlt - noch kein Paar"}),
            "checks": nachweis,
            "schema": schema_of(con, TABELLE),
        }
        ziel = publish(con, TABELLE, table_dir(data_root), manifest,
                       ordnung="city, previous_snapshot_at, previous_run_id, run_id, "
                               "offense_id, field")
        LOG.info("%s: %s Zeilen -> %s", TABELLE, f"{nachweis['rows']:,}", ziel)
    finally:
        con.close()
    return {TABELLE: ziel}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data-root", type=Path, default=None,
                   help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    p.add_argument("--config-root", type=Path, default=Path(CONFIG_DIR))
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from storage.verwaltet import sperre
    sperre(for_root(args.data_root).local_root, worker_erlaubt=True)
    from storage.analysesitzung import schreibzugriff
    # Wie build_comparison: Serving schreibt nicht nach bronze/silver/gold.
    with schreibzugriff(for_root(args.data_root).local_root, invalidieren=False):
        try:
            build(for_root(args.data_root).local_root, args.config_root)
        except TransformError as fehler:
            LOG.error("%s", fehler)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
