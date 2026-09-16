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
from datetime import datetime, timezone
from pathlib import Path

from typing import Any, NamedTuple

import duckdb

from manifeste import code_stand, eingabe_abdruck, referenz, referenzdatei
from storage import StorageError, for_root
from silver_pipeline import (
    BRONZE_LAYER,
    PARQUET_FILE,
    SILVER_LAYER,
    TransformError,
    connect,
    publish,
    read_manifest,
    schema_of,
)


LOG = logging.getLogger("build_crime_offense")

TABLE = "crime_offense"

# Der Deutungsvertrag: Was diese Tabelle bedeutet - Granularität, Regeln, Spalten -
# nicht, wie der Code sie baut. Steigt die Zahl, sind aeltere Staende anders
# zu lesen. Jede Erhoehung gehoert in AENDERUNGEN.md, siehe
# "Vertragsversionen"; ein Test prueft das.
CONTRACT_VERSION = 2


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


def chicago_sources(data_root: Path) -> Source:
    """Alle vollstaendigen Chicago-Laeufe, nicht nur der juengste.

    Chicago laedt einen Vollschnappschuss und danach Deltas. Nur den
    juengsten Lauf zu lesen hiesse, den Grossteil des Jahrgangs zu verlieren -
    anders als bei ``tract`` oder ``weather_day``, wo ein Lauf den ganzen
    Bestand traegt.
    """
    ablage = for_root(data_root)
    prefix = f"{BRONZE_LAYER}/city={CHICAGO}"
    pfade: list[str] = []
    laeufe: list[str] = []
    zeilen = 0
    for lauf in ablage.laeufe(
        prefix, "ingest_date=*/run_*/manifest.json", fehler=TransformError
    ):
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
    if ablage.config.liest_lokal and not ablage.config.remote and not wurzel.exists():
        raise TransformError(f"Kein Detroit-Bronze-Verzeichnis: {wurzel}")

    pfade: list[str] = []
    laeufe: list[str] = []
    zeilen = 0
    # Versteckte .partial-Verzeichnisse und das SUCCESS-Vokabular kennt der
    # gemeinsame Leser; Detroit braucht hier keinen Sonderweg mehr.
    for lauf in ablage.laeufe(prefix, fehler=TransformError):
        datei = lauf.datei(PARQUET_FILE).name
        if not ablage.exists(lauf.relativ, datei):
            raise TransformError(f"Manifest ohne Parquet-Datei: {lauf.relativ}")
        pfade.append(ablage.resolve_read_path(lauf.relativ, datei))
        laeufe.append(lauf.run_id)
        zeilen += lauf.zeilen

    if not pfade:
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
    return TractQuelle(ablage.resolve_read_path(rel), rel.split("/")[-2])


# ---------------------------------------------------------------------------
# Die Abfrage
# ---------------------------------------------------------------------------


def sql_list(paths: list[str]) -> str:
    inhalt = ", ".join(f"'{p}'" for p in paths)
    return f"[{inhalt}]"


def build_query(
    chicago: Source,
    detroit: Source,
    tract: TractQuelle,
    config_root: Path,
) -> str:
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
    return f"""
    WITH status AS (
        SELECT * FROM (VALUES {status_werte}) AS s(nibrs_match, mapping_status)
    ),
    fallrang AS (
        SELECT * FROM (VALUES {rang_werte}) AS r(nibrs_code, rang)
    ),
    gegen AS (
        SELECT * FROM (VALUES {gegen_werte}) AS g(crime_against, rang)
    ),
    nibrs AS (
        SELECT nibrs_code, nibrs_description, nibrs_group, crime_against
        FROM read_csv('{codes}', header = true, all_varchar = true)
    ),
    iucr_map AS (
        SELECT iucr, ibr_code AS nibrs_code, match AS nibrs_match
        FROM read_csv('{iucr}', header = true, all_varchar = true)
        WHERE mapped = 'true'
    ),
    micr_map AS (
        SELECT micr_code, nibrs_code, match AS nibrs_match,
               TRY_CAST(hierarchy AS INTEGER) AS hierarchy
        FROM read_csv('{micr}', header = true, all_varchar = true)
        WHERE mapped = 'true'
    ),
    tract AS (
        SELECT geoid, ST_GeomFromWKB(geometry) AS geom
        FROM read_parquet('{tract}')
        WHERE geometry IS NOT NULL
    ),

    -- Chicago: eine Zeile je id, die Fassung mit dem juengsten updated_on.
    chicago_roh AS (
        SELECT * FROM {chicago.reader}({sql_list(chicago.paths)})
    ),
    chicago_eindeutig AS (
        SELECT * FROM (
            SELECT *, row_number() OVER (
                PARTITION BY id
                ORDER BY TRY_CAST(updated_on AS TIMESTAMP) DESC NULLS LAST
            ) AS rang
            FROM chicago_roh
        ) WHERE rang = 1
    ),
    chicago_delikte AS (
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
            nullif(trim(c.description), '')                AS source_offense_description,
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
    ),

    -- Detroit: eine Zeile je incident_entry_id.
    -- Parquet und NDJSON tragen beide die Quellfelder unter 'attributes';
    -- nur der Leseausdruck unterscheidet sich. Die Geometrie wird nicht
    -- gebraucht, Detroit fuehrt die Koordinaten auch in den Attributen.
    detroit_roh AS (
        SELECT attributes
        FROM {detroit.reader}({sql_list(detroit.paths)})
    ),
    detroit_eindeutig AS (
        SELECT * FROM (
            SELECT *, row_number() OVER (
                PARTITION BY attributes.incident_entry_id
                ORDER BY attributes.updated_at DESC NULLS LAST
            ) AS rang
            FROM detroit_roh
        ) WHERE rang = 1
    ),
    -- Detroits Zeilen sind Anklagen, Chicagos sind Delikte. Ein Ueberfall mit
    -- Schuessen und geraubtem Auto steht bei Detroit als fuenf Zeilen, bei
    -- Chicago als eine. Wer beide Staedte summiert, ohne das zu wissen, zaehlt
    -- Detroit zu hoch - und zwar um 3,8 Prozent.
    --
    -- Welches Feld die Tat traegt, sagen die Daten selbst: Bei Vorfaellen mit
    -- mehreren Zeilen ist ``offense_description`` in 38,4 Prozent der Faelle
    -- konstant, ``charge_description`` nur in 2,3 Prozent. Die Tat ist also
    -- offense_description, die Anklage der Rest der Zeile.
    --
    -- Je (Vorfall, Tat) wird eine Zeile als die zaehlende markiert. Gewaehlt
    -- wird die, deren Anklage die Tat selbst ist - dann traegt sie schon den
    -- richtigen MICR-Code und es braucht keine Zuordnung ueber Text. Das
    -- trifft auf 99,98 Prozent der Gruppen zu. Fuer die uebrigen 19
    -- entscheidet die Hierarchie des MICR-Handbuchs, in der 1 Mord ist und 16
    -- Sachbeschaedigung: Es gilt die schwerste Anklage.
    detroit_gewaehlt AS (
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
    ),
    detroit_delikte AS (
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
    ),

    beide AS (
        SELECT * FROM chicago_delikte
        UNION ALL
        SELECT * FROM detroit_delikte
    ),
    -- Platzhalterkoordinaten sind keine Koordinaten. Detroit setzt 0/0,
    -- Chicago laesst das Feld leer.
    bereinigt AS (
        SELECT
            * EXCLUDE (latitude, longitude),
            CASE WHEN latitude BETWEEN -90 AND 90
                  AND NOT (latitude = 0 AND longitude = 0)
                 THEN latitude END                         AS latitude,
            CASE WHEN longitude BETWEEN -180 AND 180
                  AND NOT (latitude = 0 AND longitude = 0)
                 THEN longitude END                        AS longitude
        FROM beide
    ),
    -- Der raeumliche Join bewusst als INNER JOIN auf die verortbaren Punkte
    -- und erst danach zurueckverbunden. Als LEFT JOIN faellt DuckDB auf eine
    -- verschachtelte Schleife zurueck - 348'000 Punkte gegen 6'282 Polygone,
    -- und der Lauf endet nicht mehr. So bleibt es bei Sekundenbruchteilen.
    verortet AS (
        SELECT b.city, b.offense_id, t.geoid
        FROM bereinigt b
        JOIN tract t ON ST_Within(ST_Point(b.longitude, b.latitude), t.geom)
        WHERE b.latitude IS NOT NULL AND b.longitude IS NOT NULL
    ),
    -- Das Fallebene: unter den zaehlenden Zeilen eines Falls die mit dem
    -- schwersten Delikt; bei gleichem Delikt (mehrere Opfer) die frueheste.
    -- Eine Zeile ohne Fallnummer ist ihr eigener Fall. Codes ausserhalb der
    -- Hierarchie ordnen sich hinter ihr ein, nach crime_against, dann Code;
    -- ohne NIBRS-Code ganz hinten.
    fallebene AS (
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
    )

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
    ORDER BY b.city, b.occurred_at_utc, b.offense_id
    """


# ---------------------------------------------------------------------------
# Pruefungen
# ---------------------------------------------------------------------------


def reconcile(
    con: duckdb.DuckDBPyConnection,
    relation: str,
    chicago: Source,
    detroit: Source,
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
        }
        for stadt, zeilen, eindeutig, ereignisse, zugeordnet, verortet, ohne_zeit,
            taten, faelle, gezaehlte_faelle, nicht_existent, mehrdeutig
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
                   count(*) FILTER (local_time_ambiguous)
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
    chicago: Source, detroit: Source, tract: TractQuelle, config_root: Path
) -> dict[str, Any]:
    """Woraus diese Tabelle entstanden ist - vollstaendig genug zum Nachbauen.

    Die Bronze-Laeufe stehen namentlich da, seit es die Tabelle gibt. Neu
    seit dem 14.9. sind die beiden Glieder, die vorher nur Pfade waren: Die
    Crosswalks tragen ihre Pruefsumme (sie werden aus amtlichen PDFs erzeugt
    und koennen sich aendern, ohne dass der Pfad sich aendert), und
    ``silver/tract`` wird als **Referenz** genannt - mit Bauzeitpunkt,
    Eingabe-Abdruck und seiner eigenen Herkunft.
    """
    tract_manifest = {}
    tract_verzeichnis = Path(tract.pfad).parent
    if (tract_verzeichnis / "manifest.json").exists():
        tract_manifest = read_manifest(tract_verzeichnis)
    return {
        "chicago_bronze_runs": chicago.run_ids,
        "chicago_bronze_format": chicago.format,
        "detroit_bronze_runs": detroit.run_ids,
        "detroit_bronze_format": detroit.format,
        "silver_tract": referenz(Path(tract.pfad), tract_manifest),
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
) -> dict[str, Any]:
    herkunft = herkunft_von(chicago, detroit, tract, config_root)
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

    con = connect(spatial=True)
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

        con.execute(
            f"CREATE TABLE {TABLE} AS "
            + build_query(chicago, detroit, tract, config_root)
        )
        pruefung = reconcile(con, TABLE, chicago, detroit)
        manifest = build_manifest(
            con, TABLE, chicago, detroit, tract, config_root, pruefung
        )
        ziel = publish(con, TABLE, table_dir(data_root), manifest)
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
