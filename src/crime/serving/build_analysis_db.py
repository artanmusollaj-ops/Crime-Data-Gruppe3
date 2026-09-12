"""Baut ``data/serving/analyse.duckdb`` - die Auswertungsumgebung.

Aufruf aus dem Projekt-Root::

    python -m serving.build_analysis_db

Danach::

    duckdb data/serving/analyse.duckdb
    D SELECT city, nibrs_description, count(*) FROM crime_offense
      GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10;

Was das Skript tut: Es sucht jede Tabelle unter ``data/silver/`` und
``data/gold/``, legt je eine **Sicht** darauf an und schreibt dazu zwei
Hilfssichten - ``herkunft`` und ``tabellen``. Die Datei haelt keine Daten;
warum das so ist, steht im Modulkopf von ``serving``.

Drei Eigenheiten, die beim Bauen zu beachten waren:

1. **Absolute Pfade.** DuckDB loest relative Pfade gegen das
   Arbeitsverzeichnis des Prozesses auf, nicht gegen den Ort der Datenbank.
   Eine Sicht mit relativem Pfad funktionierte also nur, solange man die Datei
   aus dem Projekt-Root oeffnet. Die Datei ist ohnehin abgeleitet und nicht
   versioniert, deshalb sind absolute Pfade der ehrlichere Weg: Wer das
   Projekt verschiebt, baut sie neu.
2. **Vintages.** ``tract`` liegt unter ``dataset=tract/vintage=2024/``. Die
   Sicht zeigt auf die juengste Vintage und nennt sie in ``tabellen``, damit
   niemand raten muss, welchen Stand er sieht.
3. **Atomar veroeffentlicht.** Geschrieben wird in eine ``.part``-Datei, die
   erst nach dem letzten Schritt umbenannt wird - sonst haette ein
   abgebrochener Lauf eine halbe Datenbank hinterlassen, in der die Haelfte
   der Sichten fehlt.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import duckdb

from serving import DATABASE_NAME, SERVING_LAYER


LOG = logging.getLogger("build_analysis_db")

PARQUET_FILE = "part-0001.parquet"

# Die Schichten, die abfragbar gemacht werden. Beide sind gebaut: vier
# Silver-Tabellen und die fuenf des Sternschemas, zusammen neun Sichten. Als
# Gold dazukam, war dafuer nichts zu tun - discover() nimmt auf, was da ist.
SCHICHTEN = ("silver", "gold")


class Tabelle(NamedTuple):
    """Eine Tabelle, die als Sicht erscheinen soll."""

    name: str
    layer: str
    path: Path
    partition: str


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baut die Auswertungsdatenbank aus Silver und Gold."
    )
    parser.add_argument(
        "--data-root", type=Path, default=Path("data"),
        help="Wurzel der Schichten (Vorgabe: data)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def database_path(data_root: Path) -> Path:
    return data_root / SERVING_LAYER / DATABASE_NAME


def discover(data_root: Path) -> list[Tabelle]:
    """Findet jede Tabelle unter den Schichten.

    Gesucht wird nach ``dataset=<name>/**/part-0001.parquet``. Liegen mehrere
    Vintages vor, gewinnt die letzte in Sortierreihenfolge - bei ``vintage=``
    ist das die juengste.
    """
    gefunden: dict[str, Tabelle] = {}
    for layer in SCHICHTEN:
        wurzel = data_root / layer
        if not wurzel.exists():
            continue
        for parquet in sorted(wurzel.glob(f"dataset=*/**/{PARQUET_FILE}")):
            name = None
            partition = ""
            for teil in parquet.relative_to(wurzel).parts:
                if teil.startswith("dataset="):
                    name = teil.removeprefix("dataset=")
                elif "=" in teil:
                    partition = teil
            if name is None:
                continue
            # Spaetere Schichten und juengere Vintages ueberschreiben.
            gefunden[name] = Tabelle(name, layer, parquet.resolve(), partition)
    return sorted(gefunden.values(), key=lambda t: (t.layer, t.name))


def create_views(con: duckdb.DuckDBPyConnection, tabellen: list[Tabelle]) -> None:
    """Legt je Tabelle eine Sicht an, plus zwei Hilfssichten.

    ``herkunft`` und ``tabellen`` sind das, was eine Auswertungsumgebung von
    einem Haufen Dateien unterscheidet: Man kann sie fragen, was man vor sich
    hat, ohne das Repository zu kennen.
    """
    for t in tabellen:
        try:
            con.execute(
                f'CREATE OR REPLACE VIEW "{t.name}" AS '
                f"SELECT * FROM read_parquet('{t.path}')"
            )
        except duckdb.Error as fehler:
            # DuckDB prueft die Datei schon beim Anlegen der Sicht. Der Fehler
            # bekommt hier denselben Wortlaut wie in verify(), damit der
            # Aufrufer nicht zwei Formulierungen fuer dieselbe Sache kennen muss.
            raise RuntimeError(
                f"Sicht {t.name} ist nicht lesbar: {t.path}: {fehler}"
            ) from fehler
        LOG.info("Sicht %s -> %s", t.name, t.path)

    werte = ", ".join(
        f"('{t.name}', '{t.layer}', '{t.partition}', '{t.path}')" for t in tabellen
    )
    con.execute(f"""
        CREATE OR REPLACE VIEW tabellen AS
        SELECT * FROM (VALUES {werte}) AS t(name, schicht, partition, datei)
    """)

    gebaut = datetime.now(timezone.utc).isoformat()
    con.execute(f"""
        CREATE OR REPLACE VIEW herkunft AS
        SELECT * FROM (VALUES
            ('gebaut_am_utc', '{gebaut}'),
            ('duckdb', '{duckdb.__version__}'),
            ('tabellen', '{len(tabellen)}'),
            ('hinweis', 'Sichten ueber Parquet. Die Datei haelt keine Daten; '
                        'ein Silver-Neubau ist sofort sichtbar.'),
            ('eigene_tabellen', 'CREATE TABLE meins AS SELECT ... ist erlaubt '
                                'und liegt neben den Sichten.')
        ) AS h(schluessel, wert)
    """)


def verify(con: duckdb.DuckDBPyConnection, tabellen: list[Tabelle]) -> dict[str, int]:
    """Jede Sicht muss lesbar sein und Zeilen liefern.

    Eine Sicht auf eine Datei, die es nicht mehr gibt, faellt erst beim ersten
    ``SELECT`` auf - also bei dem, der auswerten will. Lieber hier.
    """
    zeilen: dict[str, int] = {}
    for t in tabellen:
        try:
            zeilen[t.name] = con.execute(
                f'SELECT count(*) FROM "{t.name}"'
            ).fetchone()[0]
        except duckdb.Error as fehler:
            raise RuntimeError(
                f"Sicht {t.name} ist nicht lesbar: {fehler}"
            ) from fehler
    return zeilen


def build(data_root: Path) -> Path:
    tabellen = discover(data_root)
    if not tabellen:
        raise RuntimeError(
            f"Keine Tabellen unter {data_root}/silver oder {data_root}/gold. "
            "Zuerst die Silver-Schicht bauen, etwa "
            "'python -m silver_pipeline.build_crime_offense'."
        )

    ziel = database_path(data_root)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    arbeit = ziel.with_name(f".{ziel.name}.part")
    arbeit.unlink(missing_ok=True)

    con = duckdb.connect(str(arbeit))
    try:
        # Fuer die Geometrie in tract. Fehlt die Extension, bleiben die Sichten
        # trotzdem lesbar - nur ST_-Funktionen stehen dann nicht bereit.
        try:
            con.execute("INSTALL spatial")
            con.execute("LOAD spatial")
        except duckdb.Error as fehler:
            LOG.warning("spatial nicht verfuegbar, Geometrie bleibt WKB: %s", fehler)

        create_views(con, tabellen)
        zeilen = verify(con, tabellen)
    except BaseException:
        # Eine halbe Datenbank ist schlimmer als keine: In ihr fehlt ein Teil
        # der Sichten, ohne dass man es ihr ansieht.
        con.close()
        arbeit.unlink(missing_ok=True)
        raise
    finally:
        con.close()

    arbeit.replace(ziel)
    for name, n in zeilen.items():
        LOG.info("  %-18s %8d Zeilen", name, n)
    LOG.info("%s: %d Sichten, %.1f KB",
             ziel, len(tabellen), ziel.stat().st_size / 1024)
    return ziel


def main() -> int:
    args = arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        ziel = build(args.data_root)
    except RuntimeError as fehler:
        LOG.error("%s", fehler)
        return 1
    print(f"\nBereit. Abfragen mit:\n  duckdb {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
