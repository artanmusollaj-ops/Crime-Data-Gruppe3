"""Baut die Gold-Schicht: eine Faktentabelle und vier Dimensionen.

Aufruf aus dem Projekt-Root:

    python -m gold_pipeline.build_gold

Warum kein Wuerfel gebaut wird, steht in ``gold_pipeline/__init__.py``. Hier
steht, was statt dessen entsteht und woran es haengt.

**Die Stadtzuordnung ist der eigentliche Grund fuer diese Schicht.** Bis hierher
konnte das Projekt keine Rate je Einwohner belegen: ``silver/tract`` deckt ganze
Countys ab, und ein Tract sagt nicht, zu welcher Stadt er gehoert. ``dim_tract``
beantwortet das ueber die Ortsgrenzen aus ``silver/place``.

Tracts liegen dabei nicht sauber in Stadtgrenzen, sondern ueberschreiten sie.
Drei Regeln waeren denkbar, und sie fallen weit auseinander:

    Regel                     Chicago      Detroit
    alle beruehrten Tracts    3'080'550    884'691
    Flaechengewichtung        2'651'921    638'570
    Mehrheitsregel            2'661'953    638'635
    Zensus 2020               2'746'388    639'111

Gewaehlt ist die **Mehrheitsregel**: Ein Tract gehoert zu der Stadt, die mehr
als die Haelfte seiner Flaeche bedeckt. Sie gibt jedem Tract genau eine Stadt -
die Voraussetzung dafuer, dass sich Faelle ohne Doppelzaehlung summieren lassen -
und liegt praktisch gleichauf mit der Flaechengewichtung. Der verbleibende
Abstand zum Zensus ist keine Ungenauigkeit der Regel, sondern der Unterschied
zwischen einer ACS-Schaetzung und einer Zaehlung.

**Gruppiert wird ueber die amtliche Kategorie, nicht ueber das Praefix.**
``dim_offense`` fuehrt ``nibrs_category`` aus dem NIBRS User Manual 2025.0 - 28
Group-A-Kategorien und 10 fuer Group B, gelesen von
``tools/build_nibrs_categories.py``. Die Deliktfamilie (``nibrs_family``) bleibt
daneben als Kuerzel ``13``, ``23``, ``26`` ohne Bezeichnung stehen: Die
Spezifikation fuehrt dafuer keine auslesbare Liste, und eine selbst
geschriebene waere eine gepflegte Uebersetzung mehr. Sie ist seit den
Kategorien aber auch kein Auswertungsweg mehr, sondern ein technisches Praefix
- ``left(nibrs_code, 2)`` und die Kategorie fallen an vier Stellen
nachweislich auseinander.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import duckdb

from manifeste import code_stand, eingabe_abdruck, referenz, referenzdatei
from storage import StorageError, for_root, manifest_von
from gold_pipeline import (
    GATE_HOECHSTENS,
    GATE_MINDESTENS,
    GEO_STATUS_WERTE,
    GOLD_LAYER,
    MAPPING_STATUS_WERTE,
    STADT_SCHWELLE,
    STADT_SCHLUESSEL,
    TABELLEN,
    table_dir,
)
from silver_pipeline import (
    PARQUET_FILE,
    SILVER_LAYER,
    TransformError,
    connect,
    publish,
    read_manifest,
    schema_of,
)


# Der Deutungsvertrag: Was diese Tabelle bedeutet - Granularität, Regeln, Spalten -
# nicht, wie der Code sie baut. Steigt die Zahl, sind aeltere Staende anders
# zu lesen. Jede Erhoehung gehoert in AENDERUNGEN.md, siehe
# "Vertragsversionen"; ein Test prueft das.
CONTRACT_VERSION = 4

DEFAULT_VINTAGE = 2024
NIBRS_CODES = "nibrs_offense_codes_2025.csv"
NIBRS_KATEGORIEN = "nibrs_offense_categories_2025.csv"
CROSSWALKS = ("iucr_nibrs_mapping.csv", "micr_nibrs_mapping.csv")

# Vier NIBRS-Codes hat das FBI zurueckgezogen; die Fassung 2025 fuehrt sie nicht
# mehr. Die MICR-Quellen fuehren sie weiter, und zwei davon stehen in den
# Falldaten 2024. Ein Code, der in den Daten steht, muss aber sagen koennen, was
# er heute bedeutet - sonst ist eine Zeitreihe ueber mehrere Jahrgaenge nicht zu
# lesen und ein Filter nicht zu bauen.
#
# Aufgeloest wird nur, wo es einen Beleg gibt. Die Spezifikation selbst schweigt;
# sie kennt die Codes gar nicht mehr. Belegen laesst es sich ueber die
# ILCS-Tabelle der Illinois State Police, die je Statut einen aktuellen
# IBR-Code vergibt - dieselbe Quelle, die schon die Chicagoer Gegenprobe traegt.
#
#   'replaced'        es gibt einen heutigen Code, und eine Quelle sagt welchen
#   'not_an_offense'  das FBI hat den Code gestrichen, weil es keine Tat ist
#   'unresolved'      kein Beleg; darf nicht in den Falldaten vorkommen
# Zwei Codes, die das Handbuch weiter fuehrt, aber beim Veroeffentlichen
# umschluesselt. Sie sind nicht zurueckgezogen - sie duerfen gemeldet werden -,
# aber wer sie in einer Auswertung stehen laesst, zaehlt anders als das FBI.
#
# Beleg ist das Aenderungsprotokoll des User Manual zur Fassung 2023.0:
# "Updated 11B Sodomy to indicate that offense will be reclassified to 11A Rape
# for reporting purposes as of 2023"; fuer 11C steht dort dasselbe. In der
# Codeliste selbst stehen beide mit dem Vermerk "*Converts to 11A".
UMGESCHLUESSELT = {
    "11B": (
        "11A", "reclassified",
        "Das User Manual 2025.0 fuehrt 11B mit dem Vermerk 'Converts to 11A'; "
        "das Aenderungsprotokoll zur Fassung 2023.0 sagt, dass die Meldung seit "
        "2023 auf 11A Rape umgeschluesselt wird. Der Code bleibt meldbar",
    ),
    "11C": (
        "11A", "reclassified",
        "wie 11B: Das User Manual 2025.0 fuehrt 11C mit 'Converts to 11A', das "
        "Aenderungsprotokoll zur Fassung 2023.0 nennt die Umschluesselung auf "
        "11A Rape seit 2023. Der Code bleibt meldbar",
    ),
}

ZURUECKGEZOGEN = {
    "90A": (
        "26A", "replaced",
        "Die ILCS-Tabelle der Illinois State Police fuehrt 720-5/17-1(B) "
        "'Deceptive Practices - Bad Checks' unter IBR 26A False Pretenses/"
        "Swindle/Confidence Game. Detroits MICR-Zeile 2606 'Fraud - Bad Checks' "
        "liegt in derselben Deliktfamilie 26",
    ),
    "90I": (
        None, "not_an_offense",
        "Die Codeliste NIBRS 2011 fuehrt 90I Runaway als 'Not a Crime' und "
        "vermerkt: 'In January 2011, the FBI discontinued the collection of "
        "arrest data for runaways.' Weglaufen ist keine Straftat - deshalb gibt "
        "es keinen Nachfolger. Die Zeilen bleiben zaehlbar, tragen aber kein "
        "heutiges NIBRS-Delikt",
    ),
    "90E": (
        None, "unresolved",
        "Oeffentliche Trunkenheit ist in Illinois keine Straftat; die "
        "ILCS-Tabelle fuehrt dazu keine Zeile. Kommt in den Falldaten 2024 "
        "nicht vor",
    ),
    "90H": (
        None, "unresolved",
        "Die naechstliegenden Statute 720-5/26-4 (Unauthorized Video "
        "Recording) verteilen sich je nach Ort auf 370 und 90C - kein "
        "einzelner Nachfolger. Kommt in den Falldaten 2024 nicht vor",
    ),
}

log = logging.getLogger("gold")


class Quelle(NamedTuple):
    """Etwas, aus dem eine Gold-Tabelle abgeleitet ist.

    Meist eine Silver-Tabelle. ``dim_offense`` entsteht dagegen aus zwei
    versionierten CSV-Dateien unter ``config/`` - die Dimension traegt die
    ganze NIBRS-Klassifikation und muss sagen koennen, woher sie stammt.
    """

    name: str
    pfad: str | Path   # Silver: lokal oder s3://; config: lokal
    layer: str = SILVER_LAYER
    # Das Manifest der Quelle, damit Gold ihren **Stand** nennen kann und
    # nicht nur ihren Pfad. Bei Referenzdateien unter config/ leer.
    manifest: dict[str, Any] | None = None

    @property
    def relation(self) -> str:
        return f"read_parquet('{self.pfad}')"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    parser.add_argument("--config-root", type=Path, default=Path("config"))
    parser.add_argument("--vintage", type=int, default=DEFAULT_VINTAGE)
    return parser.parse_args()


def referenzquellen(config_root: Path) -> list[Quelle]:
    """Die beiden Dateien, aus denen ``dim_offense`` entsteht.

    Sie standen lange nicht im Manifest - ausgerechnet die Dimension, die die
    Deliktklassifikation beider Staedte traegt, nannte keine Quelle. Beide
    werden von einem Werkzeug aus amtlichen PDFs erzeugt und nicht von Hand
    gepflegt; welches, sagt ``notes``.
    """
    return [
        Quelle(name, config_root / name, layer="config")
        for name in (NIBRS_CODES, NIBRS_KATEGORIEN)
    ]


def silver_quelle(data_root: Path, name: str, vintage: int | None = None) -> Quelle:
    """Der Pfad einer Silver-Tabelle; mit Vintage, wo sie danach partitioniert ist.

    Woher gelesen wird - lokal oder SeaweedFS - entscheidet die Ablage.
    """
    ablage = for_root(data_root)
    verzeichnis = f"{SILVER_LAYER}/dataset={name}"
    if vintage is not None:
        verzeichnis += f"/vintage={vintage}"
    if not ablage.exists(verzeichnis, PARQUET_FILE):
        treffer = ablage.list_files(verzeichnis, f"**/{PARQUET_FILE}")
        if not treffer:
            raise TransformError(
                f"Silver-Tabelle {name} fehlt unter {ablage.local_path(verzeichnis)}. "
                f"Zuerst bauen: python -m silver_pipeline.build_{name}"
            )
        verzeichnis = treffer[-1].rsplit("/", 1)[0]
    # Das Manifest wird mitgelesen: Gold soll sagen koennen, auf welchem
    # Silver-**Stand** es ruht - Zeitpunkt, Eingabe-Abdruck und dessen eigene
    # Herkunft. Ein Pfad allein zeigt nur auf das, was gerade dort liegt.
    manifest = {}
    if ablage.exists(verzeichnis, "manifest.json"):
        manifest = manifest_von(ablage, verzeichnis, "manifest.json")
    return Quelle(name, ablage.resolve_read_path(verzeichnis, PARQUET_FILE),
                  manifest=manifest)


# --------------------------------------------------------------------------
# dim_tract - die Stadtzuordnung
# --------------------------------------------------------------------------


def dim_tract_query(tract: Quelle, place: Quelle) -> str:
    """Ordnet jeden Tract der Stadt zu, die mehr als seine halbe Flaeche deckt.

    Der Join ist ein innerer auf ``ST_Intersects`` und danach eine Fensterfunktion:
    Ein Tract kann an beide Staedte grenzen - Chicago und Detroit liegen zwar
    weit auseinander, aber die Regel darf davon nicht abhaengen. Genommen wird
    der groesste Anteil, und nur wenn er ueber der Schwelle liegt.
    """
    staedte = ", ".join(
        f"('{geoid}', '{schluessel}')"
        for geoid, schluessel in sorted(STADT_SCHLUESSEL.items())
    )
    return f"""
    WITH studienstadt(city_geoid, city) AS (VALUES {staedte}),
    grenze AS (
        SELECT s.city_geoid, s.city, ST_GeomFromWKB(p.geometry) AS geom
        FROM {place.relation} p
        JOIN studienstadt s ON s.city_geoid = p.geoid
    ),
    anteil AS (
        SELECT
            t.geoid,
            g.city_geoid,
            g.city,
            ST_Area(ST_Intersection(ST_GeomFromWKB(t.geometry), g.geom))
                / nullif(ST_Area(ST_GeomFromWKB(t.geometry)), 0) AS flaechenanteil
        FROM {tract.relation} t
        JOIN grenze g ON ST_Intersects(ST_GeomFromWKB(t.geometry), g.geom)
    ),
    beste AS (
        SELECT * FROM (
            SELECT *, row_number() OVER (
                PARTITION BY geoid ORDER BY flaechenanteil DESC
            ) AS rang
            FROM anteil
        ) WHERE rang = 1
    )
    SELECT
        t.geoid                                         AS geoid,
        CASE WHEN b.flaechenanteil > {STADT_SCHWELLE}
             THEN b.city END                            AS city,
        CASE WHEN b.flaechenanteil > {STADT_SCHWELLE}
             THEN b.city_geoid END                      AS city_geoid,
        -- Auch unterhalb der Schwelle festgehalten: Wer flaechengewichtet
        -- rechnen will, braucht den Anteil, und wer die Regel pruefen will
        -- auch. Ohne Beruehrung ist er 0 und nicht NULL.
        coalesce(b.flaechenanteil, 0.0)                 AS city_area_share,
        t.state_fips                                    AS state_fips,
        t.state_name                                    AS state_name,
        t.county_fips                                   AS county_fips,
        t.name                                          AS tract_name,
        t.population                                    AS population,
        t.median_household_income_usd                   AS median_household_income_usd,
        t.poverty_rate                                  AS poverty_rate,
        t.land_area_m2                                  AS land_area_m2,
        t.centroid_lat                                  AS centroid_lat,
        t.centroid_lon                                  AS centroid_lon
    FROM {tract.relation} t
    LEFT JOIN beste b ON b.geoid = t.geoid
    ORDER BY geoid
    """


# --------------------------------------------------------------------------
# dim_offense, dim_date, dim_city_day
# --------------------------------------------------------------------------


def dim_offense_rows(config_root: Path) -> list[dict[str, Any]]:
    """Die amtliche NIBRS-Codeliste, plus die Codes, die nur noch die Daten kennen.

    Vier NIBRS-Codes hat das FBI zurueckgezogen; die MICR-Quellen von 2009 und
    2024 fuehren sie weiter, und zwei davon stehen in den Falldaten 2024 -
    ``90I Runaway`` mit 969 und ``90A Bad Checks`` mit 50 Faellen. Stuenden sie
    nicht in dieser Dimension, wuerde jede Auswertung, die ueber sie filtert,
    1'019 Delikte stillschweigend verlieren. Genau diese Art von Verlust soll
    ein Sternschema verhindern und nicht verursachen.

    Sie werden deshalb aufgenommen und als ``retired`` gekennzeichnet. Ihre
    Bezeichnung stammt aus den Crosswalks, die sie noch fuehren - nicht aus der
    Spezifikation, die sie nicht mehr kennt.
    """
    pfad = config_root / NIBRS_CODES
    if not pfad.exists():
        raise TransformError(f"Codeliste fehlt: {pfad}")
    with pfad.open(encoding="utf-8") as datei:
        amtlich = list(csv.DictReader(datei))
    if not amtlich:
        raise TransformError(f"Codeliste ist leer: {pfad}")

    kat_pfad = config_root / NIBRS_KATEGORIEN
    if not kat_pfad.exists():
        raise TransformError(
            f"Kategorienliste fehlt: {kat_pfad}. "
            "Zuerst: python tools/build_nibrs_categories.py"
        )
    with kat_pfad.open(encoding="utf-8") as datei:
        kategorie = {z["nibrs_code"]: z["nibrs_category"] for z in csv.DictReader(datei)}

    ohne_kategorie = sorted(
        z["nibrs_code"] for z in amtlich if z["nibrs_code"] not in kategorie
    )
    if ohne_kategorie:
        raise TransformError(
            f"Codes ohne Kategorie: {ohne_kategorie} - "
            "tools/build_nibrs_categories.py neu laufen lassen"
        )

    zeilen = []
    for z in amtlich:
        code = z["nibrs_code"]
        ersatz, aufloesung, grund = UMGESCHLUESSELT.get(code, (None, "current", None))
        zeilen.append({
            "nibrs_code": code,
            "nibrs_description": z["nibrs_description"],
            "nibrs_category": kategorie[code],
            "nibrs_family": code[:2],
            "nibrs_group": z["nibrs_group"],
            "crime_against": z["crime_against"],
            "federal_only": z["federal_only"] == "true",
            "retired": False,
            "replaced_by": ersatz,
            "resolution": aufloesung,
            "retirement_note": grund,
        })

    bekannt = {z["nibrs_code"] for z in zeilen}
    for name in CROSSWALKS:
        quelle = config_root / name
        if not quelle.exists():
            continue
        with quelle.open(encoding="utf-8") as datei:
            for z in csv.DictReader(datei):
                code = (z.get("nibrs_code") or z.get("ibr_code") or "").strip()
                if not code or code in bekannt:
                    continue
                bekannt.add(code)
                ersatz, aufloesung, grund = ZURUECKGEZOGEN.get(
                    code, (None, "unresolved", "kein Beleg hinterlegt")
                )
                zeilen.append({
                    "nibrs_code": code,
                    "nibrs_description": (
                        z.get("nibrs_description") or z.get("ibr_category") or ""
                    ).strip(),
                    "nibrs_category": kategorie.get(code, ""),
                    "nibrs_family": code[:2],
                    "nibrs_group": (z.get("nibrs_group") or "B").strip() or "B",
                    "crime_against": "",
                    "federal_only": False,
                    "retired": True,
                    "replaced_by": ersatz,
                    "resolution": aufloesung,
                    "retirement_note": grund,
                })
    return sorted(zeilen, key=lambda z: z["nibrs_code"])


def dim_date_query(offense: Quelle) -> str:
    """Ein Kalendertag je Zeile, ueber die Spanne der Falldaten.

    Erzeugt wird die Reihe und nicht aus den Fakten abgeleitet: Ein Tag ohne
    Delikt ist eine Aussage und darf nicht fehlen, sonst zeigt eine Zeitreihe
    eine Luecke als Nicht-Ereignis.
    """
    return f"""
    WITH spanne AS (
        SELECT min(occurred_date_local) AS von, max(occurred_date_local) AS bis
        FROM {offense.relation}
    )
    -- generate_series liefert auf DATE-Grenzen TIMESTAMP zurueck. Ohne den
    -- Cast traegt die Dimension einen anderen Typ als der Schluessel in
    -- fact_offense, und der Join haengt an einer stillschweigenden Umwandlung.
    SELECT
        CAST(tag AS DATE)                               AS date,
        -- Schmale Typen, weil die Sache schmal ist: ein Jahr passt in
        -- SMALLINT, alles Uebrige in TINYINT (-128 bis 127). DuckDBs
        -- Datumsfunktionen liefern durchweg BIGINT; ohne CAST stuende in
        -- einer Dimensionstabelle achtmal so viel Platz wie noetig.
        CAST(year(tag) AS SMALLINT)                     AS year,
        CAST(month(tag) AS TINYINT)                     AS month,
        CAST(quarter(tag) AS TINYINT)                   AS quarter,
        CAST(day(tag) AS TINYINT)                       AS day_of_month,
        CAST(dayofweek(tag) AS TINYINT)                 AS day_of_week,
        dayname(tag)                                    AS day_name,
        monthname(tag)                                  AS month_name,
        CAST(date_trunc('month', tag) AS DATE)          AS month_start,
        dayofweek(tag) IN (0, 6)                        AS is_weekend,
        CAST(dayofyear(tag) AS SMALLINT)                AS day_of_year
    FROM spanne, unnest(generate_series(von, bis, INTERVAL 1 DAY)) AS t(tag)
    ORDER BY date
    """


def dim_city_day_query(weather: Quelle, offense: Quelle) -> str:
    """Stadt und Tag mit dem Wetter, auf die Spanne der Falldaten beschnitten.

    Die Wetterquelle reicht bis 1942 zurueck. Fuer Gold zaehlt der Jahrgang,
    den die Falldaten abdecken; alles andere blaeht die Dimension auf, ohne
    eine Frage zu beantworten.

    **Warum die beiden Spurenspalten mitkommen.** NOAA kennt ein Messflag
    ``T``: gefallen, aber unter der Aufloesung des Geraets. Der Messwert ist
    dann ``0``, und das heisst etwas anderes als *trocken*. Silver haelt den
    Unterschied seit jeher in ``precipitation_trace`` und ``snowfall_trace``;
    Gold liess beide Spalten bis zum 15.9.2026 fallen.

    Gemessen war das keine Feinheit: Von den 481 Gold-Tagen mit ``0`` mm
    Niederschlag sind **113 Spurentage** - 45 in Chicago, 68 in Detroit. Eine
    Abfrage nach trockenen Tagen zaehlte sie mit, und niemand konnte es der
    Tabelle ansehen. Konzept 9.3 verlangt ausdruecklich, dass die
    Spurenmengen in Gold erhalten bleiben.
    """
    return f"""
    WITH spanne AS (
        SELECT min(occurred_date_local) AS von, max(occurred_date_local) AS bis
        FROM {offense.relation}
    )
    SELECT
        w.city                                          AS city,
        w.date                                          AS date,
        w.station_id                                    AS station_id,
        w.station_name                                  AS station_name,
        w.temp_max_c                                    AS temp_max_c,
        w.temp_min_c                                    AS temp_min_c,
        w.precipitation_mm                              AS precipitation_mm,
        w.snowfall_mm                                   AS snowfall_mm,
        w.precipitation_trace                           AS precipitation_trace,
        w.snowfall_trace                                AS snowfall_trace,
        w.quality_flags                                 AS quality_flags
    FROM {weather.relation} w, spanne
    WHERE w.date BETWEEN spanne.von AND spanne.bis
    ORDER BY city, date
    """


# --------------------------------------------------------------------------
# fact_offense
# --------------------------------------------------------------------------


def fact_offense_query(offense: Quelle, tracts: str = "dim_tract") -> str:
    """Eine Zeile je **Tat**, mit den Schluesseln der Dimensionen.

    Hier liegt der einzige Stellenwechsel gegenueber Silver. Detroits Zeilen
    sind **Anklagen**, Chicagos sind **Delikte**: Ein Ueberfall mit Schuessen
    und geraubtem Auto steht bei Detroit als fuenf Zeilen, bei Chicago als
    eine. Wer beide summiert, zaehlt Detroit um 3,8 Prozent zu hoch.

    Silver haelt deshalb jede Anklage und markiert je Tat eine Zeile mit
    ``counts``; Gold nimmt nur diese. Wer die Anklagen braucht - "wie oft wurde
    zusaetzlich Sachbeschaedigung angezeigt" -, findet sie vollstaendig in
    ``silver/crime_offense``.

    Dazu kommt ``counts_case`` unveraendert aus Silver: je **Fall** eine Zeile,
    die mit dem schwersten Delikt. Chicago fuehrt je Vorfall ein Delikt,
    Detroit jedes - auf Tatebene zaehlt Detroit 6,4 Prozent, die Chicago nie
    zaehlt. Wer beide Staedte auf Chicagos Zaehlweise vergleichen will, filtert
    auf ``counts_case``; die Tatzahlen bleiben, wie sie sind.


    Ergaenzt werden nur Groessen, die sich aus dem Zeitstempel ableiten, und die
    Deliktfamilie. Sie sparen keine Laufzeit - gemessen 0,3 Millisekunden -,
    sondern ersparen jeder Abfrage das Wissen, dass die Familie die ersten
    beiden Zeichen des Codes sind.
    """
    return f"""
    SELECT
        o.offense_id                                    AS offense_id,
        o.event_id                                      AS event_id,
        o.city                                          AS reporting_city,
        o.occurred_at_utc                               AS occurred_at_utc,
        o.occurred_at_local                             AS occurred_at_local,
        o.occurred_date_local                           AS date,
        CAST(hour(o.occurred_at_local) AS TINYINT)      AS hour_of_day,
        -- Genau hier wird die Spalte gebraucht: Eine Stundenverteilung ueber
        -- hour_of_day zaehlt eine mehrdeutige Ortszeit in einen der beiden
        -- Toepfe, und ohne diese Spalte ist nicht zu sehen, welche Zeilen das
        -- betrifft. Chicago liefert Wanduhrzeit ohne Zone; 48 Zeilen liegen in
        -- der Stunde, die es am 3.11.2024 zweimal gab.
        o.local_time_ambiguous                          AS local_time_ambiguous,
        o.tract_geoid                                   AS tract_geoid,
        o.nibrs_code                                    AS nibrs_code,
        left(o.nibrs_code, 2)                           AS nibrs_family,
        o.source_offense_code                           AS source_offense_code,
        o.source_offense_description                    AS source_offense_description,
        o.latitude                                      AS latitude,
        o.longitude                                     AS longitude,
        o.located                                       AS located,
        o.mapping_status                                AS mapping_status,
        -- Warum eine Zeile in einer Tract-Auswertung fehlt, in einem Wort.
        -- ``located`` sagt nur ja oder nein; hier steht der Grund, und die
        -- vierte Stufe braucht die Stadtgrenze - deshalb entsteht die Spalte
        -- in Gold und nicht in Silver.
        CASE
            WHEN o.latitude IS NULL   THEN 'missing_coordinate'
            WHEN o.tract_geoid IS NULL THEN 'no_tract'
            WHEN t.city IS NULL        THEN 'outside_city'
            ELSE 'inside_city'
        END                                             AS geo_status,
        o.arrest                                        AS arrest,
        o.unfounded                                     AS unfounded,
        o.offense_group_id                              AS offense_group_id,
        o.counts_case                                   AS counts_case
    FROM {offense.relation} o
    LEFT JOIN {tracts} t ON t.geoid = o.tract_geoid
    WHERE o.counts
    """


# --------------------------------------------------------------------------
# Nachweis
# --------------------------------------------------------------------------


def abdeckung(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """Misst, wie sich die Fakten auf die beiden Statusspalten verteilen.

    Nur messen - ob die Anteile ausreichen, entscheidet ``pruefe_gate``. Die
    Trennung ist Absicht: Eine Messung darf auch dann Zahlen liefern, wenn sie
    schlecht aussehen, und eine Testfixture mit zwei Zeilen hat naturgemaess
    schraege Anteile.

    Eine Pruefung steckt trotzdem hier, weil sie keine Ermessensfrage ist:
    Kommt in ``mapping_status`` oder ``geo_status`` ein Wert vor, den der Code
    nicht kennt, hat jemand die Einstufung geaendert - dann bleibt der Bau
    stehen, statt eine Kennzahl still zu verschieben.
    """
    unbekannt = {}
    for spalte, erlaubt in (("mapping_status", MAPPING_STATUS_WERTE),
                            ("geo_status", GEO_STATUS_WERTE)):
        fremd = sorted(
            str(z[0]) for z in con.execute(
                f"SELECT DISTINCT {spalte} FROM fact_offense"
            ).fetchall() if z[0] not in erlaubt
        )
        if fremd:
            unbekannt[spalte] = fremd
    if unbekannt:
        raise TransformError(
            f"Unbekannte Statuswerte in fact_offense: {unbekannt}. Entweder "
            "ist die Einstufung geaendert worden - dann gehoert der neue Wert "
            "in MAPPING_STATUS_WERTE beziehungsweise GEO_STATUS_WERTE - oder "
            "es ist ein Tippfehler."
        )

    gesamt = con.execute("SELECT count(*) FROM fact_offense").fetchone()[0]
    anteile: dict[str, float] = {}
    for spalte, werte in (("geo_status", GEO_STATUS_WERTE),
                          ("mapping_status", MAPPING_STATUS_WERTE)):
        for wert in sorted(werte):
            n = con.execute(
                f"SELECT count(*) FROM fact_offense WHERE {spalte} = ?", [wert]
            ).fetchone()[0]
            anteile[wert] = round(100.0 * n / gesamt, 4) if gesamt else 0.0

    return anteile


def abdeckung_je_stadt(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, float]]:
    """Dieselben Anteile, aber je meldender Stadt.

    **Warum das noetig ist.** Der Gesamtanteil ist ein Mittel, und ein Mittel
    verdeckt. Eine externe Pruefung hat das am 15.9.2026 vorgerechnet: 750
    Chicagoer Zeilen zu 100 % exakt und 250 Detroiter zu 70 % ergeben 92,5 %
    gemeinsam - bestanden, bei einer Schwelle von 85 %. Detroits Crosswalk
    haette also zu einem Drittel brechen koennen, ohne dass etwas rot wird.

    Chicago ist dreimal so gross wie Detroit. Genau deshalb traegt der
    Gesamtanteil Chicagos Zahl und nicht Detroits.
    """
    zeilen = con.execute("""
        SELECT reporting_city, geo_status, mapping_status, count(*)
        FROM fact_offense GROUP BY 1, 2, 3
    """).fetchall()
    gesamt: dict[str, int] = {}
    treffer: dict[str, dict[str, int]] = {}
    for stadt, geo, mapping, n in zeilen:
        gesamt[stadt] = gesamt.get(stadt, 0) + n
        je = treffer.setdefault(stadt, {})
        for wert in (geo, mapping):
            je[wert] = je.get(wert, 0) + n

    ergebnis: dict[str, dict[str, float]] = {}
    for stadt, n_gesamt in sorted(gesamt.items()):
        je = treffer.get(stadt, {})
        ergebnis[stadt] = {
            wert: round(100.0 * je.get(wert, 0) / n_gesamt, 4) if n_gesamt else 0.0
            for wert in sorted(set(GEO_STATUS_WERTE) | set(MAPPING_STATUS_WERTE))
        }
    return ergebnis


def pruefe_gate(anteile: dict[str, float],
                je_stadt: dict[str, dict[str, float]] | None = None) -> None:
    """Das Publish-Gate: Gold wird nur veroeffentlicht, wenn die Abdeckung traegt.

    Gerufen wird es von ``build`` und nicht von ``reconcile`` - ein Nachweis
    misst, ein Gate entscheidet. Warum die Schwellen so weit unter den
    gemessenen Werten liegen, steht bei ``GATE_MINDESTENS``.

    Geprueft wird der Gesamtanteil **und jede Stadt fuer sich**. Dieselben
    Schwellen: Wer den Vergleich zweier Staedte baut, muss ihn fuer beide
    tragen koennen. Ein Mittel ueber beide verdeckt sonst genau die Stadt, die
    bricht - siehe ``abdeckung_je_stadt``.
    """
    _gegen_schwellen(anteile, woher="insgesamt")
    for stadt, ihre in (je_stadt or {}).items():
        _gegen_schwellen(ihre, woher=stadt)


def _gegen_schwellen(anteile: dict[str, float], *, woher: str) -> None:
    for wert, boden in GATE_MINDESTENS.items():
        ist = anteile.get(wert, 0.0)
        if ist < boden:
            raise TransformError(
                f"Abdeckung reisst die Schwelle ({woher}): {wert} bei {ist} %, "
                f"verlangt sind mindestens {boden} %. Die Schwelle liegt weit "
                "unter dem gemessenen Stand - vor dem Hochsetzen pruefen, ob "
                "der raeumliche Join oder ein Crosswalk gebrochen ist."
            )
    for wert, decke in GATE_HOECHSTENS.items():
        ist = anteile.get(wert, 0.0)
        if ist > decke:
            raise TransformError(
                f"Abdeckung reisst die Schwelle ({woher}): {wert} bei {ist} %, "
                f"erlaubt sind hoechstens {decke} %."
            )


def reconcile(
    con: duckdb.DuckDBPyConnection, offense: Quelle
) -> dict[str, Any]:
    """Weist nach, dass Gold die Fakten vollstaendig traegt und die Schluessel passen.

    Die Nachweise sind auf die Fehler zugeschnitten, die diese Schicht machen
    kann: eine Zeile beim Umschreiben verlieren, einen Fremdschluessel ins Leere
    zeigen lassen, oder jedem Tract zwei Staedte geben.
    """
    silber, zaehlend = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE counts) FROM {offense.relation}"
    ).fetchone()
    gold = con.execute("SELECT count(*) FROM fact_offense").fetchone()[0]
    if zaehlend != gold:
        raise TransformError(
            f"fact_offense hat {gold:,} Zeilen, in silver/crime_offense zaehlen "
            f"aber {zaehlend:,} von {silber:,}"
        )
    # Je Tat genau eine Zeile - sonst zaehlt Detroit doppelt, und das war der
    # Grund fuer diese Schicht.
    mehrfach = con.execute(
        "SELECT count(*) FROM (SELECT offense_group_id FROM fact_offense "
        "WHERE offense_group_id IS NOT NULL "
        "GROUP BY 1 HAVING count(*) > 1)"
    ).fetchone()[0]
    if mehrfach:
        raise TransformError(
            f"{mehrfach:,} Taten stehen mehrfach in fact_offense"
        )

    verwaist_delikt = con.execute(
        "SELECT count(*) FROM fact_offense f "
        "LEFT JOIN dim_offense d ON d.nibrs_code = f.nibrs_code "
        "WHERE f.nibrs_code IS NOT NULL AND d.nibrs_code IS NULL"
    ).fetchone()[0]
    verwaist_tract = con.execute(
        "SELECT count(*) FROM fact_offense f "
        "LEFT JOIN dim_tract d ON d.geoid = f.tract_geoid "
        "WHERE f.tract_geoid IS NOT NULL AND d.geoid IS NULL"
    ).fetchone()[0]
    verwaist_tag = con.execute(
        "SELECT count(*) FROM fact_offense f "
        "LEFT JOIN dim_date d ON d.date = f.date WHERE d.date IS NULL"
    ).fetchone()[0]
    for name, anzahl in (
        ("dim_offense", verwaist_delikt),
        ("dim_tract", verwaist_tract),
        ("dim_date", verwaist_tag),
    ):
        if anzahl:
            raise TransformError(
                f"{anzahl:,} Zeilen in fact_offense zeigen auf keine Zeile in {name}"
            )

    # Ein zurueckgezogener Code, der in den Daten vorkommt, muss sagen koennen,
    # was er heute bedeutet. Sonst laesst sich weder eine Zeitreihe ueber mehrere
    # Jahrgaenge lesen noch ein Filter bauen, der nichts verliert: Wer nach 26A
    # filtert, uebersieht sonst die Faelle, die frueher 90A hiessen.
    ungeloest = con.execute(
        "SELECT d.nibrs_code, count(*) FROM fact_offense f "
        "JOIN dim_offense d ON d.nibrs_code = f.nibrs_code "
        "WHERE d.retired AND d.resolution = 'unresolved' "
        "GROUP BY 1 ORDER BY 1"
    ).fetchall()
    if ungeloest:
        raise TransformError(
            "Zurueckgezogene Codes ohne Aufloesung in den Falldaten: "
            + ", ".join(f"{code} ({n:,} Faelle)" for code, n in ungeloest)
            + " - ZURUECKGEZOGEN in build_gold.py braucht einen belegten Eintrag"
        )
    ohne_begruendung = con.execute(
        "SELECT count(*) FROM dim_offense WHERE retired "
        "AND (retirement_note IS NULL OR trim(retirement_note) = '')"
    ).fetchone()[0]
    if ohne_begruendung:
        raise TransformError(
            f"{ohne_begruendung} zurueckgezogene Codes ohne Begruendung"
        )

    mehrfach = con.execute(
        "SELECT count(*) FROM (SELECT geoid FROM dim_tract "
        "GROUP BY geoid HAVING count(*) > 1)"
    ).fetchone()[0]
    if mehrfach:
        raise TransformError(f"{mehrfach} Tracts stehen mehrfach in dim_tract")

    einwohner = {
        zeile[0]: {"tracts": zeile[1], "population": zeile[2]}
        for zeile in con.execute(
            "SELECT city, count(*), sum(population) FROM dim_tract "
            "WHERE city IS NOT NULL GROUP BY city ORDER BY city"
        ).fetchall()
    }
    fehlend = sorted(set(STADT_SCHLUESSEL.values()) - set(einwohner))
    if fehlend:
        raise TransformError(
            f"Keine Tracts der Stadt zugeordnet: {fehlend} - die Stadtgrenze "
            "aus silver/place passt nicht zu den Tracts"
        )

    # Wo die meldende Stadt und die Stadt des Tracts auseinanderfallen, liegt
    # ein Fall knapp jenseits der Stadtgrenze. Das ist kein Fehler, aber es
    # gehoert gemessen - es ist der Preis der Mehrheitsregel.
    abweichend = con.execute(
        "SELECT count(*) FROM fact_offense f JOIN dim_tract d ON d.geoid = f.tract_geoid "
        "WHERE d.city IS NOT NULL AND d.city <> f.reporting_city"
    ).fetchone()[0]
    ausserhalb = con.execute(
        "SELECT count(*) FROM fact_offense f JOIN dim_tract d ON d.geoid = f.tract_geoid "
        "WHERE d.city IS NULL"
    ).fetchone()[0]
    verortet = con.execute(
        "SELECT count(*) FROM fact_offense WHERE tract_geoid IS NOT NULL"
    ).fetchone()[0]

    zurueckgezogen = {
        zeile[0]: {
            "resolution": zeile[1],
            "replaced_by": zeile[2],
            "offenses": zeile[3],
        }
        for zeile in con.execute(
            "SELECT d.nibrs_code, d.resolution, d.replaced_by, count(f.offense_id) "
            "FROM dim_offense d LEFT JOIN fact_offense f ON f.nibrs_code = d.nibrs_code "
            "WHERE d.retired GROUP BY 1, 2, 3 ORDER BY 1"
        ).fetchall()
    }

    anteile = abdeckung(con)

    return {
        "verified": True,
        "grain": "eine Tat; Detroits weitere Anklagen bleiben in Silver",
        "coverage_percent": anteile,
        "coverage_percent_by_city": abdeckung_je_stadt(con),
        "coverage_gate": {
            "minimum": GATE_MINDESTENS,
            "maximum": GATE_HOECHSTENS,
            "applies_to": "insgesamt und je meldender Stadt",
        },
        "fact_rows": gold,
        "silver_rows": silber,
        "silver_rows_counting": zaehlend,
        "charges_dropped": silber - zaehlend,
        "retired_codes": zurueckgezogen,
        "orphan_keys": {
            "dim_offense": verwaist_delikt,
            "dim_tract": verwaist_tract,
            "dim_date": verwaist_tag,
        },
        "tract_geoid_unique": True,
        "city_assignment": einwohner,
        "offenses_in_a_tract": verortet,
        "offenses_whose_tract_belongs_to_the_other_city": abweichend,
        "offenses_whose_tract_belongs_to_no_study_city": ausserhalb,
    }


def herkunft_der_quelle(q: Quelle) -> dict[str, Any]:
    """Wie Gold eine Quelle nennt - mit ihrem Stand, nicht nur ihrem Pfad.

    Bis zum 14.9. stand hier ``{"layer", "table", "path"}``, und das war das
    schwaechste Glied der Herkunftskette: Ein Pfad zeigt auf das, was gerade
    dort liegt. Wird Silver neu gebaut, zeigt derselbe Satz auf etwas anderes
    - und nichts am Gold-Manifest verraet es. Jetzt steht dabei, **wann**
    jener Stand gebaut wurde, auf **welchen Eingaben** er ruhte, und
    woertlich dessen eigene Herkunft. Damit nennt ein Gold-Manifest die
    Bronze-Laeufe, aus denen seine Zahlen stammen, auch wenn Silver
    inzwischen weitergezogen ist.

    Referenzdateien unter ``config/`` tragen stattdessen ihre Pruefsumme -
    sie werden aus amtlichen PDFs erzeugt und haben keinen Bauzeitpunkt.
    """
    kopf = {"layer": q.layer, "table": q.name}
    if q.layer == "config":
        return {**kopf, **referenzdatei(Path(q.pfad))}
    return {**kopf, **referenz(q.pfad, q.manifest or {})}


def build_manifest(
    con: duckdb.DuckDBPyConnection,
    tabelle: str,
    quellen: list[Quelle],
    started: datetime,
    nachweis: dict[str, Any] | None,
    granularitaet: str,
    notizen: dict[str, str],
) -> dict[str, Any]:
    herkunft = [herkunft_der_quelle(q) for q in quellen]
    manifest = {
        "status": "complete",
        "contract_version": CONTRACT_VERSION,
        "code_version": code_stand(),
        "layer": GOLD_LAYER,
        "table": tabelle,
        "grain": granularitaet,
        "built_at_utc": started.isoformat().replace("+00:00", "Z"),
        "tool": f"duckdb {duckdb.__version__} mit spatial",
        "format": "parquet (snappy)",
        "row_count": con.execute(f"SELECT count(*) FROM {tabelle}").fetchone()[0],
        "derived_from": herkunft,
        "input_fingerprint": eingabe_abdruck(herkunft),
        "schema": schema_of(con, tabelle),
        "notes": notizen,
    }
    if nachweis is not None:
        manifest["reconciliation"] = nachweis
    return manifest


def build(data_root: Path, config_root: Path, vintage: int) -> dict[str, Path]:
    """Baut alle fuenf Tabellen und veroeffentlicht sie einzeln atomar."""
    started = datetime.now(timezone.utc)
    offense = silver_quelle(data_root, "crime_offense")
    tract = silver_quelle(data_root, "tract", vintage)
    place = silver_quelle(data_root, "place", vintage)
    weather = silver_quelle(data_root, "weather_day")
    for q in (offense, tract, place, weather):
        log.info("Quelle: silver/%s", q.name)

    con = connect(spatial=True)
    ziele: dict[str, Path] = {}
    try:
        con.execute(f"CREATE TABLE dim_tract AS {dim_tract_query(tract, place)}")
        con.execute(
            "CREATE TABLE dim_offense (nibrs_code VARCHAR, nibrs_description VARCHAR, "
            "nibrs_category VARCHAR, nibrs_family VARCHAR, nibrs_group VARCHAR, "
            "crime_against VARCHAR, federal_only BOOLEAN, retired BOOLEAN, "
            "replaced_by VARCHAR, resolution VARCHAR, retirement_note VARCHAR)"
        )
        con.executemany(
            "INSERT INTO dim_offense VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(z.values()) for z in dim_offense_rows(config_root)],
        )
        con.execute(f"CREATE TABLE dim_date AS {dim_date_query(offense)}")
        con.execute(
            f"CREATE TABLE dim_city_day AS {dim_city_day_query(weather, offense)}"
        )
        con.execute(f"CREATE TABLE fact_offense AS {fact_offense_query(offense)}")

        nachweis = reconcile(con, offense)
        # Erst hier, nicht im Nachweis: Was gemessen wurde, steht im Manifest;
        # ob es reicht, entscheidet das Gate - und zwar bevor irgendeine
        # Tabelle veroeffentlicht wird.
        pruefe_gate(nachweis["coverage_percent"],
                    nachweis.get("coverage_percent_by_city"))

        bauplan = [
            ("fact_offense", "eine Tat", [offense],
             {"granularitaet": (
                 "eine Zeile je Tat. Detroits Zeilen sind Anklagen - je Tat "
                 "zaehlt eine; Chicagos Zeile ist schon die Tat. Ohne das "
                 "waere Detroit um 3,8 Prozent zu hoch gezaehlt"),
              "alle_anklagen": (
                  "vollstaendig in silver/crime_offense, mit counts und "
                  "counts_reason je Zeile"),
              "reporting_city": "die meldende Stadt, nicht die Stadt des Tracts",
              "local_time_ambiguous": (
                  "die Ortszeit gab es zweimal - der Wechsel zurueck von der "
                  "Sommerzeit. Betrifft nur Chicago, das Wanduhrzeit ohne Zone "
                  "liefert; Detroit liefert einen Zeitpunkt. Wer hour_of_day "
                  "auswertet, sollte die Spalte kennen")}),
            ("dim_tract", "ein Census Tract", [tract, place],
             {"stadtzuordnung": (
                 f"Mehrheitsregel: Flaechenanteil ueber {STADT_SCHWELLE}. "
                 "city_area_share bleibt erhalten, wer flaechengewichtet "
                 "rechnen will"),
              "city_ist_null": (
                  "Tract liegt ausserhalb beider Studienstaedte oder nur "
                  "teilweise darin")}),
            ("dim_offense", "ein NIBRS-Delikt", referenzquellen(config_root),
             {"nibrs_category": (
                 "die amtliche Gliederung aus dem NIBRS User Manual 2025.0: "
                 "28 Group-A- und 10 Group-B-Kategorien. Fuer die vier "
                 "zurueckgezogenen Codes aus der Codeliste NIBRS 2011, die das "
                 "Handbuch nicht mehr fuehrt"),
              "nibrs_family": (
                 "die ersten beiden Zeichen des Codes. KEINE amtliche "
                 "Gliederung - 11 und 36 sind beide Sex Offenses, 58/61/62 "
                 "alle Commerce Violations, 10 zerfaellt in drei und 90 in "
                 "zehn Kategorien. Als technischer Schluessel erhalten, zum "
                 "Gruppieren gehoert nibrs_category"),
              "retired": (
                  "true fuer Codes, die das FBI zurueckgezogen hat, die die "
                  "MICR-Quellen aber weiter fuehren. Sie stehen hier, damit "
                  "kein Filter ueber die Dimension Faelle verliert"),
              "resolution": (
                  "was der Code heute bedeutet: current, replaced (dann nennt "
                  "replaced_by den heutigen Code), not_an_offense, oder "
                  "unresolved. Ein unresolved-Code darf in den Falldaten nicht "
                  "vorkommen; der Bau scheitert sonst"),
              "replaced_by": (
                  "der heutige NIBRS-Code, belegt ueber die ILCS-Tabelle der "
                  "Illinois State Police; retirement_note nennt das Statut")}),
            ("dim_date", "ein Kalendertag", [offense],
             {"vollstaendig": "auch Tage ohne Delikt, sonst zeigt eine "
                              "Zeitreihe eine Luecke als Nicht-Ereignis"}),
            ("dim_city_day", "eine Stadt an einem Tag", [weather, offense],
             {"spanne": "auf die Spanne der Falldaten beschnitten",
              "spurenmengen": (
                  "precipitation_trace und snowfall_trace tragen NOAAs Flag "
                  "T: gefallen, aber unter der Aufloesung. Der Messwert ist "
                  "dann 0 und bedeutet nicht trocken - wer trockene Tage "
                  "zaehlt, muss die Spalte lesen")}),
        ]
        gebaut = tuple(z[0] for z in bauplan)
        if gebaut != TABELLEN:
            raise TransformError(
                f"Der Bauplan nennt {gebaut}, gold_pipeline.TABELLEN sagt "
                f"{TABELLEN}. Beide muessen dasselbe sagen - ein Release "
                "leitet daraus ab, was vollstaendig heisst."
            )
        for tabelle, granularitaet, quellen, notizen in bauplan:
            manifest = build_manifest(
                con, tabelle, quellen, started,
                nachweis if tabelle == "fact_offense" else None,
                granularitaet, notizen,
            )
            ziele[tabelle] = publish(
                con, tabelle, table_dir(data_root, tabelle), manifest
            )
            log.info(
                "%s: %s Zeilen -> %s",
                tabelle,
                f"{manifest['row_count']:,}",
                ziele[tabelle],
            )
    finally:
        con.close()
    # Erst wenn alle fuenf lokal stehen: Ein halbes Gold auf S3 waere genau
    # der Stand, den ein anderer Rechner dann fuer vollstaendig hielte.
    ablage = for_root(data_root)
    for tabelle in ziele.values():
        ablage.publish_table(tabelle)
    return ziele


def main() -> int:
    args = arguments()
    try:
        ziele = build(for_root(args.data_root).local_root, args.config_root, args.vintage)
        manifest = read_manifest(ziele["fact_offense"])
        nachweis = manifest["reconciliation"]
        log.info("Gold gebaut, %s Tabellen", len(ziele))
        for stadt, werte in sorted(nachweis["city_assignment"].items()):
            log.info(
                "  %s: %s Tracts, %s Einwohner",
                stadt,
                f"{werte['tracts']:,}",
                f"{werte['population']:,}",
            )
        log.info(
            "  Delikte in einem Tract: %s, davon in keiner Studienstadt: %s",
            f"{nachweis['offenses_in_a_tract']:,}",
            f"{nachweis['offenses_whose_tract_belongs_to_no_study_city']:,}",
        )
        return 0
    except (TransformError, StorageError, OSError, duckdb.Error) as error:
        log.error("Gold-Aufbau fehlgeschlagen: %s", error)
        return 1
    except KeyboardInterrupt:
        log.error("Abgebrochen; es wurde keine Tabelle veroeffentlicht")
        return 130


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    raise SystemExit(main())
