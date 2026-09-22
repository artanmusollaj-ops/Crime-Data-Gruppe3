"""Laedt ein Release nach ClickHouse - mit Nachweis, nicht auf Zuruf.

    python -m serving.load_clickhouse              # das aktuelle Release
    python -m serving.load_clickhouse --trocken    # nur zeigen, was liefe

**Warum es diesen Schritt ueberhaupt gibt.** Ein Release ist Parquet plus
Pruefsummen und beantwortet jede Frage - aber nur dem, der DuckDB startet. Die
Analyseplattform soll einem Analysten gehoeren, der SQL tippt und eine Antwort
will. ClickHouse ist dafuer der Zugang; dieses Modul ist der Weg dorthin.

**Die Zusage, die dabei nicht verlorengehen darf.** Alles vor dieser Stelle
ruht auf unveraenderlichen Laeufen: Ein Stand ist entweder ganz da oder gar
nicht, und jede Zahl laesst sich auf ein Release zurueckfuehren. Eine Datenbank
ist veraenderlich und kennt das nicht. Deshalb laedt dieses Modul **nie** in
``fact_offense``, sondern immer in eine Tabelle, deren Name das Release traegt,
prueft danach, und legt erst dann die Sicht ``fact_offense`` darauf um. Faellt
die Pruefung, bleibt der alte Stand stehen - dasselbe Versprechen wie beim
``.part``-Umbenennen in ``storage``.

**Was hier Entscheidung ist und was abgelesen.** Abgelesen wird die
Spaltenliste: Sie kommt aus dem Parquet des Releases, damit eine neue
Gold-Spalte nicht stillschweigend fehlt. Entschieden sind die Sortierung, die
Partitionierung und welche Spalten als ``LowCardinality`` liegen - das sind
Leistungsfragen, die niemand ableiten kann. Ein Test haelt beides gegeneinander:
Jede Spalte des Releases braucht eine Entscheidung.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pyarrow.parquet as pq

DATENWURZEL = Path("data")
TABELLE = "fact_offense"
QUELLE_IM_RELEASE = "gold/dataset=fact_offense/part-0001.parquet"

# --------------------------------------------------------------------------
# Die Entscheidungen. Alles hier ist Abwaegung, keine Ableitung.
# --------------------------------------------------------------------------

#: ClickHouse legt die Zeilen physisch in dieser Reihenfolge ab und baut darauf
#: seinen duennen Index. Eine Abfrage, die nach einem Praefix davon filtert,
#: liest ein paar Bloecke; eine andere liest die Tabelle.
#:
#: Naheliegend waere ``(reporting_city, date, nibrs_code)`` gewesen - Stadt,
#: Zeitraum, Delikt ist die Frage des Dashboards. ``nibrs_code`` traegt aber
#: drei NULL (die unmapped-Zeilen aus Chicago), und ein nullbarer
#: Sortierschluessel verlangt in ClickHouse ``allow_nullable_key``. Drei Zeilen
#: von 345'073 sind diesen Schalter nicht wert; innerhalb eines Tages einer
#: Stadt ist der Rest ohnehin ein kleiner Block.
SORTIERUNG = ("reporting_city", "date")

#: Ein Jahrgang braucht das nicht. Kommt der zweite dazu, kann ClickHouse ganze
#: Monate ueberspringen, statt sie zu lesen.
PARTITION = "toYYYYMM(date)"

#: Der Schluessel, gegen den der Abgleich zaehlt.
SCHLUESSEL = "offense_id"

#: Woerterbuch statt Text. Gemessen am Jahrgang 2024: reporting_city 2,
#: mapping_status 4, geo_status 4, nibrs_family 25, nibrs_code 59,
#: source_offense_code 429, tract_geoid 1'146 verschiedene Werte. Oberhalb von
#: rund zehntausend kippt der Vorteil - offense_id (345'073) gehoert deshalb
#: nicht dazu, obwohl es verlockend aussieht.
NIEDRIGE_KARDINALITAET = frozenset({
    "reporting_city", "nibrs_code", "nibrs_family", "tract_geoid",
    "source_offense_code", "mapping_status", "geo_status",
})

#: Arrow sagt, was in der Datei steht; ClickHouse braucht seinen eigenen Namen
#: dafuer. Kein Eintrag heisst: Diese Spalte ist noch nicht entschieden, und
#: der Bau bricht ab, statt zu raten.
TYPEN = {
    "string": "String",
    "bool": "Bool",
    "double": "Float64",
    "int8": "Int8",
    "int16": "Int16",
    "int32": "Int32",
    "int64": "Int64",
    "date32[day]": "Date",
    "timestamp[us]": "DateTime64(6)",
    "timestamp[ms]": "DateTime64(3)",
    "timestamp[s]": "DateTime",
}


class LadeFehler(RuntimeError):
    """Etwas stimmt nicht - und dann wird nichts umgelegt."""


@dataclass(frozen=True)
class Spalte:
    name: str
    arrow: str
    nullable: bool

    @property
    def clickhouse(self) -> str:
        grund = TYPEN.get(self.arrow)
        if grund is None:
            raise LadeFehler(
                f"Fuer {self.name} ({self.arrow}) ist kein ClickHouse-Typ "
                f"entschieden. Eintrag in TYPEN ergaenzen - geraten wird nicht."
            )
        if self.name in NIEDRIGE_KARDINALITAET and grund != "String":
            raise LadeFehler(
                f"{self.name} steht in NIEDRIGE_KARDINALITAET, ist aber "
                f"{grund} - LowCardinality lohnt nur fuer String.")
        # Die Schachtelung ist nicht beliebig: ClickHouse verweigert
        # ``Nullable(LowCardinality(String))`` mit *Nested type cannot be
        # inside Nullable type*. Richtig herum ist LowCardinality aussen.
        if self.nullable:
            grund = f"Nullable({grund})"
        if self.name in NIEDRIGE_KARDINALITAET:
            grund = f"LowCardinality({grund})"
        return grund


# --------------------------------------------------------------------------
# Abgelesen: was im Release wirklich steht
# --------------------------------------------------------------------------


def spalten(parquet: Path) -> list[Spalte]:
    """Die Spalten aus der Datei - nicht aus einer zweiten Liste.

    Bewusst ueber das Arrow-Schema und nicht ueber ``DESCRIBE``: DuckDB
    ergaenzt aus dem Pfad ``dataset=fact_offense`` eine Hive-Spalte
    ``dataset``, die in der Datei gar nicht steht. Sie gehoert nicht in die
    Zieltabelle.

    **Nullbarkeit wird gezaehlt, nicht geglaubt.** Parquet markiert jede Spalte
    als nullbar, auch wo nie ein NULL steht - uebernaehme man das, waeren alle
    22 Spalten ``Nullable``, obwohl es nur acht sind. Das kostet ein Byte je
    Zeile und Spalte und blockiert Optimierungen, ohne irgendetwas auszusagen.
    """
    import duckdb

    schema = pq.ParquetFile(parquet).schema_arrow
    namen = [f.name for f in schema]
    teile = ", ".join(
        f'count(*) FILTER (WHERE "{n}" IS NULL)' for n in namen)
    con = duckdb.connect()
    try:
        leer = con.execute(
            f"SELECT {teile} FROM read_parquet('{parquet}')").fetchone()
    finally:
        con.close()
    return [Spalte(f.name, str(f.type), n > 0) for f, n in zip(schema, leer)]


def tabellenname(release_id: str) -> str:
    """``2026-09-21T12-55-05Z`` -> ``fact_offense_20260921T125505Z``.

    ClickHouse-Bezeichner vertragen weder Bindestrich noch Doppelpunkt. Die
    Kennung bleibt trotzdem lesbar, und genau darum geht es: Wer die Tabelle
    sieht, weiss, aus welchem Release sie stammt.
    """
    return f"{TABELLE}_{re.sub(r'[^0-9A-Za-z]', '', release_id)}"


# --------------------------------------------------------------------------
# Die erzeugten Anweisungen. Reine Funktionen - pruefbar ohne ClickHouse.
# --------------------------------------------------------------------------


def ddl(tabelle: str, felder: list[Spalte]) -> str:
    """Die Anweisung - und die Zusicherung, dass der Schluessel traegt.

    Ein nullbarer Sortierschluessel ist in ClickHouse nur mit einem Schalter
    erlaubt. Statt ihn zu setzen, faellt hier der Bau: Wenn eine
    Schluesselspalte NULL bekommt, hat sich etwas in Gold geaendert, und das
    gehoert angesehen und nicht umschifft.
    """
    nach_name = {s.name: s for s in felder}
    for name in (*SORTIERUNG, SCHLUESSEL):
        s = nach_name.get(name)
        if s is None:
            raise LadeFehler(f"{name} steht im Schluessel, aber nicht im Release")
        if s.nullable:
            raise LadeFehler(
                f"{name} traegt NULL und steht im Schluessel. Entweder die "
                f"Sortierung aendern oder klaeren, warum Gold dort NULL liefert.")
    zeilen = ",\n".join(f"    {s.name} {s.clickhouse}" for s in felder)
    return (f"CREATE TABLE IF NOT EXISTS {tabelle} (\n{zeilen}\n)\n"
            f"ENGINE = MergeTree\n"
            f"PARTITION BY {PARTITION}\n"
            f"ORDER BY ({', '.join(SORTIERUNG)})")


def einfuegen_aus_s3(tabelle: str, url: str, schluessel: str, geheim: str) -> str:
    """Ein einziger grosser Insert.

    ClickHouse legt je Insert einen Part an und verschmilzt sie im Hintergrund.
    Viele kleine Inserts laufen deshalb in *too many parts* - die Stapelung
    passiert hier also nicht, sondern wird vermieden.
    """
    return (f"INSERT INTO {tabelle} SELECT * FROM s3("
            f"'{url}', '{schluessel}', '{geheim}', 'Parquet')")


def sicht_umlegen(tabelle: str) -> str:
    """Der Zeigerwechsel. Bis hierher sieht niemand den neuen Stand."""
    return f"CREATE OR REPLACE VIEW {TABELLE} AS SELECT * FROM {tabelle}"


# --------------------------------------------------------------------------
# Der Abgleich: dieselbe Frage an beide Seiten
# --------------------------------------------------------------------------
# Eine Pruefsumme ueber den Inhalt waere staerker, laesst sich zwischen zwei
# Engines aber nicht ehrlich vergleichen - sie haengt an der Textdarstellung
# von Zahlen und Zeitstempeln. Diese drei Fragen haengen daran nicht.


def abgleich_clickhouse(tabelle: str) -> dict[str, str]:
    return {
        "zeilen": f"SELECT count() FROM {tabelle}",
        "schluessel": f"SELECT uniqExact({SCHLUESSEL}) FROM {tabelle}",
        "verteilung": (
            f"SELECT reporting_city, mapping_status, geo_status, count() "
            f"FROM {tabelle} GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"),
    }


def abgleich_release(parquet: Path) -> dict[str, Any]:
    import duckdb

    con = duckdb.connect()
    quelle = f"read_parquet('{parquet}')"
    try:
        return {
            "zeilen": con.execute(f"SELECT count(*) FROM {quelle}").fetchone()[0],
            "schluessel": con.execute(
                f"SELECT count(DISTINCT {SCHLUESSEL}) FROM {quelle}").fetchone()[0],
            "verteilung": [tuple(z) for z in con.execute(
                f"SELECT reporting_city, mapping_status, geo_status, count(*) "
                f"FROM {quelle} GROUP BY 1, 2, 3 ORDER BY 1, 2, 3").fetchall()],
        }
    finally:
        con.close()


def vergleiche(erwartet: dict[str, Any], gefunden: dict[str, Any]) -> None:
    """Weicht etwas ab, wird nichts umgelegt."""
    for name in ("zeilen", "schluessel"):
        if erwartet[name] != gefunden[name]:
            raise LadeFehler(
                f"{name}: Release sagt {erwartet[name]:,}, ClickHouse "
                f"{gefunden[name]:,} - die Sicht bleibt auf dem alten Stand.")
    if erwartet["verteilung"] != gefunden["verteilung"]:
        nur_hier = set(erwartet["verteilung"]) - set(gefunden["verteilung"])
        raise LadeFehler(
            f"Die Verteilung ueber Stadt, mapping_status und geo_status "
            f"stimmt nicht: {sorted(nur_hier)[:3]} fehlen in ClickHouse.")


# --------------------------------------------------------------------------
# Der Ablauf
# --------------------------------------------------------------------------


class Klient(Protocol):
    """So wenig, wie dieses Modul von ClickHouse braucht.

    Damit laeuft der Test mit einem Dictionary statt einer Datenbank - genau
    wie ``FakeS3Client`` in ``storage``.
    """

    def befehl(self, sql: str) -> None: ...
    def abfrage(self, sql: str) -> list[tuple]: ...


def aktuelles_release(datenwurzel: Path) -> tuple[str, Path]:
    zeiger = datenwurzel / "releases" / "AKTUELL.json"
    if not zeiger.is_file():
        raise LadeFehler(f"{zeiger} fehlt - erst 'run_all --release' laufen lassen")
    kennung = json.loads(zeiger.read_text(encoding="utf-8"))["release_id"]
    parquet = datenwurzel / "releases" / f"release={kennung}" / QUELLE_IM_RELEASE
    if not parquet.is_file():
        raise LadeFehler(f"{parquet} fehlt - Release {kennung} liegt nicht lokal")
    return kennung, parquet


def lade(klient: Klient, kennung: str, parquet: Path, *, s3_url: str,
         s3_schluessel: str, s3_geheim: str) -> dict[str, Any]:
    """Anlegen, fuellen, pruefen, umlegen - in dieser Reihenfolge."""
    ziel = tabellenname(kennung)
    felder = spalten(parquet)

    klient.befehl(ddl(ziel, felder))
    klient.befehl(einfuegen_aus_s3(ziel, s3_url, s3_schluessel, s3_geheim))

    fragen = abgleich_clickhouse(ziel)
    gefunden = {
        "zeilen": klient.abfrage(fragen["zeilen"])[0][0],
        "schluessel": klient.abfrage(fragen["schluessel"])[0][0],
        "verteilung": [tuple(z) for z in klient.abfrage(fragen["verteilung"])],
    }
    erwartet = abgleich_release(parquet)
    vergleiche(erwartet, gefunden)          # wirft, bevor irgendetwas sichtbar wird

    klient.befehl(sicht_umlegen(ziel))
    return {"release_id": kennung, "tabelle": ziel, "spalten": len(felder),
            **{k: erwartet[k] for k in ("zeilen", "schluessel")}}


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--data-root", type=Path, default=None,
                          help="lokale Wurzel; ohne Angabe entscheidet die Ablage")
    zerleger.add_argument("--trocken", action="store_true",
                          help="nur die Anweisungen zeigen, nichts ausfuehren")
    args = zerleger.parse_args(argv)

    # Der Pfad geht durch die Ablage und nicht an ihr vorbei: Im s3-Modus gibt
    # es keinen lokalen Bestand, und nur sie weiss, wo die Wurzel liegt. Ein
    # Waechter in tests/storage/test_pipelines_hybrid.py haelt das fest.
    from storage import for_root

    kennung, parquet = aktuelles_release(for_root(args.data_root).local_root)
    ziel = tabellenname(kennung)
    felder = spalten(parquet)

    if args.trocken:
        print(ddl(ziel, felder))
        print()
        print(einfuegen_aus_s3(ziel, f"…/release={kennung}/{QUELLE_IM_RELEASE}",
                               "$S3_ACCESS_KEY", "$S3_SECRET_KEY"))
        print()
        print(sicht_umlegen(ziel))
        return 0

    raise SystemExit(
        "Ohne --trocken braucht es einen ClickHouse-Klienten. "
        "Er wird gereicht, nicht hier gebaut: 'lade(klient, …)'."
    )


if __name__ == "__main__":
    raise SystemExit(main())
