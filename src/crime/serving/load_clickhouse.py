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
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, Protocol


DATENWURZEL = Path("data")

#: Der Port aus ``docker-compose.yml`` - verschoben, weil 8123 belegt sein
#: kann, und an 127.0.0.1 gebunden, weil dieser Dienst keine Anmeldung hat.
STANDARD_URL = "http://localhost:18123"

#: Wo die Releases im Container liegen. ``file()`` loest relativ zu
#: ``user_files`` auf, deshalb steht hier kein fuehrender Schraegstrich.
EINGEHAENGT = "releases"


# --------------------------------------------------------------------------
# Die Entscheidungen. Alles hier ist Abwaegung, keine Ableitung.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ziel:
    """Was fuer eine Tabelle entschieden werden muss, damit sie in ClickHouse taugt."""

    name: str
    #: ClickHouse legt die Zeilen physisch so ab und baut darauf seinen duennen
    #: Index. Ein Filter auf ein Praefix davon liest ein paar Bloecke, jeder
    #: andere die ganze Tabelle.
    sortierung: tuple[str, ...]
    #: Wogegen der Abgleich seine Eindeutigkeit zaehlt. Mehrspaltig, wo der
    #: Schluessel zusammengesetzt ist: ``dim_city_day`` haette ueber ``date``
    #: allein nur 366 statt 732 gezaehlt und die Haelfte nicht geprueft.
    schluessel: tuple[str, ...]
    #: Spalten, ueber die der Abgleich zusaetzlich gruppiert. Bewusst nur Text
    #: und ganze Zahlen: Ein Wahrheitswert kommt aus DuckDB als ``True`` und
    #: aus ClickHouse als ``1``, und der Vergleich schlaege an, ohne dass
    #: etwas fehlt.
    verteilung: tuple[str, ...]
    partition: str | None = None
    niedrige_kardinalitaet: frozenset[str] = frozenset()

    @property
    def quelle_im_release(self) -> str:
        return f"gold/dataset={self.name}/part-0001.parquet"


#: ``LowCardinality`` lohnt erst, wenn viele Zeilen wenige Werte wiederholen.
#: Bei 85 Zeilen (dim_offense), 366 (dim_date) oder 732 (dim_city_day) ist das
#: Woerterbuch teurer als der Text - deshalb tragen nur die beiden grossen
#: Tabellen welche.
ZIELE: tuple[Ziel, ...] = (
    Ziel(
        name="fact_offense",
        # Naheliegend waere ``(reporting_city, date, nibrs_code)`` gewesen -
        # Stadt, Zeitraum, Delikt ist die Frage des Dashboards. ``nibrs_code``
        # traegt aber drei NULL (die unmapped-Zeilen aus Chicago), und ein
        # nullbarer Sortierschluessel verlangt ``allow_nullable_key``. Drei
        # Zeilen von 345'073 sind diesen Schalter nicht wert.
        sortierung=("reporting_city", "date"),
        schluessel=("offense_id",),
        verteilung=("reporting_city", "mapping_status", "geo_status"),
        # Ein Jahrgang braucht das nicht. Kommt der zweite dazu, kann
        # ClickHouse ganze Monate ueberspringen, statt sie zu lesen.
        partition="toYYYYMM(date)",
        # Gemessen am Jahrgang 2024: reporting_city 2, mapping_status 4,
        # geo_status 4, nibrs_family 25, nibrs_code 59, source_offense_code
        # 429, tract_geoid 1'146 verschiedene Werte. Oberhalb von rund
        # zehntausend kippt der Vorteil - offense_id (345'073) gehoert deshalb
        # nicht dazu, obwohl es verlockend aussieht.
        niedrige_kardinalitaet=frozenset({
            "reporting_city", "nibrs_code", "nibrs_family", "tract_geoid",
            "source_offense_code", "mapping_status", "geo_status"}),
    ),
    Ziel(
        name="dim_offense",
        sortierung=("nibrs_code",),
        schluessel=("nibrs_code",),
        verteilung=("nibrs_group", "crime_against"),
    ),
    Ziel(
        name="dim_tract",
        sortierung=("geoid",),
        schluessel=("geoid",),
        # Nicht ueber ``city``: Das traegt bei 5'227 der 6'282 Tracts NULL, und
        # wie zwei Engines NULL sortieren, ist nichts, worauf ein Nachweis
        # ruhen sollte.
        verteilung=("state_fips", "county_fips"),
        niedrige_kardinalitaet=frozenset({
            "city", "city_geoid", "state_fips", "state_name", "county_fips"}),
    ),
    Ziel(
        name="dim_date",
        sortierung=("date",),
        schluessel=("date",),
        verteilung=("quarter", "month"),
    ),
    Ziel(
        name="dim_city_day",
        sortierung=("city", "date"),
        schluessel=("city", "date"),
        verteilung=("city", "station_id"),
    ),
)

NACH_NAME = {z.name: z for z in ZIELE}


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
    "list<element: string>": "Array(String)",
}

#: ClickHouse laesst diese Typen nicht in ``Nullable`` stehen. Beide Faelle
#: sehen im erzeugten Text voellig richtig aus und fallen erst der Datenbank
#: auf - deshalb stehen sie hier und nicht in einem Kommentar.
NICHT_NULLBAR = ("Array(",)


class LadeFehler(RuntimeError):
    """Etwas stimmt nicht - und dann wird nichts umgelegt."""


@dataclass(frozen=True)
class Spalte:
    name: str
    arrow: str
    nullable: bool
    ziel: str = "fact_offense"

    @property
    def clickhouse(self) -> str:
        grund = TYPEN.get(self.arrow)
        if grund is None:
            raise LadeFehler(
                f"Fuer {self.name} ({self.arrow}) ist kein ClickHouse-Typ "
                f"entschieden. Eintrag in TYPEN ergaenzen - geraten wird nicht."
            )
        klein = NACH_NAME[self.ziel].niedrige_kardinalitaet
        if self.name in klein and grund != "String":
            raise LadeFehler(
                f"{self.name} steht in niedrige_kardinalitaet, ist aber "
                f"{grund} - LowCardinality lohnt nur fuer String.")
        # Die Schachtelung ist nicht beliebig: ClickHouse verweigert
        # ``Nullable(LowCardinality(String))`` mit *Nested type cannot be
        # inside Nullable type*. Richtig herum ist LowCardinality aussen.
        if self.nullable:
            if grund.startswith(NICHT_NULLBAR):
                raise LadeFehler(
                    f"{self.name} traegt NULL, aber ClickHouse laesst {grund} "
                    f"nicht in Nullable stehen.")
            grund = f"Nullable({grund})"
        if self.name in klein:
            grund = f"LowCardinality({grund})"
        return grund


# --------------------------------------------------------------------------
# Abgelesen: was im Release wirklich steht
# --------------------------------------------------------------------------


def spalten(parquet: Path, ziel: str = "fact_offense") -> list[Spalte]:
    """Die Spalten aus der Datei - nicht aus einer zweiten Liste.

    Die Spalten kommen aus ``storage.parquet_schema`` und nicht aus
    ``DESCRIBE``: DuckDB ergaenzt aus dem Pfad ``dataset=fact_offense`` eine
    Hive-Spalte ``dataset``, die in der Datei gar nicht steht. Sie gehoert
    nicht in die Zieltabelle - die Begruendung steht in ``storage.parquet``.

    **Nullbarkeit wird gezaehlt, nicht geglaubt.** Parquet markiert jede Spalte
    als nullbar, auch wo nie ein NULL steht - uebernaehme man das, waeren alle
    22 Spalten ``Nullable``, obwohl es nur acht sind. Das kostet ein Byte je
    Zeile und Spalte und blockiert Optimierungen, ohne irgendetwas auszusagen.
    """
    from storage.duckdb import verbinde

    from storage import parquet_schema

    schema = parquet_schema(parquet)
    namen = [f.name for f in schema]
    teile = ", ".join(
        f'count(*) FILTER (WHERE "{n}" IS NULL)' for n in namen)
    con = verbinde()
    try:
        leer = con.execute(
            f"SELECT {teile} FROM read_parquet('{parquet}')").fetchone()
    finally:
        con.close()
    return [Spalte(f.name, str(f.type), n > 0, ziel)
            for f, n in zip(schema, leer)]


def tabellenname(release_id: str, ziel: str = "fact_offense") -> str:
    """``2026-09-21T12-55-05Z`` -> ``fact_offense_20260921T125505Z``.

    ClickHouse-Bezeichner vertragen weder Bindestrich noch Doppelpunkt. Die
    Kennung bleibt trotzdem lesbar, und genau darum geht es: Wer die Tabelle
    sieht, weiss, aus welchem Release sie stammt.
    """
    return f"{ziel}_{re.sub(r'[^0-9A-Za-z]', '', release_id)}"


# --------------------------------------------------------------------------
# Die erzeugten Anweisungen. Reine Funktionen - pruefbar ohne ClickHouse.
# --------------------------------------------------------------------------


def ddl(tabelle: str, felder: list[Spalte], ziel: Ziel) -> str:
    """Die Anweisung - und die Zusicherung, dass der Schluessel traegt.

    Ein nullbarer Sortierschluessel ist in ClickHouse nur mit einem Schalter
    erlaubt. Statt ihn zu setzen, faellt hier der Bau: Wenn eine
    Schluesselspalte NULL bekommt, hat sich etwas in Gold geaendert, und das
    gehoert angesehen und nicht umschifft.

    **``OR REPLACE`` und nicht ``IF NOT EXISTS``.** Mit ``IF NOT EXISTS`` war
    ein zweiter Lauf kein zweiter Lauf, sondern ein zweites Einfuegen: Die
    Tabelle stand schon, der Insert lief noch einmal, und aus 345'073 Zeilen
    wurden 690'146. Aufgefallen ist das erst, als ein Lauf nach einem
    gescheiterten Abgleich wiederholt wurde - also genau dann, wenn man es am
    wenigsten gebrauchen kann. ClickHouse fuehrt ``CREATE OR REPLACE TABLE``
    atomar aus (Anlegen und Tauschen), die Sicht sieht also nie einen halben
    Stand.
    """
    nach_name = {s.name: s for s in felder}
    for name in (*ziel.sortierung, *ziel.schluessel):
        s = nach_name.get(name)
        if s is None:
            raise LadeFehler(f"{name} steht im Schluessel, aber nicht im Release")
        if s.nullable:
            raise LadeFehler(
                f"{name} traegt NULL und steht im Schluessel. Entweder die "
                f"Sortierung aendern oder klaeren, warum Gold dort NULL liefert.")
    zeilen = ",\n".join(f"    {s.name} {s.clickhouse}" for s in felder)
    teile = [f"CREATE OR REPLACE TABLE {tabelle} (\n{zeilen}\n)",
             "ENGINE = MergeTree"]
    if ziel.partition:
        teile.append(f"PARTITION BY {ziel.partition}")
    teile.append(f"ORDER BY ({', '.join(ziel.sortierung)})")
    return "\n".join(teile)


def einfuegen_aus_s3(tabelle: str, url: str, schluessel: str, geheim: str) -> str:
    """Ein einziger grosser Insert.

    ClickHouse legt je Insert einen Part an und verschmilzt sie im Hintergrund.
    Viele kleine Inserts laufen deshalb in *too many parts* - die Stapelung
    passiert hier also nicht, sondern wird vermieden.
    """
    return (f"INSERT INTO {tabelle} SELECT * FROM s3("
            f"'{url}', '{schluessel}', '{geheim}', 'Parquet')")


def einfuegen_aus_datei(tabelle: str, pfad: str) -> str:
    """Derselbe Insert, aber aus ``user_files`` statt aus S3.

    Fuer den Fall, dass ClickHouse das Release-Verzeichnis eingehaengt
    bekommt - beim Entwickeln, im Test, und ueberall dort, wo man den Weg
    beweisen will, ohne Zugangsdaten in eine Kommandozeile zu schreiben.
    """
    return f"INSERT INTO {tabelle} SELECT * FROM file('{pfad}', 'Parquet')"


def sicht_umlegen(tabelle: str, ziel: Ziel) -> str:
    """Der Zeigerwechsel. Bis hierher sieht niemand den neuen Stand."""
    return f"CREATE OR REPLACE VIEW {ziel.name} AS SELECT * FROM {tabelle}"


# --------------------------------------------------------------------------
# Der Abgleich: dieselbe Frage an beide Seiten
# --------------------------------------------------------------------------
# Eine Pruefsumme ueber den Inhalt waere staerker, laesst sich zwischen zwei
# Engines aber nicht ehrlich vergleichen - sie haengt an der Textdarstellung
# von Zahlen und Zeitstempeln. Diese drei Fragen haengen daran nicht.


def abgleich_clickhouse(tabelle: str, ziel: Ziel) -> dict[str, str]:
    spalten_liste = ", ".join(ziel.verteilung)
    nummern = ", ".join(str(i + 1) for i in range(len(ziel.verteilung)))
    return {
        "zeilen": f"SELECT count() FROM {tabelle}",
        "schluessel": (f"SELECT uniqExact({', '.join(ziel.schluessel)}) "
                       f"FROM {tabelle}"),
        "verteilung": (f"SELECT {spalten_liste}, count() FROM {tabelle} "
                       f"GROUP BY {nummern} ORDER BY {nummern}"),
    }


def abgleich_release(parquet: Path, ziel: Ziel) -> dict[str, Any]:
    from storage.duckdb import verbinde

    spalten_liste = ", ".join(ziel.verteilung)
    nummern = ", ".join(str(i + 1) for i in range(len(ziel.verteilung)))
    con = verbinde()
    quelle = f"read_parquet('{parquet}')"
    try:
        return {
            "zeilen": con.execute(f"SELECT count(*) FROM {quelle}").fetchone()[0],
            # Der Zeilenkonstruktor, damit auch ein zusammengesetzter
            # Schluessel zaehlt - ClickHouse nimmt dafuer mehrere Argumente.
            "schluessel": con.execute(
                f"SELECT count(DISTINCT ({', '.join(ziel.schluessel)})) "
                f"FROM {quelle}").fetchone()[0],
            "verteilung": [tuple(z) for z in con.execute(
                f"SELECT {spalten_liste}, count(*) FROM {quelle} "
                f"GROUP BY {nummern} ORDER BY {nummern}").fetchall()],
        }
    finally:
        con.close()


def _lesbar(wert: Any) -> str:
    """Tausendertrennung, wo sie geht - und sonst der Wert mit seinem Typ.

    ``f"{wert:,}"`` wirft bei allem, was keine Zahl ist. Die Meldung ueber
    einen Abgleichsfehler darf aber nicht selbst abstuerzen: Genau dann
    braucht sie jemand. Und wenn die Abweichung der **Typ** ist - ClickHouse
    gab "345073", das Release 345073 - dann ist das die Auskunft, die
    weiterhilft.
    """
    if isinstance(wert, int) and not isinstance(wert, bool):
        return f"{wert:,}"
    return f"{wert!r} ({type(wert).__name__})"


def vergleiche(erwartet: dict[str, Any], gefunden: dict[str, Any],
               ziel: Ziel = ZIELE[0]) -> None:
    """Weicht etwas ab, wird nichts umgelegt."""
    for name in ("zeilen", "schluessel"):
        if erwartet[name] != gefunden[name]:
            raise LadeFehler(
                f"{name}: Release sagt {_lesbar(erwartet[name])}, ClickHouse "
                f"{_lesbar(gefunden[name])} - die Sicht bleibt auf dem alten "
                f"Stand.")
    if erwartet["verteilung"] != gefunden["verteilung"]:
        nur_hier = set(erwartet["verteilung"]) - set(gefunden["verteilung"])
        raise LadeFehler(
            f"Die Verteilung ueber {', '.join(ziel.verteilung)} stimmt nicht: "
            f"{sorted(nur_hier, key=str)[:3]} fehlen in ClickHouse.")


# --------------------------------------------------------------------------
# Der Ablauf
# --------------------------------------------------------------------------


class Klient(Protocol):
    """So wenig, wie dieses Modul von ClickHouse braucht.

    Damit laeuft der Test mit einem Dictionary statt einer Datenbank - genau
    wie ``FakeS3Client`` in ``storage``.

    **Eine Zusage macht ``abfrage`` trotzdem:** Werte kommen mit ihrem Typ
    zurueck, nicht als geratener Text. Ein Klient, der TSV liest und alles
    Ziffernfoermige in ``int`` verwandelt, macht aus dem County ``'001'`` die
    Zahl ``1`` - und der Abgleich schlaegt an, obwohl nichts fehlt. Genau das
    ist beim ersten Laden von ``dim_tract`` passiert. ``FORMAT JSONCompact``
    liefert die Typen mit; TSV tut es nicht.
    """

    def befehl(self, sql: str) -> None: ...
    def abfrage(self, sql: str) -> list[tuple]: ...


class HttpKlient:
    """Der schmale Weg ueber die HTTP-Schnittstelle - ohne neue Abhaengigkeit.

    **Warum er jetzt hier steht.** Bis zum 1.10.2026 weigerte sich ``main``,
    ohne ``--trocken`` zu laufen, mit der Begruendung, ein Klient werde
    gereicht und nicht gebaut. Das war als Trennung gedacht, hiess praktisch
    aber: Das Modul konnte seine eigene Aufgabe nicht erledigen, und jeder
    Aufrufer schrieb sich denselben Klienten neu - der Test tat es, und
    ``pruefe_stand`` haette es wieder getan. ``load_elasticsearch`` hat es von
    Anfang an andersherum gehalten; diese Fassung zieht nach. Die Trennung
    bleibt, wo sie zaehlt: ``lade`` nimmt weiterhin **irgendeinen** Klienten
    entgegen und weiss nichts von HTTP.
    """

    def __init__(self, url: str = STANDARD_URL, datenbank: str = "default"):
        self.url = url.rstrip("/")
        self.datenbank = datenbank

    def _sende(self, sql: str) -> bytes:
        einstellungen = {
            "database": self.datenbank,
            # Ohne das liefert ClickHouse jede UInt64 als **Zeichenkette** -
            # JSON kann 64 Bit nicht verlustfrei als Zahl. ``count()`` kaeme
            # also als "345073" zurueck, DuckDB liefert 345073, und der
            # Abgleich schluege an, obwohl nichts fehlt. Dieselbe Falle wie
            # TSV, nur eine Ebene tiefer.
            "output_format_json_quote_64bit_integers": "0",
        }
        ziel = f"{self.url}/?{urllib.parse.urlencode(einstellungen)}"
        anfrage = urllib.request.Request(ziel, data=sql.encode("utf-8"),
                                         method="POST")
        try:
            with urllib.request.urlopen(anfrage, timeout=600) as antwort:
                return antwort.read()
        except urllib.error.HTTPError as fehler:
            text = fehler.read().decode("utf-8", "replace")[:600]
            raise LadeFehler(f"ClickHouse: HTTP {fehler.code}: {text}") from fehler

    def befehl(self, sql: str) -> None:
        self._sende(sql)

    def abfrage(self, sql: str) -> list[tuple]:
        # JSONCompact und nicht TSV: TSV liefert alles als Text, und wer ihn
        # zurueckraet, macht aus dem County '001' die Zahl 1. Genau das ist
        # beim ersten Laden von dim_tract passiert.
        roh = self._sende(sql + " FORMAT JSONCompact")
        return [tuple(zeile) for zeile in json.loads(roh)["data"]]


def aktuelles_release(datenwurzel: Path) -> tuple[str, Path]:
    """Die Kennung, auf die der Zeiger zeigt, und das Verzeichnis dazu."""
    zeiger = datenwurzel / "releases" / "AKTUELL.json"
    if not zeiger.is_file():
        raise LadeFehler(f"{zeiger} fehlt - erst 'run_all --release' laufen lassen")
    kennung = json.loads(zeiger.read_text(encoding="utf-8"))["release_id"]
    verzeichnis = datenwurzel / "releases" / f"release={kennung}"
    if not verzeichnis.is_dir():
        raise LadeFehler(f"Release {kennung} liegt nicht lokal: {verzeichnis}")
    return kennung, verzeichnis


def quelle(verzeichnis: Path, ziel: Ziel) -> Path:
    parquet = verzeichnis / ziel.quelle_im_release
    if not parquet.is_file():
        raise LadeFehler(f"{parquet} fehlt im Release")
    return parquet


def lade(klient: Klient, kennung: str, parquet: Path, *,
         einfuegen: Callable[[str], str],
         ziel: Ziel = ZIELE[0]) -> dict[str, Any]:
    """Anlegen, fuellen, pruefen, umlegen - in dieser Reihenfolge.

    ``einfuegen`` bekommt den Zieltabellennamen und liefert die
    Insert-Anweisung. Damit weiss dieser Ablauf nicht, ob die Daten aus S3
    oder aus einem eingehaengten Verzeichnis kommen - und muss es nicht.
    """
    tabelle = tabellenname(kennung, ziel.name)
    felder = spalten(parquet, ziel.name)

    klient.befehl(ddl(tabelle, felder, ziel))
    klient.befehl(einfuegen(tabelle))

    fragen = abgleich_clickhouse(tabelle, ziel)
    gefunden = {
        "zeilen": klient.abfrage(fragen["zeilen"])[0][0],
        "schluessel": klient.abfrage(fragen["schluessel"])[0][0],
        "verteilung": [tuple(z) for z in klient.abfrage(fragen["verteilung"])],
    }
    erwartet = abgleich_release(parquet, ziel)
    vergleiche(erwartet, gefunden, ziel)    # wirft, bevor etwas sichtbar wird

    klient.befehl(sicht_umlegen(tabelle, ziel))
    return {"release_id": kennung, "tabelle": tabelle, "spalten": len(felder),
            **{k: erwartet[k] for k in ("zeilen", "schluessel")}}


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--data-root", type=Path, default=None,
                          help="lokale Wurzel; ohne Angabe entscheidet die Ablage")
    zerleger.add_argument("--url", default=STANDARD_URL,
                          help=f"ClickHouse (Standard: {STANDARD_URL})")
    zerleger.add_argument("--trocken", action="store_true",
                          help="nur die Anweisungen zeigen, nichts ausfuehren")
    args = zerleger.parse_args(argv)

    # Der Pfad geht durch die Ablage und nicht an ihr vorbei: Im s3-Modus gibt
    # es keinen lokalen Bestand, und nur sie weiss, wo die Wurzel liegt. Ein
    # Waechter in tests/storage/test_pipelines_hybrid.py haelt das fest.
    from storage import for_root

    kennung, verzeichnis = aktuelles_release(for_root(args.data_root).local_root)

    if args.trocken:
        for ziel in ZIELE:
            tabelle = tabellenname(kennung, ziel.name)
            felder = spalten(quelle(verzeichnis, ziel), ziel.name)
            print(ddl(tabelle, felder, ziel))
            print()
            print(einfuegen_aus_s3(
                tabelle, f"…/release={kennung}/{ziel.quelle_im_release}",
                "$S3_ACCESS_KEY", "$S3_SECRET_KEY"))
            print()
            print(sicht_umlegen(tabelle, ziel))
            print("\n" + "-" * 72 + "\n")
        return 0

    klient = HttpKlient(args.url)
    for ziel in ZIELE:
        # Der Pfad, unter dem ClickHouse das Release sieht - nicht der, unter
        # dem wir es sehen. Die Einhaengung steht in docker-compose.yml.
        drinnen = (f"{EINGEHAENGT}/release={kennung}/{ziel.quelle_im_release}")
        ergebnis = lade(
            klient, kennung, quelle(verzeichnis, ziel),
            einfuegen=lambda tabelle, p=drinnen: einfuegen_aus_datei(tabelle, p),
            ziel=ziel)
        print(f"{ergebnis['tabelle']:<40} {ergebnis['zeilen']:>9,} Zeilen, "
              f"{ergebnis['spalten']} Spalten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
