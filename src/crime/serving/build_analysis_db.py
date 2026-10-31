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
from typing import Any
from typing import NamedTuple

import duckdb

from storage import TABELLENSCHICHTEN, for_root
from storage import duckdb as storage_duckdb

from serving import DATABASE_NAME, SERVING_LAYER


LOG = logging.getLogger("build_analysis_db")

PARQUET_FILE = "part-0001.parquet"

# Die Schichten, die abfragbar gemacht werden. Beide sind gebaut: vier
# Silver-Tabellen und die fuenf des Sternschemas, zusammen neun Sichten. Als
# Gold dazukam, war dafuer nichts zu tun - discover() nimmt auf, was da ist.
# Seit dem 17.9.2026 auch serving: die vier Vergleichstabellen aus
# build_comparison bekommen Sichten wie jede andere Tabelle. Die Datenbank
# selbst liegt zwar auch unter serving/, aber nicht unter dataset= - der
# Glob findet sie nicht.
# Die Liste steht kanonisch in ``storage.backend``; hier ist sie die Auswahl
# daraus - ein Name, keine zweite Fassung.
SCHICHTEN = TABELLENSCHICHTEN


class Tabelle(NamedTuple):
    """Eine Tabelle, die als Sicht erscheinen soll."""

    name: str
    layer: str
    path: str | Path   # lokal absolut, oder s3://
    partition: str


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baut die Auswertungsdatenbank aus Silver und Gold."
    )
    parser.add_argument(
        "--data-root", type=Path, default=None,
        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)",
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
    ablage = for_root(data_root)
    for layer in SCHICHTEN:
        for rel in ablage.list_files(layer, f"dataset=*/**/{PARQUET_FILE}"):
            name = None
            partition = ""
            for teil in rel.split("/")[1:]:
                if teil.startswith("dataset="):
                    name = teil.removeprefix("dataset=")
                elif "=" in teil:
                    partition = teil
            if name is None:
                continue
            # Lokal absolut, damit die Datenbank von ueberall lesbar bleibt;
            # auf S3 die URL. Im Hybridmodus entscheidet die Ablage je Datei.
            pfad = ablage.resolve_read_path(rel)
            path: str | Path = pfad if pfad.startswith("s3://") else Path(pfad).resolve()
            # Spaetere Schichten und juengere Vintages ueberschreiben.
            gefunden[name] = Tabelle(name, layer, path, partition)
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


def uebernimm_eigene_tabellen(con: duckdb.DuckDBPyConnection, alt: Path) -> list[str]:
    """Kopiert selbst angelegte Tabellen aus der bisherigen Datenbank herueber.

    **Warum das noetig ist.** Konzept 5.2 laedt ausdruecklich dazu ein: *"wer
    ein Zwischenergebnis behalten will, legt daneben ``CREATE TABLE meins AS
    SELECT …`` an"*, und die Hinweistabelle der Datenbank sagt dasselbe. Nur
    entstand beim Neubau eine **neue Datei**, die die bisherige ersetzte - die
    eigene Tabelle war weg, ohne Meldung. Eine externe Pruefung hat das am
    15.9.2026 vorgefuehrt; die Einladung stand da seit dem ersten Tag.

    Uebernommen wird, was eine echte Tabelle ist. Alles, was dieses Modul
    anlegt, sind Sichten - was also als Tabelle dasteht, hat jemand selbst
    angelegt. Traegt eine davon den Namen einer Sicht, gewinnt die Sicht und
    die Tabelle wird mit Meldung uebergangen: Sonst verdeckte ein
    Zwischenergebnis stillschweigend die Daten, ueber die es gerechnet wurde.
    """
    if not alt.is_file():
        return []
    eigene: list[str] = []
    con.execute(f"ATTACH '{alt}' AS vorher (READ_ONLY)")
    try:
        sichten = {r[0] for r in con.execute(
            "SELECT view_name FROM duckdb_views() WHERE NOT internal"
        ).fetchall()}
        namen = [r[0] for r in con.execute(
            "SELECT table_name FROM duckdb_tables() "
            "WHERE database_name = 'vorher' AND NOT internal ORDER BY table_name"
        ).fetchall()]
        for name in namen:
            if name in sichten:
                LOG.warning(
                    "Eigene Tabelle %r nicht uebernommen: Eine Sicht dieses "
                    "Namens gehoert zur Auswertung. Erst umbenennen, dann neu "
                    "bauen.", name,
                )
                continue
            con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM vorher."{name}"')
            eigene.append(name)
    except duckdb.Error as fehler:
        LOG.warning("Eigene Tabellen nicht uebernommen: %s", fehler)
    finally:
        con.execute("DETACH vorher")
    return eigene


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

    # Die Datenbank selbst bleibt immer lokal (data/serving/), in jedem Modus.
    # Kann die Ablage S3 lesen, bringt die Verbindung httpfs und ein
    # temporaeres Secret mit - und wer die Datei spaeter oeffnet, braucht
    # dasselbe: storage.duckdb.connect(config, pfad).
    con = storage_duckdb.connect(for_root(data_root).config, arbeit)
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
        uebernommen = uebernimm_eigene_tabellen(con, ziel)
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
    if uebernommen:
        LOG.info("  eigene Tabellen uebernommen: %s", ", ".join(uebernommen))
    LOG.info("%s: %d Sichten, %.1f KB",
             ziel, len(tabellen), ziel.stat().st_size / 1024)
    return ziel


def build_selbststaendig(
    tabellen: list[tuple[str, Path]],
    ziel: Path,
    release: dict[str, Any],
) -> Path:
    """Eine Datenbank mit **Tabellen** statt Sichten - fuer ein Release.

    Alles oben gilt weiter: Die Arbeitsdatenbank haelt Sichten, weil Sichten
    nie veralten und keinen zweiten Bestand bilden. Ein Release ist etwas
    anderes. Es ist unveraenderlich - eine Kopie darin kann nicht veralten,
    weil sich nichts darunter mehr bewegt - und es wird auf einen anderen
    Rechner geholt, wo Sichten mit absoluten Pfaden ins Leere zeigten.

    ``release_info`` traegt Kennung und Zeitpunkt, damit ein Dashboard sagen
    kann, welchen Stand es zeigt (Rat vom 17.9.2026, Schritt 6).
    """
    ziel.parent.mkdir(parents=True, exist_ok=True)
    arbeit = ziel.with_name(f".{ziel.name}.part")
    arbeit.unlink(missing_ok=True)
    con = storage_duckdb.verbinde(arbeit)
    try:
        try:
            con.execute("INSTALL spatial")
            con.execute("LOAD spatial")
        except duckdb.Error as fehler:
            LOG.warning("spatial nicht verfuegbar, Geometrie bleibt WKB: %s", fehler)
        for name, parquet in tabellen:
            con.execute(
                f'CREATE TABLE "{name}" AS SELECT * FROM read_parquet(?)',
                [str(parquet)],
            )
        con.execute(
            "CREATE TABLE release_info AS SELECT ? AS release_id, ? AS created_at_utc",
            [release["release_id"], release["created_at_utc"]],
        )
    except BaseException:
        con.close()
        arbeit.unlink(missing_ok=True)
        raise
    finally:
        con.close()
    arbeit.replace(ziel)
    LOG.info("%s: %d Tabellen, %.1f MB", ziel, len(tabellen), ziel.stat().st_size / 1e6)
    return ziel


def main() -> int:
    args = arguments()
    from storage.verwaltet import sperre
    sperre(for_root(args.data_root).local_root, worker_erlaubt=True)
    from storage.analysesitzung import schreibzugriff
    with schreibzugriff(for_root(args.data_root).local_root, invalidieren=True):
        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.INFO,
            format="%(levelname)s %(message)s",
        )
        try:
            ziel = build(for_root(args.data_root).local_root)
        except RuntimeError as fehler:
            LOG.error("%s", fehler)
            return 1
        print(f"\nBereit. Abfragen mit:\n  duckdb {ziel}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
