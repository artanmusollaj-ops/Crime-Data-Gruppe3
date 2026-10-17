"""Baut die Silver-Tabelle ``crime_offense`` aus den Falldaten beider Staedte.

Eine Zeile je **Delikt**, nicht je Fall. Detroit liefert die 1:n-Beziehung
schon mit (``incident_entry_id`` je Delikt, ``report_number`` je Vorgang);
Chicago hat ``id`` als Deliktschluessel, ``case_number`` taugt nicht - 25
Nummern kommen mehrfach vor.

Aufruf aus dem Projekt-Root::

    python -m silver_pipeline.build_crime_offense

Dies ist die Tabelle, die den Staedtevergleich ueberhaupt erst traegt. Bis
hierher lagen die beiden Crosswalks als Referenzdateien herum, ohne dass sie
auf die Falldaten angewandt wurden; die vergleichbare Kategorie kam aus
Chicagos ``fbi_code`` (SRS) und Detroits ``offense_category`` - zwei
Hausklassifikationen, die niemand aufeinander abgebildet hat.

Was hier gedeutet wird und in Bronze bewusst nicht:

1. **Delikt statt Fall.** Chicagos Delta-Laeufe ueberlappen; dieselbe ``id``
   kommt in mehreren Laeufen vor. Behalten wird die Fassung mit dem
   juengsten ``updated_on``, nicht die zuerst gesehene.
2. **Zeitzonen.** Chicago liefert ``date`` als **Ortszeit ohne Angabe der
   Zone** - ``2024-01-01T00:56:00.000`` ist Chicagoer Lokalzeit. Detroit
   liefert Millisekunden seit Epoch, also einen echten UTC-Zeitpunkt. Ohne
   Umrechnung liegen die beiden Staedte auf verschiedenen Achsen und jeder
   Vergleich nach Tageszeit ist falsch. Die Tabelle fuehrt deshalb beides:
   ``occurred_at_utc`` fuer den Vergleich, ``occurred_at_local`` fuer die
   Frage, was in der Stadt Ortszeit war.
3. **NIBRS statt Hausklassifikation.** Chicagos ``iucr`` ueber
   ``config/iucr_nibrs_mapping.csv``, Detroits ``state_offense_code`` ueber
   ``config/micr_nibrs_mapping.csv``, beide auf die amtliche Codeliste
   ``config/nibrs_offense_codes_2025.csv``. Von dort kommen Gruppe und
   ``crime_against``.
4. **Raum.** Punkt-in-Polygon gegen ``silver/tract``, damit beide Staedte
   dieselbe Raumeinheit tragen. Nicht verortete Faelle **bleiben** in der
   Tabelle und tragen ``located = false``; sonst verschwaende die Verzerrung
   aus Absprache 2.4 unbemerkt.
5. **Zwei Koerner, beide fuer beide Staedte.** ``counts`` markiert je **Tat**
   eine Zeile (Detroits Anklagen fallen zusammen). ``counts_case`` markiert
   je **Fall** eine Zeile - die mit dem schwersten Delikt. Das braucht es,
   weil die Staedte verschieden zaehlen: Chicago fuehrt je Vorfall **ein**
   Delikt (259'272 Zeilen auf 259'243 Faelle; die einzigen Mehrfachzeilen
   sind Mordopfer, ein Datensatz je Opfer), Detroit fuehrt je Vorfall
   **jedes** Delikt (85'345 Taten auf 80'229 Faelle). Auf Tatebene zaehlt
   Detroit damit 6,4 Prozent, die Chicago nie zaehlt. Die Rangfolge steht in
   ``FALLKORN_RANG`` und gilt fuer beide Staedte gleich - eine Regel nur fuer
   eine Stadt waere die naechste Schieflage.

**Was diese Tabelle nicht tut:** Sie wirft nichts weg. Weder unverortete
Faelle noch solche ohne NIBRS-Zuordnung noch Detroits ``UNFOUNDED``-Faelle.
Alle drei sind gekennzeichnet, damit eine Auswertung sie bewusst ein- oder
ausschliessen kann.

Zu den zwei Zeitzonen-Randfaellen, und was von ihnen heute **nicht** geprueft
wird:

*Die Stunde, die es nicht gibt.* Beim Wechsel zur Sommerzeit (Chicago,
10.3.2024 zwischen 02:00 und 03:00) rechnet DuckDB die Ortszeit als
Winterzeit um. Im Jahrgang 2024 nennt keine Quellzeile eine solche Ortszeit.

*Die Stunde, die es zweimal gibt.* Beim Wechsel zurueck (3.11.2024 zwischen
01:00 und 02:00) ist die Ortszeit mehrdeutig; DuckDB waehlt eine der beiden
Moeglichkeiten. **48 Chicagoer Zeilen** liegen dort.

Beide Faelle werden **je Zeile ausgewiesen**: ``local_time_nonexistent`` und
``local_time_ambiguous``, und ``reconcile`` zaehlt sie je Stadt ins Manifest.
Fuer Detroit sind beide immer falsch - die Quelle liefert Millisekunden seit
Epoch, also einen Zeitpunkt, und aus dem entsteht die Ortszeit. Mehrdeutig
wird es erst, wenn eine Quelle Wanduhrzeit ohne Zone liefert.

Erkannt wird ohne Wissen ueber Wechseldaten: Hin und zurueck gerechnet muss
dieselbe Ortszeit herauskommen, sonst gab es sie nicht; fuehrt eine Stunde
davor oder danach auf dieselbe Ortszeit, gab es sie zweimal.

Bis zum 16.9.2026 geschah beides stillschweigend, und ein frueherer Stand
dieses Docstrings behauptete faelschlich, ``reconcile`` zaehle die Faelle.
Gemessen und aufgeschrieben ist der Weg dorthin in
``notebooks/36_hypothesen.ipynb`` unter H3.
"""

from __future__ import annotations

import argparse
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from typing import Any, NamedTuple

import duckdb

from manifeste import (Lauf, code_stand, eingabe_abdruck, referenz,
                       referenzdatei)
from storage import StorageError, for_root
from storage.duckdb import grenzen
from silver_pipeline import (
    BRONZE_LAYER,
    PARQUET_FILE,
    SILVER_LAYER,
    TransformError,
    connect,
    publish,
    schema_of,
)


LOG = logging.getLogger("build_crime_offense")

TABLE = "crime_offense"

# Der Deutungsvertrag: Was diese Tabelle bedeutet - Granularität, Regeln, Spalten -
# nicht, wie der Code sie baut. Steigt die Zahl, sind aeltere Staende anders
# zu lesen. Jede Erhoehung gehoert in AENDERUNGEN.md, siehe
# "Vertragsversionen"; ein Test prueft das.
CONTRACT_VERSION = 3


CHICAGO = "chicago"
DETROIT = "detroit"
# Der Verzeichnisname unter bronze/. Er folgt seit dem 12.9. demselben Muster
# wie Chicagos - sprechender Partitionsschluessel statt blossem Namen, damit
# beide Staedte in einer Auflistung gleich aussehen.
DETROIT_BRONZE = f"city={DETROIT}"

# Ortszeit der beiden Staedte. Chicago liefert Lokalzeit ohne Zonenangabe,
# Detroit einen UTC-Zeitpunkt - beide brauchen ihre Zone, aber fuer
# entgegengesetzte Richtungen.
TIMEZONES = {CHICAGO: "America/Chicago", DETROIT: "America/Detroit"}

CONFIG_DIR = "config"
IUCR_MAPPING = "iucr_nibrs_mapping.csv"
MICR_MAPPING = "micr_nibrs_mapping.csv"
NIBRS_CODES = "nibrs_offense_codes_2025.csv"

TRACT_TABLE = "dataset=tract"

# Detroit fuehrt zurueckgezogene Faelle weiter und markiert sie im Status.
UNFOUNDED = "UNFOUNDED"

# Wie gut ist eine NIBRS-Zuordnung belegt? ``nibrs_match`` sagt, *woher* sie
# kommt; ``mapping_status`` fasst das zu der Frage zusammen, die eine
# Auswertung stellt: **Darf ich diese Zeile mit der anderen Stadt
# vergleichen?**
#
#   exact         ein amtliches Dokument sagt, dass dieser Code so abgebildet
#                 wird - die Codeliste selbst, das MICR-Handbuch, die Liste
#                 der Arrest Charges, Anhang F
#   ambiguous     wir haben entschieden, weil die Quellen auseinandergingen
#                 oder schwiegen. Chicago fuehrt 0760 als *Burglary from Motor
#                 Vehicle*, NIBRS zaehlt das Eindringen in ein Fahrzeug als
#                 23F Theft from Motor Vehicle - beides vertretbar, aber es
#                 ist eine Entscheidung und keine Ableitung
#   fallback_90Z  die Zuordnung existiert und fuehrt auf den Auffangcode. Ein
#                 gueltiger Code, fuer einen Deliktvergleich aber wertlos
#   unmapped      kein Code
#
# Eine neue Herkunft darf **nicht** stillschweigend durchgehen - sonst waechst
# oder schrumpft die Vergleichbarkeit, ohne dass jemand hingesehen hat.
# ``reconcile`` laesst den Bau deshalb bei einem unbekannten Wert scheitern.
MAPPING_STATUS = {
    "nibrs_definition": "exact",
    "micr_manual_1110_2024": "exact",
    "micr_arrest_charge_1110_2024": "exact",
    "appendix_f_2009": "exact",
    "nibrs_ermessen": "ambiguous",
    "detroit_charge_file_class": "ambiguous",
    "nibrs_auffang": "fallback_90Z",
}
AUFFANG_CODE = "90Z"

# Das Fallebene: je Fall zaehlt die Zeile mit dem schwersten Delikt. Die
# Reihenfolge ist die Hierarchieregel des UCR Handbook (FBI 2004, "Hierarchy
# Rule"), auf NIBRS-Codes uebersetzt: Toetung, Vergewaltigung, Raub, schwere
# Koerperverletzung, Einbruch, Diebstahl, Fahrzeugdiebstahl, Brandstiftung.
# Alles Uebrige dahinter - Personen vor Eigentum vor Gesellschaft, dann nach
# Code. Fuer Chicago entscheidet die Liste faktisch nie (Mehrfachzeilen sind
# Mordopfer mit gleichem Code), fuer Detroit in 4'576 Faellen.
FALLKORN_RANG: tuple[str, ...] = (
    "09A", "09B", "11A", "11B", "11C", "120", "13A", "220",
    "23A", "23B", "23C", "23D", "23E", "23F", "23G", "23H", "240", "200",
)
CRIME_AGAINST_RANG = {"Person": 1, "Property": 2, "Society": 3}


class Source(NamedTuple):
    """Ein Bronze-Bestand, aus dem die Tabelle entsteht."""

    city: str
    paths: list[str]   # lokal oder s3://, siehe storage.resolve_read_path
    run_ids: list[str]
    row_count: int
    reader: str = "read_parquet"
    format: str = "PARQUET"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baut die Silver-Tabelle crime_offense aus beiden Staedten."
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)",
    )
    parser.add_argument(
        "--config-root",
        type=Path,
        default=Path(CONFIG_DIR),
        help="Verzeichnis der Referenztabellen (Vorgabe: config)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def table_dir(data_root: Path) -> Path:
    return data_root / SILVER_LAYER / f"dataset={TABLE}"


# ---------------------------------------------------------------------------
# Quellen finden
# ---------------------------------------------------------------------------


def ab_dem_juengsten_vollabzug(laeufe: list[Lauf], stadt: str) -> list[Lauf]:
    """Je Jahrgang: der juengste Vollabzug und was danach kam.

    **Warum nicht alle Laeufe.** Bis zum 17.10.2026 las dieses Modul jeden
    vollstaendigen Lauf und entdoppelte je ``id`` nach dem juengsten
    ``updated_on``. Eine Zeile, die die Quelle **zurueckgezogen** hat, taucht
    danach nicht mehr auf - sie bekommt aber auch kein neues ``updated_on``.
    Im Topf aus allen Laeufen bleibt also genau eine Fassung von ihr, die alte
    aus dem ueberholten Vollabzug, und die gewinnt, weil sie keinen
    Konkurrenten hat.

    Die Auskunft *"diese id war in Lauf A und ist in Lauf B nicht mehr"*
    existiert nur **zwischen** den Laeufen. Der ``UNION`` wirft sie weg, bevor
    irgendeine Frage gestellt wird.

    **Gemessen am 17.10.2026 auf srv01:** 89 Chicago-Zeilen hatten ihren
    Jahrgang verlassen, und **alle 89** standen weiter in ``crime_offense`` -
    2026 allein 80. Und es konnte nur wachsen: Die Tabelle gewinnt Zeilen,
    verliert aber nie welche. Dabei *erkannte* die Strecke das Verschwinden
    laengst - ``silver/source_change`` schreibt es als ``art =
    verschwunden`` auf. Zwei Tabellen derselben Schicht, aus demselben Lauf,
    sagten Verschiedenes.

    **Die Regel.** Bei einem Vollabzug sagt die Quelle: das ist der ganze
    Jahrgang. Abwesenheit heisst dort *nicht mehr in diesem Jahrgang*. Also
    gilt je Stadt und Jahrgang der juengste Vollabzug als Boden; was darunter
    liegt, ist ueberholt. Die Laeufe danach - Deltas wie spaetere Vollabzuege -
    kommen dazu, denn sie ergaenzen und aktualisieren.

    **Umdatierung ist keine Loeschung, und das loest sich von selbst.** Ein
    Datensatz, dessen Datum die Quelle in ein anderes Jahr korrigiert,
    verlaesst das Fenster seines alten Jahrgangs und erscheint im neuen. Weil
    die Regel *je Jahrgang* greift, kommt er ueber den Vollabzug seines neuen
    Jahrgangs herein und bleibt erhalten. Von den 89 gemessenen Faellen waren
    5 solche; deshalb steht in Detroits Manifest zu Recht
    ``captures_source_deletions: False`` - *ein* Jahrgang allein kann die
    beiden Faelle nicht unterscheiden, der Blick ueber alle Jahrgaenge kann es.

    **Ein Jahrgang ohne Vollabzug behaelt alle seine Laeufe.** Besser geht es
    dann nicht: Ohne Schnappschuss gibt es keinen Boden, und Deltas allein
    sagen nichts ueber Abwesenheit. Gemeldet wird es, damit es nicht still
    bleibt.
    """
    je_jahr: dict[str, list[Lauf]] = {}
    for lauf in laeufe:
        je_jahr.setdefault(lauf.jahrgang, []).append(lauf)

    behalten: list[Lauf] = []
    for jahr, gruppe in sorted(je_jahr.items()):
        geordnet = sorted(gruppe, key=lambda lauf: lauf.begonnen_um)
        boden = next((lauf for lauf in reversed(geordnet)
                      if lauf.vollabzug), None)
        if boden is None:
            LOG.warning(
                "%s %s: kein Vollabzug, alle %d Laeufe werden gelesen - "
                "zurueckgezogene Zeilen sind so nicht erkennbar",
                stadt, jahr or "ohne Jahrgang", len(geordnet))
            behalten.extend(geordnet)
            continue
        ab = [lauf for lauf in geordnet
              if lauf.begonnen_um >= boden.begonnen_um]
        if len(ab) < len(geordnet):
            LOG.info("%s %s: %d von %d Laeufen, ab dem Vollabzug vom %s",
                     stadt, jahr, len(ab), len(geordnet), boden.begonnen_um[:19])
        behalten.extend(ab)
    return behalten


def chicago_sources(data_root: Path) -> Source:
    """Je Jahrgang der juengste Vollabzug und was danach kam.

    Chicago laedt je Jahrgang einen Vollschnappschuss und danach Deltas. Nur
    den juengsten Lauf zu lesen hiesse, den Grossteil des Jahrgangs zu
    verlieren - anders als bei ``tract`` oder ``weather_day``, wo ein Lauf den
    ganzen Bestand traegt. **Alle** zu lesen heisst dagegen,
    zurueckgezogene Zeilen zu behalten; die Begruendung steht an
    ``ab_dem_juengsten_vollabzug``.
    """
    ablage = for_root(data_root)
    prefix = f"{BRONZE_LAYER}/city={CHICAGO}"
    pfade: list[str] = []
    laeufe: list[str] = []
    zeilen = 0
    gefunden = ablage.laeufe(
        prefix, "ingest_date=*/run_*/manifest.json", fehler=TransformError)
    for lauf in ab_dem_juengsten_vollabzug(gefunden, CHICAGO):
        if not ablage.exists(lauf.relativ, PARQUET_FILE):
            raise TransformError(f"Lauf ohne Parquet-Datei: {lauf.relativ}")
        pfade.append(ablage.resolve_read_path(lauf.relativ, PARQUET_FILE))
        laeufe.append(lauf.run_id)
        zeilen += lauf.zeilen

    if not pfade:
        raise TransformError(
            "Kein vollstaendiger Chicago-Bronze-Lauf. Zuerst die Ingestion starten."
        )
    return Source(CHICAGO, pfade, laeufe, zeilen)


def detroit_sources(data_root: Path) -> Source:
    """Detroits Bronze-Bestand: Laufverzeichnisse mit Parquet.

    ::

        bronze/city=detroit/full/year=2024/run_<uuid>/part-0001.parquet
        bronze/city=detroit/incremental/run_date=2026-09-11/run_<uuid>/...

    **Warum es keinen NDJSON-Rueckfall mehr gibt.** Bis zum 11.9. lag je Lauf
    eine NDJSON-Datei flach unter ``bronze/city=detroit/``, und diese Funktion las
    sie als Rueckfall mit. Das ist bewusst entfernt worden, denn jene Bestaende
    stammen aus der Zeit vor dem Zeitzonen-Fix: Ihr Jahresfenster war in UTC
    gezogen statt in Detroiter Ortszeit, weshalb sie 66 Faelle vom 31.12.2023
    enthalten und 56 vom Jahresende 2024 vermissen lassen. Ein Rueckfall haette
    diese Daten weiter eingelesen - mit einer Warnung im Log, die man
    ueberliest. Lieber ein klarer Fehler und ein neuer Full Load.
    """
    ablage = for_root(data_root)
    prefix = f"{BRONZE_LAYER}/{DETROIT_BRONZE}"
    wurzel = ablage.local_path(prefix)
    # Lokal mit Absicht, und die Bedingung sagt es: Der Griff haengt
    # an `liest_lokal and not remote`, laeuft also nur im
    # `local`-Modus. Dort ist ein fehlendes Verzeichnis die
    # verstaendlichste Fehlermeldung.
    if ablage.config.liest_lokal and not ablage.config.remote and not wurzel.exists():
        raise TransformError(f"Kein Detroit-Bronze-Verzeichnis: {wurzel}")

    pfade: list[str] = []
    laeufe: list[str] = []
    zeilen = 0
    # Versteckte .partial-Verzeichnisse und das SUCCESS-Vokabular kennt der
    # gemeinsame Leser; Detroit braucht hier keinen Sonderweg mehr.
    #
    # Dieselbe Regel wie bei Chicago, und aus demselben Grund: Detroits
    # ``FULL`` fragt den ganzen Jahrgang neu ab (``selection_basis:
    # INCIDENT_OCCURRENCE_TIME``), Abwesenheit heisst dort also "nicht mehr in
    # diesem Jahrgang". Der Jahrgang steht unter ``year``, nicht unter
    # ``event_year`` - ``Lauf.jahrgang`` kennt beide.
    gefunden = ablage.laeufe(prefix, fehler=TransformError)
    for lauf in ab_dem_juengsten_vollabzug(gefunden, DETROIT):
        datei = lauf.datei(PARQUET_FILE).name
        if not ablage.exists(lauf.relativ, datei):
            raise TransformError(f"Manifest ohne Parquet-Datei: {lauf.relativ}")
        pfade.append(ablage.resolve_read_path(lauf.relativ, datei))
        laeufe.append(lauf.run_id)
        zeilen += lauf.zeilen

    if not pfade:
        # Lokal mit Absicht: Dieser Zweig verbessert nur eine
        # Fehlermeldung - er sucht NDJSON-Reste aus der Zeit vor dem
        # Zeitzonen-Fix, die es nur lokal je gab. Im `s3`-Modus bleibt
        # er leer, und es gilt der allgemeine Fehler darunter.
        veraltet = sorted(wurzel.glob("*.ndjson")) if wurzel.exists() else []
        if veraltet:
            raise TransformError(
                f"Nur NDJSON-Bestaende aus der Zeit vor dem Zeitzonen-Fix "
                f"gefunden ({len(veraltet)} Datei(en) unter {wurzel}). Sie "
                "enthalten Faelle aus dem falschen Jahr und werden nicht mehr "
                "gelesen. Neu laden mit: python -m "
                "detroit_pipeline.extract_detroit --mode full --years 2024"
            )
        raise TransformError(
            "Kein erfolgreicher Detroit-Bronze-Lauf. Zuerst die Ingestion starten: "
            "python -m detroit_pipeline.extract_detroit --mode full --years 2024"
        )
    return Source(DETROIT, pfade, laeufe, zeilen, "read_parquet", "PARQUET")


class TractQuelle(NamedTuple):
    """``silver/tract`` einer Vintage: woher gelesen wird, und welche Vintage."""

    pfad: str        # lokal oder s3://
    vintage: str     # etwa "vintage=2024"
    #: Der **Ablagepfad** des Tabellenverzeichnisses, etwa
    #: ``silver/dataset=tract/vintage=2024``. Ohne ihn liesse sich das
    #: Manifest jener Tabelle nicht ueber die Ablage lesen - und ``pfad``
    #: taugt dafuer nicht: Im ``s3``-Modus ist er eine Adresse, kein Pfad.
    #: Bis zum 17.10.2026 fehlte er, und die Folge steht an ``herkunft_von``.
    verzeichnis: str = ""

    def __str__(self) -> str:
        return self.pfad


def tract_source(data_root: Path) -> TractQuelle:
    """Die juengste Vintage von ``silver/tract``."""
    ablage = for_root(data_root)
    prefix = f"{SILVER_LAYER}/{TRACT_TABLE}"
    kandidaten = ablage.list_files(prefix, "vintage=*/" + PARQUET_FILE)
    if not kandidaten:
        raise TransformError(
            f"silver/tract fehlt unter {ablage.local_path(prefix)}. "
            "Zuerst 'python -m silver_pipeline.build_tract' laufen lassen."
        )
    rel = kandidaten[-1]
    return TractQuelle(ablage.resolve_read_path(rel), rel.split("/")[-2],
                       rel.rsplit("/", 1)[0])


# ---------------------------------------------------------------------------
# Die Abfrage
# ---------------------------------------------------------------------------


def sql_list(paths: list[str]) -> str:
    inhalt = ", ".join(f"'{p}'" for p in paths)
    return f"[{inhalt}]"


#: Die Zeilenordnung der geschriebenen Parquet-Datei - ``city`` plus
#: ``offense_id`` ist eindeutig, ``occurred_at_utc`` steht dazwischen, damit
#: die Datei nach Zeit geordnet liegt.
#:
#: **Warum sie hier steht und nicht als Schlusssortierung in der Abfrage.**
#: Ohne ``ordnung`` schreibt ``COPY`` die *physische* Ordnung der Tabelle, und
#: die haengt an ``threads`` und ``preserve_insertion_order`` - darum
#: veraenderten beide am 13.10.2026 die Parquet-Bytes und waren als Ausweg
#: gesperrt. Mit ``ordnung`` haengen die Bytes am Schluessel, und der Plan ist
#: frei.
ORDNUNG = "city, occurred_at_utc, offense_id"


def build_query(
    chicago: Source,
    detroit: Source,
    tract: TractQuelle,
    config_root: Path,
) -> tuple[list[tuple[str, str]], str]:
    """Beide Staedte, auf NIBRS gebracht und raeumlich verortet.

    Der Aufbau ist bewusst zweistufig: erst je Stadt eine Relation mit
    denselben Spalten, dann ein ``UNION ALL``. So bleibt sichtbar, welche
    Deutung je Stadt noetig ist - und das ist genau der Punkt, an dem beide
    Datensaetze sich unterscheiden.
    """
    iucr = config_root / IUCR_MAPPING
    micr = config_root / MICR_MAPPING
    codes = config_root / NIBRS_CODES

    # Die Einstufung kommt aus MAPPING_STATUS und nicht aus verstreuten
    # CASE-Zweigen: So steht sie an einer Stelle, und ein Test kann sie gegen
    # die Werte halten, die in den Crosswalks wirklich vorkommen.
    status_werte = ", ".join(
        f"('{herkunft}', '{stufe}')"
        for herkunft, stufe in sorted(MAPPING_STATUS.items())
    )
    rang_werte = ", ".join(
        f"('{code}', {rang})" for rang, code in enumerate(FALLKORN_RANG, 1)
    )
    gegen_werte = ", ".join(
        f"('{gegen}', {rang})" for gegen, rang in sorted(CRIME_AGAINST_RANG.items())
    )
    # **Stufe fuer Stufe, nicht als eine Anweisung.** Der Grund ist
    # gemessen: Als eine Anweisung braucht dieselbe Abfrage 896 MB und
    # starb auf ``srv01`` viermal daran ("failed to pin block"); gestuft
    # laeuft sie mit 256 MB durch (16.10.2026, 1,875 Mio. Zeilen). In einer
    # Anweisung ist jede Zwischenstufe gleichzeitig gepinnt, und deshalb
    # half auch kein Auslagerungsverzeichnis - DuckDB kann nicht ablegen,
    # was noch gebraucht wird.
    #
    # Die Namen sind dieselben wie vorher, als sie CTEs waren: Eine
    # spaetere Stufe, die ``bereinigt`` nennt, findet die Tabelle dieses
    # Namens. So blieb der SQL-Text Zeichen fuer Zeichen derselbe, und die
    # gebaute Datei ist byteweise dieselbe - das war die Gegenprobe.
    return [
        ('status',
         f"""
        SELECT * FROM (VALUES {status_werte}) AS s(nibrs_match, mapping_status)
    """),
        ('fallrang',
         f"""
        SELECT * FROM (VALUES {rang_werte}) AS r(nibrs_code, rang)
    """),
        ('gegen',
         f"""
        SELECT * FROM (VALUES {gegen_werte}) AS g(crime_against, rang)
    """),
        ('nibrs',
         f"""
        SELECT nibrs_code, nibrs_description, nibrs_group, crime_against
        FROM read_csv('{codes}', header = true, all_varchar = true)
    """),
        ('iucr_map',
         f"""
        SELECT iucr, ibr_code AS nibrs_code, match AS nibrs_match
        FROM read_csv('{iucr}', header = true, all_varchar = true)
        WHERE mapped = 'true'
    """),
        ('micr_map',
         f"""
        SELECT micr_code, nibrs_code, match AS nibrs_match,
               TRY_CAST(hierarchy AS INTEGER) AS hierarchy
        FROM read_csv('{micr}', header = true, all_varchar = true)
        WHERE mapped = 'true'
    """),
        ('tract',
         f"""
        SELECT geoid, ST_GeomFromWKB(geometry) AS geom
        FROM read_parquet('{tract}')
        WHERE geometry IS NOT NULL
    """),
        # Chicago: eine Zeile je id, die Fassung mit dem juengsten updated_on.
        ('chicago_roh',
         f"""
        SELECT * FROM {chicago.reader}({sql_list(chicago.paths)})
    """),
        ('chicago_eindeutig',
         """
        SELECT * FROM (
            SELECT *, row_number() OVER (
                PARTITION BY id
                ORDER BY TRY_CAST(updated_on AS TIMESTAMP) DESC NULLS LAST
            ) AS rang
            FROM chicago_roh
        ) WHERE rang = 1
    """),
        ('chicago_delikte',
         f"""
        SELECT
            '{CHICAGO}'                                    AS city,
            c.id                                           AS offense_id,
            nullif(trim(c.case_number), '')                AS event_id,
            -- date ist Ortszeit ohne Zonenangabe; erst die Zone macht daraus
            -- einen Zeitpunkt.
            CAST(timezone('{TIMEZONES[CHICAGO]}',
                 CAST(c.date AS TIMESTAMP)) AS TIMESTAMP)  AS occurred_at_utc,
            CAST(c.date AS TIMESTAMP)                      AS occurred_at_local,
            -- Die beiden Zeitzonen-Randfaelle, je Zeile beantwortet.
            -- Hin und zurueck: Kommt eine andere Ortszeit heraus, gab es die
            -- genannte nicht (Uhr vorgestellt).
            CAST(timezone('{TIMEZONES[CHICAGO]}',
                 timezone('{TIMEZONES[CHICAGO]}', CAST(c.date AS TIMESTAMP))
                 ) AS TIMESTAMP) <> CAST(c.date AS TIMESTAMP)
                                                           AS local_time_nonexistent,
            -- Eine Stunde vor oder nach dem gewaehlten Zeitpunkt fuehrt auf
            -- dieselbe Ortszeit: Dann gab es sie zweimal (Uhr zurueckgestellt).
            (CAST(timezone('{TIMEZONES[CHICAGO]}',
                  timezone('{TIMEZONES[CHICAGO]}', CAST(c.date AS TIMESTAMP))
                  - INTERVAL 1 HOUR) AS TIMESTAMP) = CAST(c.date AS TIMESTAMP)
             OR CAST(timezone('{TIMEZONES[CHICAGO]}',
                  timezone('{TIMEZONES[CHICAGO]}', CAST(c.date AS TIMESTAMP))
                  + INTERVAL 1 HOUR) AS TIMESTAMP) = CAST(c.date AS TIMESTAMP))
                                                           AS local_time_ambiguous,
            nullif(trim(c.iucr), '')                       AS source_offense_code,
            -- Chicago beschreibt ein Delikt in ZWEI Feldern, und keines
            -- traegt allein: ``description`` = '$500 AND UNDER' ist ohne
            -- ``primary_type`` = 'THEFT' bedeutungslos. Schlimmer, es ist
            -- mehrdeutig - 'SIMPLE' steht unter BATTERY, ASSAULT und
            -- STALKING. Seit Vertrag 3 werden beide Haelften gefuehrt,
            -- getrennt durch ': ' (kommt in keinem Quelltext vor).
            CASE
                WHEN nullif(trim(c.primary_type), '') IS NULL
                    THEN nullif(trim(c.description), '')
                WHEN nullif(trim(c.description), '') IS NULL
                    THEN trim(c.primary_type)
                WHEN trim(c.primary_type) = trim(c.description)
                    THEN trim(c.primary_type)
                ELSE trim(c.primary_type) || ': ' || trim(c.description)
            END                                            AS source_offense_description,
            m.nibrs_code                                   AS nibrs_code,
            m.nibrs_match                                  AS nibrs_match,
            TRY_CAST(c.latitude AS DOUBLE)                 AS latitude,
            TRY_CAST(c.longitude AS DOUBLE)                AS longitude,
            c.arrest                                       AS arrest,
            NULL                                           AS unfounded,
            -- Chicagos Zeile ist schon das Delikt; sie ist ihre eigene Gruppe
            -- und zaehlt immer.
            nullif(trim(c.id), '')                         AS offense_group_id,
            TRUE                                           AS counts,
            'eine_zeile_ist_ein_delikt'                    AS counts_reason
        FROM chicago_eindeutig c
        LEFT JOIN iucr_map m ON trim(c.iucr) = m.iucr
    """),
        # Detroit: eine Zeile je incident_entry_id.
        # Parquet und NDJSON tragen beide die Quellfelder unter 'attributes';
        # nur der Leseausdruck unterscheidet sich. Die Geometrie wird nicht
        # gebraucht, Detroit fuehrt die Koordinaten auch in den Attributen.
        #
        # **Die Typen werden hier gesetzt, nicht geerbt.** Bronze deutet
        # nichts: Ein Feld, das in einem Lauf durchgehend leer ist, kommt
        # untypisiert zurueck - pyarrow gibt ihm den Null-Typ, DuckDB
        # materialisiert ihn als INTEGER, und ``trim(INTEGER)`` bindet nicht.
        # Solange diese Stufe eine inline eingesetzte CTE war, wandelte der
        # Binder den untypisierten NULL stillschweigend; als eigene Tabelle
        # tut er es nicht mehr. Der Fehler waere also erst auf ``srv01``
        # aufgefallen, und zwar an einem Delta-Lauf ohne einen einzigen
        # ``case_status``. Gecastet werden nur die Textfelder und die
        # Koordinaten; die beiden Epochenfelder bleiben, wie die Quelle sie
        # fuehrt - ein Cast dort verschoebe Zeitpunkte.
        ('detroit_roh',
         f"""
        SELECT struct_pack(
            incident_entry_id   := CAST(attributes.incident_entry_id AS VARCHAR),
            report_number       := CAST(attributes.report_number AS VARCHAR),
            case_id             := CAST(attributes.case_id AS VARCHAR),
            state_offense_code  := CAST(attributes.state_offense_code AS VARCHAR),
            charge_description  := CAST(attributes.charge_description AS VARCHAR),
            offense_description := CAST(attributes.offense_description AS VARCHAR),
            case_status         := CAST(attributes.case_status AS VARCHAR),
            incident_occurred_at:= attributes.incident_occurred_at,
            updated_at          := attributes.updated_at,
            latitude            := CAST(attributes.latitude AS DOUBLE),
            longitude           := CAST(attributes.longitude AS DOUBLE)
        ) AS attributes
        FROM {detroit.reader}({sql_list(detroit.paths)})
    """),
        ('detroit_eindeutig',
         """
        SELECT * FROM (
            SELECT *, row_number() OVER (
                PARTITION BY attributes.incident_entry_id
                ORDER BY attributes.updated_at DESC NULLS LAST
            ) AS rang
            FROM detroit_roh
        ) WHERE rang = 1
    """),
        # Detroits Zeilen sind Anklagen, Chicagos sind Delikte. Ein Ueberfall mit
        # Schuessen und geraubtem Auto steht bei Detroit als fuenf Zeilen, bei
        # Chicago als eine. Wer beide Staedte summiert, ohne das zu wissen, zaehlt
        # Detroit zu hoch - und zwar um 3,8 Prozent.
        # 
        # Welches Feld die Tat traegt, sagen die Daten selbst: Bei Vorfaellen mit
        # mehreren Zeilen ist ``offense_description`` in 38,4 Prozent der Faelle
        # konstant, ``charge_description`` nur in 2,3 Prozent. Die Tat ist also
        # offense_description, die Anklage der Rest der Zeile.
        # 
        # Je (Vorfall, Tat) wird eine Zeile als die zaehlende markiert. Gewaehlt
        # wird die, deren Anklage die Tat selbst ist - dann traegt sie schon den
        # richtigen MICR-Code und es braucht keine Zuordnung ueber Text. Das
        # trifft auf 99,98 Prozent der Gruppen zu. Fuer die uebrigen 19
        # entscheidet die Hierarchie des MICR-Handbuchs, in der 1 Mord ist und 16
        # Sachbeschaedigung: Es gilt die schwerste Anklage.
        ('detroit_gewaehlt',
         """
        SELECT *, row_number() OVER (
            PARTITION BY trim(attributes.case_id),
                         coalesce(trim(attributes.offense_description), '')
            ORDER BY
                CASE WHEN trim(attributes.charge_description)
                        = trim(attributes.offense_description) THEN 0 ELSE 1 END,
                coalesce(mm.hierarchy, 99),
                trim(attributes.incident_entry_id)
        ) AS rang_in_tat
        FROM detroit_eindeutig d
        LEFT JOIN micr_map mm ON trim(d.attributes.state_offense_code) = mm.micr_code
    """),
        ('detroit_delikte',
         f"""
        SELECT
            '{DETROIT}'                                    AS city,
            nullif(trim(d.attributes.incident_entry_id), '') AS offense_id,
            nullif(trim(d.attributes.report_number), '')     AS event_id,
            -- Millisekunden seit Epoch sind bereits UTC.
            epoch_ms(d.attributes.incident_occurred_at)    AS occurred_at_utc,
            timezone('{TIMEZONES[DETROIT]}',
                epoch_ms(d.attributes.incident_occurred_at)
                AT TIME ZONE 'UTC')                        AS occurred_at_local,
            -- Detroit liefert Millisekunden seit Epoch, also einen Zeitpunkt.
            -- Die Ortszeit wird daraus abgeleitet und kann deshalb weder
            -- fehlen noch doppelt sein - die Mehrdeutigkeit entsteht erst,
            -- wenn eine Quelle Wanduhrzeit ohne Zone liefert.
            FALSE                                          AS local_time_nonexistent,
            FALSE                                          AS local_time_ambiguous,
            nullif(trim(d.attributes.state_offense_code), '') AS source_offense_code,
            nullif(trim(d.attributes.offense_description), '') AS source_offense_description,
            m.nibrs_code                                   AS nibrs_code,
            m.nibrs_match                                  AS nibrs_match,
            d.attributes.latitude                          AS latitude,
            d.attributes.longitude                         AS longitude,
            NULL                                           AS arrest,
            upper(coalesce(trim(d.attributes.case_status), '')) = '{UNFOUNDED}'
                                                           AS unfounded,
            -- Der Schluessel der Tat: Vorfall plus ihre Beschreibung.
            trim(d.attributes.case_id) || '|'
                || coalesce(trim(d.attributes.offense_description), '')
                                                           AS offense_group_id,
            d.rang_in_tat = 1                              AS counts,
            CASE
                WHEN d.rang_in_tat > 1 THEN 'weitere_anklage_zur_selben_tat'
                WHEN trim(d.attributes.charge_description)
                     = trim(d.attributes.offense_description)
                    THEN 'anklage_ist_die_tat'
                ELSE 'schwerste_anklage'
            END                                            AS counts_reason
        FROM detroit_gewaehlt d
        LEFT JOIN micr_map m ON trim(d.attributes.state_offense_code) = m.micr_code
    """),
        ('beide',
         """
        SELECT * FROM chicago_delikte
        UNION ALL
        SELECT * FROM detroit_delikte
    """),
        # Platzhalterkoordinaten sind keine Koordinaten. Detroit setzt 0/0,
        # Chicago laesst das Feld leer.
        ('bereinigt',
         """
        SELECT
            * EXCLUDE (latitude, longitude),
            CASE WHEN latitude BETWEEN -90 AND 90
                  AND NOT (latitude = 0 AND longitude = 0)
                 THEN latitude END                         AS latitude,
            CASE WHEN longitude BETWEEN -180 AND 180
                  AND NOT (latitude = 0 AND longitude = 0)
                 THEN longitude END                        AS longitude
        FROM beide
    """),
        # Der raeumliche Join bewusst als INNER JOIN auf die verortbaren Punkte
        # und erst danach zurueckverbunden. Als LEFT JOIN faellt DuckDB auf eine
        # verschachtelte Schleife zurueck - 348'000 Punkte gegen 6'282 Polygone,
        # und der Lauf endet nicht mehr. So bleibt es bei Sekundenbruchteilen.
        ('verortet',
         """
        SELECT b.city, b.offense_id, t.geoid
        FROM bereinigt b
        JOIN tract t ON ST_Within(ST_Point(b.longitude, b.latitude), t.geom)
        WHERE b.latitude IS NOT NULL AND b.longitude IS NOT NULL
    """),
        # Das Fallebene: unter den zaehlenden Zeilen eines Falls die mit dem
        # schwersten Delikt; bei gleichem Delikt (mehrere Opfer) die frueheste.
        # Eine Zeile ohne Fallnummer ist ihr eigener Fall. Codes ausserhalb der
        # Hierarchie ordnen sich hinter ihr ein, nach crime_against, dann Code;
        # ohne NIBRS-Code ganz hinten.
        ('fallebene',
         """
        SELECT b.city, b.offense_id,
               row_number() OVER (
                   PARTITION BY b.city, coalesce(b.event_id, b.offense_id)
                   ORDER BY coalesce(fr.rang, 100 + coalesce(g.rang, 9)),
                            b.nibrs_code NULLS LAST,
                            b.occurred_at_utc, b.offense_id
               ) AS rang_im_fall
        FROM bereinigt b
        LEFT JOIN nibrs n ON b.nibrs_code = n.nibrs_code
        LEFT JOIN fallrang fr ON b.nibrs_code = fr.nibrs_code
        LEFT JOIN gegen g ON n.crime_against = g.crime_against
        WHERE b.counts
    """),
    ], f"""

    SELECT
        b.city,
        b.offense_id,
        b.event_id,
        b.occurred_at_utc,
        b.occurred_at_local,
        CAST(b.occurred_at_local AS DATE)                  AS occurred_date_local,
        b.local_time_nonexistent,
        b.local_time_ambiguous,
        b.source_offense_code,
        b.source_offense_description,
        b.nibrs_code,
        n.nibrs_description,
        n.nibrs_group,
        n.crime_against,
        b.nibrs_match,
        b.nibrs_code IS NOT NULL                           AS nibrs_mapped,
        CASE
            WHEN b.nibrs_code IS NULL            THEN 'unmapped'
            WHEN b.nibrs_code = '{AUFFANG_CODE}' THEN 'fallback_90Z'
            ELSE s.mapping_status
        END                                                AS mapping_status,
        b.latitude,
        b.longitude,
        v.geoid                                            AS tract_geoid,
        v.geoid IS NOT NULL                                AS located,
        CAST(b.arrest AS BOOLEAN)                          AS arrest,
        CAST(b.unfounded AS BOOLEAN)                       AS unfounded,
        b.offense_group_id,
        CAST(b.counts AS BOOLEAN)                          AS counts,
        b.counts_reason,
        coalesce(f.rang_im_fall = 1, FALSE)                AS counts_case
    FROM bereinigt b
    LEFT JOIN nibrs n ON b.nibrs_code = n.nibrs_code
    LEFT JOIN status s ON b.nibrs_match = s.nibrs_match
    LEFT JOIN verortet v
      ON b.city = v.city AND b.offense_id = v.offense_id
    LEFT JOIN fallebene f
      ON b.city = f.city AND b.offense_id = f.offense_id
    """


# ---------------------------------------------------------------------------
# Pruefungen
# ---------------------------------------------------------------------------


def gegen_crosswalk(
    con: duckdb.DuckDBPyConnection, relation: str, config_root: Path
) -> dict[str, int]:
    """Traegt jede Zeile den Zielcode, den der Crosswalk **heute** nennt?

    **Warum das keine Tautologie ist.** Der Bau wendet den Crosswalk als Join
    an, das Ergebnis ist also im Moment des Baus konsistent. Wird die CSV
    danach geaendert und Silver nicht neu gebaut, driftet die Tabelle von ihrer
    Referenz weg - und nichts merkt es. Das Manifest haelt zwar die Pruefsumme
    der CSV fest, aber niemand vergleicht sie mit der Datei auf der Platte.

    Gefunden hat die Luecke Artans SQL-Pruefung M03 am 16.9.2026. Sie stand
    dort als Review-Abfrage; hier ist sie hart, weil ein Silver, das etwas
    anderes behauptet als sein Crosswalk, keine Grundlage fuer eine Zahl ist.

    Geprueft wird gegen dieselbe Auswahl, die der Bau benutzt: nur Zeilen mit
    ``mapped = 'true'``. Ein Code ohne aktivierte Zuordnung fuehrt in Silver zu
    ``nibrs_code IS NULL``, und genau das muss dann auch dastehen.
    """
    iucr = (config_root / IUCR_MAPPING).as_posix()
    micr = (config_root / MICR_MAPPING).as_posix()
    abweichungen = con.execute(f"""
        WITH referenz AS (
            SELECT '{CHICAGO}' AS city, iucr AS quellcode,
                   ibr_code AS nibrs_code, match AS nibrs_match
            FROM read_csv('{iucr}', header = true, all_varchar = true)
            WHERE mapped = 'true'
            UNION ALL
            SELECT '{DETROIT}', micr_code, nibrs_code, match
            FROM read_csv('{micr}', header = true, all_varchar = true)
            WHERE mapped = 'true'
        )
        SELECT s.city, count(*)
        FROM {relation} s
        LEFT JOIN referenz r
          ON r.city = s.city AND r.quellcode = trim(s.source_offense_code)
        WHERE s.nibrs_code IS DISTINCT FROM r.nibrs_code
           OR (r.nibrs_code IS NOT NULL
               AND s.nibrs_match IS DISTINCT FROM r.nibrs_match)
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    if abweichungen:
        wo = ", ".join(f"{stadt}: {n:,} Zeilen" for stadt, n in abweichungen)
        raise TransformError(
            f"Silver weicht vom heutigen Crosswalk ab ({wo}). Entweder wurde "
            "eine Mapping-CSV geaendert, ohne Silver neu zu bauen, oder die "
            "Zuordnung im Bau stimmt nicht mehr mit der Referenz ueberein. "
            "Neu bauen: python -m orchestration.run_all --ohne-ingestion"
        )
    return {"abweichungen": 0}


def reconcile(
    con: duckdb.DuckDBPyConnection,
    relation: str,
    chicago: Source,
    detroit: Source,
    config_root: Path | None = None,
) -> dict[str, Any]:
    """Was die Tabelle ueber sich selbst behaupten darf.

    Geprueft wird, was stillschweigend schieflaufen kann: ein doppelter
    Deliktschluessel, ein verlorener Fall, ein Zeitpunkt ausserhalb des
    Jahrgangs. Was nur unvollstaendig ist - fehlende Koordinaten, fehlende
    NIBRS-Zuordnung, eine mehrdeutige Ortszeit - wird gezaehlt und nicht
    beanstandet.
    """
    je_stadt = {
        stadt: {
            "rows": zeilen,
            "distinct_offense_id": eindeutig,
            "distinct_event_id": ereignisse,
            "nibrs_mapped": zugeordnet,
            "located": verortet,
            "without_timestamp": ohne_zeit,
            "counts": taten,
            "counts_case": faelle,
            "distinct_counted_event_id": gezaehlte_faelle,
            # Die beiden Zeitzonen-Randfaelle. Sie beanstanden nichts - sie
            # machen sichtbar, wie viele Zeilen eine Ortszeit tragen, die es
            # nicht oder zweimal gab. Ohne diese Zahl weiss niemand, ob eine
            # Stundenverteilung davon beruehrt ist.
            "local_time_nonexistent": nicht_existent,
            "local_time_ambiguous": mehrdeutig,
            # Die drei folgenden kamen am 17.9.2026 aus Artans SQL-Pruefungen
            # (S03, S04, Z05). S04 und Z05 brechen ab; S03 zaehlt nur.
            #
            # Warum S03 weich ist: ``event_id`` ist die Fallnummer der Quelle,
            # und die darf fehlen. Der Bau setzt sie dann auf NULL und behandelt
            # die Zeile ueber ``coalesce(event_id, offense_id)`` als ihren
            # eigenen Fall - sonst fielen alle Zeilen ohne Nummer in einen Fall
            # zusammen. Das ist Absicht und in
            # ``test_ohne_fallnummer_ist_die_zeile_ihr_eigener_fall`` festgehalten.
            #
            # Artans Sorge bleibt trotzdem berechtigt, nur trifft sie nicht den
            # Bau, sondern jede Abfrage von Hand: ``count(DISTINCT event_id)``
            # ueberspringt NULL stillschweigend. Deshalb steht die Zahl im
            # Manifest, statt den Bau abzubrechen. Heute ist sie null, weil
            # beide Quellen durchgehend Fallnummern liefern.
            "ohne_event_id": ohne_vorfall,
            "fall_ohne_tat": fall_ohne_tat,
            "without_zeitpunkt_unstimmig": unstimmig,
        }
        for stadt, zeilen, eindeutig, ereignisse, zugeordnet, verortet, ohne_zeit,
            taten, faelle, gezaehlte_faelle, nicht_existent, mehrdeutig,
            ohne_vorfall, fall_ohne_tat, unstimmig
        in con.execute(f"""
            SELECT city, count(*), count(DISTINCT offense_id),
                   count(DISTINCT event_id),
                   count(*) FILTER (nibrs_mapped),
                   count(*) FILTER (located),
                   count(*) FILTER (occurred_at_utc IS NULL),
                   count(*) FILTER (counts),
                   count(*) FILTER (counts_case),
                   count(DISTINCT coalesce(event_id, offense_id)) FILTER (counts),
                   count(*) FILTER (local_time_nonexistent),
                   count(*) FILTER (local_time_ambiguous),
                   count(*) FILTER (event_id IS NULL OR trim(event_id) = ''),
                   count(*) FILTER (counts_case AND NOT counts),
                   -- Hin und zurueck: Aus dem UTC-Zeitpunkt muss dieselbe
                   -- Ortszeit entstehen, die dasteht. Ausgenommen ist der
                   -- dokumentierte Fall einer Ortszeit, die es nie gab.
                   -- Eine Stunde im Jahr sieht die Pruefung nichts: Beim
                   -- Zurueckstellen der Uhr hat Detroit schon EST, Chicago
                   -- noch CDT, und beide Zonen fallen zusammen. Gemessen am
                   -- 17.9.2026 waren das 30 der 88'685 Detroit-Zeilen; ein
                   -- systematischer Zonenfehler faellt trotzdem 88'655-fach
                   -- auf.
                   count(*) FILTER (
                       NOT local_time_nonexistent
                       AND occurred_at_utc IS NOT NULL
                       AND occurred_at_local IS DISTINCT FROM CAST(timezone(
                           CASE city WHEN '{CHICAGO}' THEN '{TIMEZONES[CHICAGO]}'
                                     ELSE '{TIMEZONES[DETROIT]}' END,
                           occurred_at_utc AT TIME ZONE 'UTC') AS TIMESTAMP))
            FROM {relation} GROUP BY city ORDER BY city
        """).fetchall()
    }

    for stadt, zahlen in je_stadt.items():
        if zahlen["rows"] != zahlen["distinct_offense_id"]:
            raise TransformError(
                f"{stadt}: {zahlen['rows']} Zeilen, aber nur "
                f"{zahlen['distinct_offense_id']} verschiedene offense_id - "
                "die Granularität ist nicht ein Delikt je Zeile"
            )
        if zahlen["without_zeitpunkt_unstimmig"]:
            raise TransformError(
                f"{stadt}: {zahlen['without_zeitpunkt_unstimmig']} Zeilen, deren "
                "UTC-Zeitpunkt nicht zur Ortszeit passt. Entweder ist die "
                "Zeitzonenumrechnung gebrochen oder die Stadtzeitzone stimmt "
                "nicht mehr. Nicht existierende Ortszeiten sind hier bereits "
                "ausgenommen, die traegt local_time_nonexistent."
            )
        if zahlen["fall_ohne_tat"]:
            raise TransformError(
                f"{stadt}: {zahlen['fall_ohne_tat']} Zeilen zaehlen als Fall, "
                "aber nicht als Tat. Ein Fall besteht aus Taten; die Auswahl "
                "je Fall muss eine der zaehlenden Zeilen treffen."
            )
        if zahlen["without_timestamp"]:
            raise TransformError(
                f"{stadt}: {zahlen['without_timestamp']} Zeilen ohne Zeitpunkt"
            )
        # Das Fallebene ist genau dann richtig, wenn je Fall mit zaehlender
        # Zeile genau eine als counts_case markiert ist - nicht mehr, nicht
        # weniger. Eine Zeile, die nicht zaehlt, kann auch nicht je Fall zaehlen.
        if zahlen["counts_case"] != zahlen["distinct_counted_event_id"]:
            raise TransformError(
                f"{stadt}: {zahlen['counts_case']} Zeilen mit counts_case, aber "
                f"{zahlen['distinct_counted_event_id']} Faelle mit zaehlender "
                "Zeile - das Fallebene ist nicht eine Zeile je Fall"
            )

    # Eine neue Herkunft in einem Crosswalk darf nicht stillschweigend
    # durchrutschen: Die Zeile haette einen gueltigen NIBRS-Code und truege
    # trotzdem ein leeres ``mapping_status``. Wer danach filtert, verloere
    # sie - genau die Sorte Verlust, die diese Spalte verhindern soll.
    bekannt = ", ".join(repr(k) for k in sorted(MAPPING_STATUS))
    if config_root is not None:
        gegen_crosswalk(con, relation, config_root)

    unbekannt = con.execute(f"""
        SELECT nibrs_match, count(*) FROM {relation}
        WHERE nibrs_code IS NOT NULL AND nibrs_code <> '{AUFFANG_CODE}'
          AND (nibrs_match IS NULL OR nibrs_match NOT IN ({bekannt}))
        GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    if unbekannt:
        raise TransformError(
            "Unbekannte Herkunft der NIBRS-Zuordnung: "
            + ", ".join(f"{h} ({n} Zeilen)" for h, n in unbekannt)
            + ". In MAPPING_STATUS eintragen und dabei entscheiden, ob die "
            "Zuordnung belegt (exact) oder eine Entscheidung (ambiguous) ist."
        )

    # Chicagos Deltas ueberlappen; die Rohsumme ist deshalb groesser als die
    # Zeilenzahl. Kleiner darf sie nie sein - dann waere etwas verlorengegangen.
    if je_stadt.get(CHICAGO, {}).get("rows", 0) > chicago.row_count:
        raise TransformError(
            f"Chicago: {je_stadt[CHICAGO]['rows']} Zeilen aus "
            f"{chicago.row_count} Bronze-Zeilen - mehr Ergebnis als Quelle"
        )
    # Seit dem Parquet-Umbau kann auch Detroit mehrere Laeufe haben: ein Full
    # Load plus taegliche Nachlaeufe, die einander ueberlappen. Die Rohsumme ist
    # deshalb groesser oder gleich der Zeilenzahl - kleiner nie, dann waere
    # etwas verlorengegangen.
    if je_stadt.get(DETROIT, {}).get("rows", 0) > detroit.row_count:
        raise TransformError(
            f"Detroit: {je_stadt[DETROIT]['rows']} Zeilen aus "
            f"{detroit.row_count} Bronze-Zeilen - mehr Ergebnis als Quelle"
        )

    zeitraum = con.execute(
        f"SELECT min(occurred_at_utc), max(occurred_at_utc) FROM {relation}"
    ).fetchone()

    auffang = con.execute(
        f"SELECT count(*) FROM {relation} WHERE nibrs_code = '90Z'"
    ).fetchone()[0]

    return {
        "per_city": je_stadt,
        "rows": sum(z["rows"] for z in je_stadt.values()),
        "occurred_at_utc_min": str(zeitraum[0]),
        "occurred_at_utc_max": str(zeitraum[1]),
        "nibrs_fallback_90z": auffang,
    }


def comparability(con: duckdb.DuckDBPyConnection, relation: str) -> list[dict[str, Any]]:
    """Die Zahl, um derentwillen die Tabelle gebaut wurde.

    Fuer jeden NIBRS-Code, der in beiden Staedten vorkommt, die Fallzahlen -
    das erste Mal, dass beide Datensaetze dieselbe Sprache sprechen.
    """
    return [
        {
            "nibrs_code": code,
            "nibrs_description": text,
            "chicago": chi,
            "detroit": det,
        }
        for code, text, chi, det in con.execute(f"""
            SELECT nibrs_code, any_value(nibrs_description),
                   count(*) FILTER (city = '{CHICAGO}'),
                   count(*) FILTER (city = '{DETROIT}')
            FROM {relation}
            WHERE nibrs_code IS NOT NULL
            GROUP BY nibrs_code
            HAVING count(*) FILTER (city = '{CHICAGO}') > 0
               AND count(*) FILTER (city = '{DETROIT}') > 0
            ORDER BY count(*) DESC
            LIMIT 15
        """).fetchall()
    ]


# ---------------------------------------------------------------------------
# Manifest und Aufbau
# ---------------------------------------------------------------------------


def herkunft_von(
    chicago: Source, detroit: Source, tract: TractQuelle, config_root: Path,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Woraus diese Tabelle entstanden ist - vollstaendig genug zum Nachbauen.

    Die Bronze-Laeufe stehen namentlich da, seit es die Tabelle gibt. Neu
    seit dem 14.9. sind die beiden Glieder, die vorher nur Pfade waren: Die
    Crosswalks tragen ihre Pruefsumme (sie werden aus amtlichen PDFs erzeugt
    und koennen sich aendern, ohne dass der Pfad sich aendert), und
    ``silver/tract`` wird als **Referenz** genannt - mit Bauzeitpunkt,
    Eingabe-Abdruck und seiner eigenen Herkunft.
    """
    # **Zwei Fehler in zwei Zeilen, bis zum 17.10.2026.** Hier stand
    #
    #     tract_verzeichnis = Path(tract.pfad).parent
    #     if (tract_verzeichnis / "manifest.json").exists():
    #
    # und ``tract.pfad`` ist im ``s3``-Modus ``s3://urban-crime/...``.
    # ``Path`` macht aus dem Doppel-Slash ein einfaches, also war
    # ``.exists()`` **immer falsch** - das Manifest blieb leer, und mit ihm
    # fehlten Bauzeitpunkt, Eingabe-Abdruck und die eigene Herkunft von
    # ``silver/tract``. Die Herkunftskette von ``crime_offense`` nach Bronze
    # war auf ``srv01`` nicht nachvollziehbar, und das trifft genau die
    # Kernthese der Arbeit: Ein Manifest, das sagt "hier kommt es her" und es
    # nicht sagt, ist schlimmer als keines.
    #
    # Derselbe ``Path``-Griff verstuemmelte dazu den Pfad, der stattdessen
    # dastand: ``s3:/urban-crime/...`` mit einem Slash. Er sieht aus wie eine
    # Adresse und ist keine. Deshalb geht ``tract.pfad`` jetzt **als
    # Zeichenkette** in die Referenz - eine Ablageadresse ist kein
    # Dateisystempfad.
    # ``data_root`` muss **durchgereicht** werden. Hier stand kurzzeitig
    # ``for_root(None)``, und das nimmt die Standardwurzel ``data/`` statt der
    # des Aufrufers - lokal faellt das nicht auf, weil ``data/`` existiert.
    # Der Frischklon-Lauf ohne ``data/`` hat es gezeigt: 57 Tests rot,
    # ``FileNotFoundError`` auf einem Pfad, den kein Test gesetzt hat.
    ablage = for_root(data_root)
    tract_manifest = {}
    if tract.verzeichnis and ablage.exists(tract.verzeichnis, "manifest.json"):
        tract_manifest = ablage.tabellen_manifest(tract.verzeichnis)
    return {
        "chicago_bronze_runs": chicago.run_ids,
        "chicago_bronze_format": chicago.format,
        "detroit_bronze_runs": detroit.run_ids,
        "detroit_bronze_format": detroit.format,
        "silver_tract": referenz(tract.pfad, tract_manifest),
        "crosswalks": [
            referenzdatei(config_root / name)
            for name in (IUCR_MAPPING, MICR_MAPPING, NIBRS_CODES)
        ],
    }


def build_manifest(
    con: duckdb.DuckDBPyConnection,
    relation: str,
    chicago: Source,
    detroit: Source,
    tract: TractQuelle,
    config_root: Path,
    pruefung: dict[str, Any],
    data_root: Path | None = None,
) -> dict[str, Any]:
    herkunft = herkunft_von(chicago, detroit, tract, config_root, data_root)
    return {
        # Als einziges Manifest des Projekts fehlte hier lange der Status -
        # ausgerechnet bei der Tabelle, die den Vergleich traegt. Wer sie las,
        # konnte nicht wissen, ob der Bau durchgelaufen ist.
        "status": "complete",
        "contract_version": CONTRACT_VERSION,
        "code_version": code_stand(),
        "table": TABLE,
        "layer": SILVER_LAYER,
        # Je Stadt steht die Zahl unter "checks"; hier oben steht sie noch
        # einmal, weil jede andere Tabelle das auch tut. Wer Manifeste
        # einsammelt, soll nicht fuer eine davon einen Sonderweg brauchen.
        "row_count": sum(
            stadt["rows"] for stadt in pruefung["per_city"].values()
        ),
        "grain": "eine Anklage; je Tat ist eine Zeile mit counts markiert, "
                 "je Fall eine mit counts_case",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "tool": f"duckdb {duckdb.__version__} mit spatial und icu",
        "derived_from": herkunft,
        "input_fingerprint": eingabe_abdruck(herkunft),
        "timezones": TIMEZONES,
        "checks": pruefung,
        "comparable_offenses": comparability(con, relation),
        "schema": schema_of(con, relation),
    }


def build(data_root: Path, config_root: Path) -> Path:
    chicago = chicago_sources(data_root)
    detroit = detroit_sources(data_root)
    tract = tract_source(data_root)
    LOG.info(
        "Quellen: Chicago %d Laeufe, Detroit %d Laeufe, tract %s",
        len(chicago.paths), len(detroit.paths), tract.vintage,
    )

    # **Die Datenbank auf eine Datei, nicht in den Arbeitsspeicher.** Eine
    # ``:memory:``-Datenbank *ist* der Speicher: Die gebaute Tabelle und jede
    # Zwischenstufe liegen darin, und ``temp_directory`` erreicht sie nicht.
    # Zusammen mit der Stufung (siehe ``build_query``) sind das die zwei
    # Haelften derselben Messung - eine allein genuegt nicht.
    #
    # Die Datei liegt im Auslagerungsverzeichnis, wenn eines gesetzt ist: Auf
    # ``srv01`` ist das der Datentraeger, der dafuer Platz hat. Sie geht am
    # Ende mit; sie traegt nichts, was das Manifest nicht beschreibt.
    with tempfile.TemporaryDirectory(
            dir=grenzen().get("temp_directory") or None,
            prefix=".bau-crime_offense-") as bau:
        return _build(Path(bau) / "bau.duckdb", data_root, config_root,
                      chicago, detroit, tract)


def _build(datenbank: Path, data_root: Path, config_root: Path,
           chicago: Source, detroit: Source, tract: TractQuelle) -> Path:
    con = connect(spatial=True, datenbank=datenbank)
    try:
        # Ohne icu kennt DuckDB keine benannten Zeitzonen; ohne UTC als
        # Sitzungszone haengt das Ergebnis an der Zone des Rechners.
        try:
            con.execute("INSTALL icu")
            con.execute("LOAD icu")
        except duckdb.Error as error:
            raise TransformError(
                f"icu-Extension nicht verfuegbar, Zeitzonen nicht aufloesbar: {error}"
            ) from error
        con.execute("SET TimeZone='UTC'")

        # Erlaubt, seit ``ORDNUNG`` im ``COPY`` steht: Die Bytes haengen am
        # Schluessel, nicht daran, in welcher Ordnung die Zeilen in die
        # Tabelle gelangen. Vorher hat dieses Flag die Parquet-Bytes
        # veraendert (13.10.2026) und war deshalb gesperrt - obwohl DuckDB es
        # bei genau diesem Fehler selbst an zweiter Stelle vorschlaegt. Es
        # gilt nur fuer diese Verbindung; die uebrigen Bauten ruhen noch auf
        # der Einfuegeordnung.
        con.execute("SET preserve_insertion_order=false")

        stufen, schluss = build_query(chicago, detroit, tract, config_root)
        for name, abfrage in stufen:
            con.execute(f"CREATE TABLE {name} AS {abfrage}")
        con.execute(f"CREATE TABLE {TABLE} AS {schluss}")
        pruefung = reconcile(con, TABLE, chicago, detroit, config_root)
        manifest = build_manifest(
            con, TABLE, chicago, detroit, tract, config_root, pruefung,
            data_root,
        )
        ziel = publish(con, TABLE, table_dir(data_root), manifest,
                       ordnung=ORDNUNG)
        LOG.info("%s: %d Zeilen", ziel, pruefung["rows"])
    finally:
        con.close()
    # Erst nach Bau, Pruefung und Manifest - was hier ankommt, hat bestanden.
    for_root(data_root).publish_table(ziel)
    return ziel


def main() -> int:
    args = arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        build(for_root(args.data_root).local_root, args.config_root)
    except (TransformError, StorageError) as error:
        LOG.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
