#!/usr/bin/env python3
"""Erzeugt ``docs/feldkatalog.md`` aus den Manifesten und den Beschreibungen hier.

    python tools/build_feldkatalog.py

**Warum erzeugt und nicht geschrieben.** Ein von Hand gepflegter Feldkatalog
ist die Sorte Dokument, die still veraltet: Eine Spalte kommt dazu, niemand
denkt daran, und der Katalog behauptet weiter den alten Stand. Spaltennamen und
Typen kommen deshalb aus den **Manifesten** der gebauten Tabellen - dort stehen
sie ohnehin, und sie stimmen per Konstruktion. Von Hand gepflegt wird nur, was
sich nicht ableiten laesst: die **Bedeutung**.

``tests/test_feldkatalog.py`` prueft dreierlei: dass jede gebaute Spalte eine
Beschreibung hat, dass keine Beschreibung ins Leere zeigt, und dass ein zweiter
Lauf dieselbe Datei liefert.

**Wie eine neue Spalte dazukommt.** Tabelle bauen, ``python
tools/build_feldkatalog.py`` laufen lassen - der Lauf scheitert und nennt die
Spalte. Dann hier eintragen und erneut laufen lassen. Der Umweg ist Absicht:
Wer eine Spalte hinzufuegt, soll einen Satz darueber schreiben muessen.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "crime"))
from manifeste import tabellen  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ZIEL = PROJECT_ROOT / "docs" / "feldkatalog.md"

# serving seit 17.9.2026: die vier Vergleichstabellen aus build_comparison.
SCHICHTEN = ("silver", "gold", "serving")

# Spalten, die ueberall dasselbe bedeuten. Sie hier einmal zu erklaeren ist
# ehrlicher, als denselben Satz neunmal zu wiederholen und beim zehnten Mal
# leicht anders.
GEMEINSAM: dict[str, str] = {
    # Steht seit dem 16.9.2026 in silver/crime_offense und gold/fact_offense.
    "local_time_ambiguous":
        "Die Ortszeit gab es **zweimal** - der Wechsel zurück von der "
        "Sommerzeit. Betrifft nur Chicago, das Wanduhrzeit ohne Zone liefert; "
        "Detroit liefert einen Zeitpunkt und hat den Fall nicht.",
    "local_time_nonexistent":
        "Die Ortszeit gab es **nicht** - der Wechsel zur Sommerzeit. DuckDB "
        "rechnet sie als Winterzeit um.",
    # Steht seit dem 15.9.2026 in silver/weather_day **und** gold/dim_city_day
    # und bedeutet dort dasselbe.
    "precipitation_trace":
        "Spurenmenge Niederschlag - messbar, aber unter der Auflösung. "
        "`precipitation_mm = 0` mit diesem Flag heisst **nicht** trocken.",
    "snowfall_trace": "Spurenmenge Schnee, analog.",
    "geoid": "Census-GEOID der Raumeinheit, die sie eindeutig macht. "
             "Der Schlüssel, über den Delikte, Einwohner und Geometrie zusammenfinden.",
    "state_fips": "Zwei Ziffern des Bundesstaats: `17` Illinois, `26` Michigan.",
    "state_name": "Name des Bundesstaats, kleingeschrieben.",
    "county_fips": "Drei Ziffern des County innerhalb des Bundesstaats: "
                   "`031` Cook (Chicago), `163` Wayne (Detroit).",
    "land_area_m2": "Landfläche in Quadratmetern, aus TIGER/Line. "
                    "Ohne Wasser - für eine Flächendichte die richtige Grösse.",
    "water_area_m2": "Wasserfläche in Quadratmetern. Getrennt geführt, weil ein "
                     "Tract am Seeufer sonst künstlich gross wirkt.",
    "centroid_lat": "Breitengrad des Flächenschwerpunkts. Für eine Karte, die "
                    "Punkte statt Flächen zeigt.",
    "centroid_lon": "Längengrad des Flächenschwerpunkts.",
    "geometry": "Der Umriss als WKB. Kein Browser liest das - für eine Karte "
                "schreibt `serving.export_geojson` daraus GeoJSON.",
    "latitude": "Breitengrad des Tatorts, WGS84. `NULL`, wo die Quelle keine "
                "Koordinate liefert.",
    "longitude": "Längengrad des Tatorts, WGS84.",
    "city": "Stadt, kleingeschrieben: `chicago` oder `detroit`.",
    "date": "Kalendertag in Ortszeit der Stadt.",
    "station_id": "GHCN-Kennung der Wetterstation, etwa `USW00094846` "
                  "(Chicago O'Hare).",
    "station_name": "Name der Station, wie NOAA ihn führt.",
    "temp_max_c": "Tageshöchsttemperatur in Grad Celsius. GHCN liefert Zehntel; "
                  "hier aufgelöst.",
    "temp_min_c": "Tagestiefsttemperatur in Grad Celsius.",
    "precipitation_mm": "Niederschlag in Millimetern. **`NULL` heisst nicht "
                        "gemessen, `0` heisst trocken** - der Unterschied "
                        "entscheidet jede Wetterauswertung.",
    "snowfall_mm": "Schneefall in Millimetern. GHCN führt ihn bereits in "
                   "Millimetern, anders als Temperatur und Niederschlag.",
    "quality_flags": "Auffälligkeiten, die **benannt und nicht entfernt** "
                     "werden - etwa `MISSING_MEDIAN_INCOME` oder "
                     "`SUSPECT_SNOWFALL`. Leer, wenn nichts auffiel.",
    "population": "Einwohnerzahl aus der ACS-5-Jahres-Schätzung. Der Nenner "
                  "jeder Rate. `0` kommt vor - Wasserflächen, Flughäfen, "
                  "Industriegebiete.",
    "median_household_income_usd": "Medianes Haushaltseinkommen in Dollar, ACS. "
                                   "`NULL`, wo die Schätzung zu unsicher ist - "
                                   "in Wayne County öfter als in Cook County.",
    "poverty_rate": "Anteil der Menschen unter der Armutsgrenze, 0 bis 1. "
                    "`NULL` bei null Einwohnern statt einer Division durch null.",
    "nibrs_code": "NIBRS-Deliktcode des FBI, etwa `13A`. Die gemeinsame Sprache "
                  "beider Städte - erst über ihn wird IUCR mit MICR vergleichbar.",
    "nibrs_description": "Bezeichnung des NIBRS-Codes, etwa *Aggravated Assault*.",
    "nibrs_group": "`A` oder `B`. Group A meldet NIBRS vollständig, Group B nur "
                   "bei Festnahme.",
    "nibrs_family": "Die ersten beiden Zeichen des Codes. **Keine amtliche "
                    "Gliederung** - zum Gruppieren gehört `nibrs_category`.",
    "crime_against": "Wogegen sich die Tat richtet: `Person`, `Property` oder "
                     "`Society`. Aus der NIBRS-Codeliste.",
    "offense_id": "Schlüssel der Zeile. Chicagos `id`, Detroits "
                  "`incident_entry_id`.",
    "event_id": "Schlüssel des Vorfalls. Ein Vorfall kann mehrere Delikte "
                "umfassen - und ist deshalb **kein** Zeilenschlüssel.",
    "occurred_at_utc": "Tatzeitpunkt in UTC. Die Achse, auf der sich beide "
                       "Städte vergleichen lassen.",
    "occurred_at_local": "Tatzeitpunkt in Ortszeit der Stadt. Für die Frage, "
                         "was *in der Stadt* für eine Uhrzeit war.",
    "source_offense_code": "Der Deliktcode, wie die Quelle ihn führt: Chicagos "
                           "`iucr`, Detroits `state_offense_code` (MICR).",
    "source_offense_description": "Die Deliktbezeichnung der Quelle, unverändert. "
                                  "Bleibt stehen, damit jede Zuordnung "
                                  "nachprüfbar ist.",
    "tract_geoid": "GEOID des Census Tracts, in dem der Punkt liegt - aus dem "
                   "eigenen räumlichen Join, nicht aus der Quelle.",
    "located": "Ob die Zeile einem Tract zugeordnet werden konnte. **Warum "
               "nicht**, sagt `geo_status` in Gold.",
    "arrest": "Ob es zu einer Festnahme kam. Nur Chicago liefert das; bei "
              "Detroit `NULL`.",
    "unfounded": "Ob der Fall als unbegründet zurückgezogen wurde. Nur Detroit "
                 "führt das; die Zeilen bleiben erhalten und werden "
                 "gekennzeichnet statt entfernt.",
    "offense_group_id": "Schlüssel der **Tat**: Vorfall plus Deliktbeschreibung. "
                        "Detroits mehrere Anklagen zu einer Tat teilen ihn.",
    "counts_case": "**Die zählende Zeile je Fall** - die mit dem schwersten "
                   "Delikt (Rangfolge `FALLKORN_RANG`, für beide Städte gleich). "
                   "Chicago führt je Vorfall ein Delikt, Detroit jedes; wer auf "
                   "Chicagos Zählweise vergleicht, filtert hierauf.",
    "mapping_status": "Wie gut die NIBRS-Zuordnung belegt ist: `exact` (ein "
                      "amtliches Dokument), `ambiguous` (wir haben entschieden), "
                      "`fallback_90Z` (Auffangcode), `unmapped`.",
}

# Spalten, deren Bedeutung an der Tabelle haengt.
JE_TABELLE: dict[tuple[str, str], str] = {
    ("crime_offense", "nibrs_match"):
        "Woher die Zuordnung stammt, etwa `nibrs_definition` oder "
        "`micr_manual_1110_2024`. `mapping_status` fasst das zusammen.",
    ("crime_offense", "nibrs_mapped"):
        "Ob überhaupt ein NIBRS-Code gefunden wurde. Feiner beantwortet das "
        "`mapping_status`.",
    ("crime_offense", "occurred_date_local"):
        "Tatdatum in Ortszeit. Der Schlüssel für den Join auf `weather_day`.",
    ("crime_offense", "counts"):
        "**Die zählende Zeile je Tat.** Detroit liefert je Vorfall mehrere "
        "Anklagen; genau eine trägt `true`. Gold nimmt nur diese - sonst "
        "zählte Detroit 3,9 % zu hoch.",
    ("crime_offense", "counts_reason"):
        "Warum diese Zeile zählt oder nicht: `eine_zeile_ist_ein_delikt` "
        "(Chicago), `anklage_ist_die_tat`, `schwerste_anklage`, "
        "`weitere_anklage_zur_selben_tat`.",
    ("place", "place_fips"): "Fünf Ziffern des Orts innerhalb des Bundesstaats.",
    ("place", "name"): "Kurzname des Orts, etwa *Chicago*.",
    ("place", "name_long"): "Vollständiger Name mit Rechtsform, etwa *Chicago city*.",
    ("place", "lsad_code"): "Code der Rechtsform (Legal/Statistical Area "
                            "Description), etwa `25` für *city*.",
    ("place", "lsad_text"): "Die Rechtsform ausgeschrieben.",
    ("place", "class_code"): "FIPS-Klasse des Orts, etwa `C1` für eine "
                             "eingemeindete Gemeinde.",
    ("tract", "tract_code"): "Sechs Ziffern des Tracts innerhalb des County.",
    ("tract", "name"): "Bezeichnung des Tracts, etwa *Census Tract 8400*.",
    ("tract", "population_below_poverty"):
        "Absolute Zahl der Menschen unter der Armutsgrenze. Bleibt erhalten, "
        "auch wo `poverty_rate` `NULL` ist.",
    ("dim_date", "year"): "Kalenderjahr.",
    ("dim_date", "month"): "Monat als Zahl, 1 bis 12.",
    ("dim_date", "quarter"): "Quartal, 1 bis 4.",
    ("dim_date", "day_of_month"): "Tag im Monat, 1 bis 31.",
    ("dim_date", "day_of_week"): "Wochentag als Zahl.",
    ("dim_date", "day_name"): "Wochentag ausgeschrieben, englisch.",
    ("dim_date", "month_name"): "Monat ausgeschrieben, englisch.",
    ("dim_date", "month_start"): "Erster Tag des Monats - zum Gruppieren, ohne "
                                 "in der Abfrage zu rechnen.",
    ("dim_date", "is_weekend"): "Samstag oder Sonntag.",
    ("dim_date", "day_of_year"): "Tag im Jahr, 1 bis 366.",
    ("dim_date", "date"): "Der Kalendertag. **Jeder Tag steht hier**, auch einer "
                          "ohne Delikt - sonst zeigte eine Zeitreihe eine Lücke "
                          "als Nicht-Ereignis.",
    ("dim_offense", "nibrs_category"):
        "Die **amtliche** Deliktgliederung aus dem NIBRS User Manual 2025.0: "
        "28 Group-A- und 10 Group-B-Kategorien. Danach wird gruppiert, nicht "
        "nach `nibrs_family`.",
    ("dim_offense", "federal_only"): "Delikte, die nur Bundesbehörden melden.",
    ("dim_offense", "retired"):
        "Codes, die das FBI zurückgezogen hat, die die MICR-Quellen aber weiter "
        "führen. Sie stehen hier, damit kein Filter über die Dimension Fälle "
        "verliert.",
    ("dim_offense", "replaced_by"): "Der heutige Code, wenn es einen gibt - "
                                    "belegt über die ILCS-Tabelle der Illinois "
                                    "State Police.",
    ("dim_offense", "resolution"):
        "Was der Code heute bedeutet: `current`, `replaced`, `not_an_offense` "
        "oder `unresolved`. Ein `unresolved`-Code in den Falldaten lässt den "
        "Gold-Bau scheitern.",
    ("dim_offense", "retirement_note"): "Der Beleg für die Auflösung, mit "
                                        "Statut.",
    ("dim_tract", "city"):
        "Stadt, der dieser Tract zugerechnet wird - oder `NULL`. **Der Filter, "
        "den jede Auswertung braucht**: `dim_tract` enthält alle Tracts beider "
        "Countys, auch die ausserhalb der Städte.",
    ("dim_tract", "city_geoid"): "GEOID der Stadt aus `silver/place`.",
    ("dim_tract", "city_area_share"):
        "Welcher Anteil der Tractfläche in der Stadt liegt, 0 bis 1. Ueber 0,5 "
        "gehört der Tract zur Stadt (Mehrheitsregel). Der Wert bleibt "
        "erhalten, damit sich auch flächengewichtet rechnen lässt.",
    ("dim_tract", "tract_name"): "Bezeichnung des Tracts.",
    ("fact_offense", "reporting_city"):
        "Die Stadt, deren Polizei den Fall gemeldet hat. **Nicht dasselbe wie "
        "`dim_tract.city`** - die Stadtpolizei erfasst auch jenseits der "
        "Stadtgrenze.",
    ("fact_offense", "date"): "Tatdatum in Ortszeit. Schlüssel auf `dim_date`.",
    ("fact_offense", "hour_of_day"): "Tatstunde in Ortszeit, 0 bis 23.",
    ("fact_offense", "geo_status"):
        "Warum eine Zeile in einer Tract-Auswertung fehlt - oder dass sie nicht "
        "fehlt: `inside_city`, `outside_city` (Tract gehört einer anderen "
        "Gemeinde), `no_tract`, `missing_coordinate`.",

    # --- serving: die vier Vergleichstabellen aus Gold -----------------------
    # Was hier keine Achse ist, existiert hier nicht. Die Quelle der Wahrheit
    # bleibt der Stern; diese Tabellen sind jederzeit daraus neu erzeugbar.
    **{
        (tabelle, "reporting_city"): "Die meldende Stadt - `chicago` oder `detroit`."
        for tabelle in ("comparison_day", "comparison_week", "comparison_month",
                        "partition_quality")
    },
    **{
        (tabelle, "nibrs_category"):
            "Die amtliche NIBRS-Kategorie aus `dim_offense`; `unmapped` für die "
            "Taten ohne Code, damit sie zählbar bleiben."
        for tabelle in ("comparison_day", "comparison_week", "comparison_month")
    },
    **{
        (tabelle, "offenses"):
            "**Taten.** Summiert sich je Stadt auf `fact_offense` - jede Tat "
            "trägt genau eine Kategorie."
        for tabelle in ("comparison_day", "comparison_week", "comparison_month")
    },
    **{
        (tabelle, "cases"):
            "**Fälle.** Summe von `counts_case`; genau eine Zeile je Fall, "
            "deshalb ebenfalls additiv über Kategorien."
        for tabelle in ("comparison_day", "comparison_week", "comparison_month")
    },
    **{
        (tabelle, "days_in_period"):
            "Kalendertage der Periode: 7 je Woche, 28 bis 31 je Monat."
        for tabelle in ("comparison_week", "comparison_month")
    },
    **{
        (tabelle, "days_in_window"):
            "Davon im Zeitfenster der Daten (`min(date)` bis `max(date)` der "
            "Faktentabelle). Kleiner als `days_in_period` heisst **Teilperiode** - "
            "die Woche ab 30.12. hat zwei Tage, nicht sieben."
        for tabelle in ("comparison_week", "comparison_month")
    },
    ("comparison_day", "date"): "Tatdatum in Ortszeit.",
    ("comparison_week", "week_start"): "Montag der Woche (ISO).",
    ("comparison_week", "week_end"): "Sonntag der Woche - auch wenn er ausserhalb des Fensters liegt.",
    ("comparison_month", "month"): "Monatserster.",
    ("comparison_month", "month_end"): "Monatsletzter.",
    ("partition_quality", "month"): "Monatserster - die Partition, über die die Anteile gerechnet sind.",
    ("partition_quality", "offenses"): "Taten in dieser Stadt und diesem Monat.",
    ("partition_quality", "share_exact"): "Anteil `mapping_status = exact` in Prozent.",
    ("partition_quality", "share_ambiguous"): "Anteil `mapping_status = ambiguous` in Prozent.",
    ("partition_quality", "share_fallback_90z"): "Anteil `mapping_status = fallback_90Z` in Prozent.",
    ("partition_quality", "share_unmapped"): "Anteil `mapping_status = unmapped` in Prozent.",
    ("partition_quality", "share_inside_city"): "Anteil `geo_status = inside_city` in Prozent.",
    ("partition_quality", "share_outside_city"): "Anteil `geo_status = outside_city` in Prozent.",
    ("partition_quality", "share_no_tract"): "Anteil `geo_status = no_tract` in Prozent.",
    ("partition_quality", "share_missing_coordinate"): "Anteil `geo_status = missing_coordinate` in Prozent.",
    ("partition_quality", "local_time_ambiguous"):
        "Zahl der Taten in der doppelten Stunde beim Zurückstellen der Uhr "
        "(nur Chicago). Eine Zahl, kein Anteil.",
}


def manifeste() -> list[tuple[str, str, dict]]:
    """Jede gebaute Tabelle mit ihrem Manifest, nach Schicht und Name sortiert."""
    return [
        (t.schicht, t.name, t.manifest)
        for t in tabellen(PROJECT_ROOT / "data", SCHICHTEN)
    ]


def beschreibung(tabelle: str, spalte: str) -> str | None:
    return JE_TABELLE.get((tabelle, spalte)) or GEMEINSAM.get(spalte)


def baue() -> str:
    tabellen = manifeste()
    if not tabellen:
        raise SystemExit(
            "Keine gebauten Tabellen unter data/silver oder data/gold gefunden. "
            "Der Katalog liest die Spalten aus den Manifesten - zuerst bauen."
        )

    fehlend = [
        (schicht, name, spalte)
        for schicht, name, m in tabellen
        for spalte in m.get("schema", {})
        if beschreibung(name, spalte) is None
    ]
    if fehlend:
        zeilen = "\n".join(f"  {s}/{t}.{sp}" for s, t, sp in fehlend)
        raise SystemExit(
            f"{len(fehlend)} Spalten ohne Beschreibung:\n{zeilen}\n\n"
            "In tools/build_feldkatalog.py eintragen - in GEMEINSAM, wenn die "
            "Spalte ueberall dasselbe bedeutet, sonst in JE_TABELLE."
        )

    spalten_gesamt = sum(len(m.get("schema", {})) for _, _, m in tabellen)
    teile = [
        "# Feldkatalog",
        "",
        "Was jede Spalte in Silver und Gold bedeutet. **Erzeugt, nicht "
        "geschrieben** — Spaltennamen und Typen kommen aus den Manifesten der",
        "gebauten Tabellen, die Bedeutung aus "
        "[`tools/build_feldkatalog.py`](../tools/build_feldkatalog.py).",
        "",
        "```bash",
        "python tools/build_feldkatalog.py",
        "```",
        "",
        f"**{spalten_gesamt} Spalten in {len(tabellen)} Tabellen.** Kommt eine "
        "dazu, scheitert der Lauf und nennt sie: Wer eine Spalte hinzufügt,",
        "soll einen Satz darüber schreiben müssen. `tests/test_feldkatalog.py` "
        "prüft, dass der Katalog vollständig und reproduzierbar ist.",
        "",
        "Die Rohschichten stehen hier nicht: **Bronze deutet nicht**, seine "
        "Spalten sind die der Quelle. Was sie bedeuten, sagen die",
        "Quellnotebooks 01, 11, 21 und 22.",
        "",
    ]

    for schicht in SCHICHTEN:
        dieser = [(n, m) for s, n, m in tabellen if s == schicht]
        if not dieser:
            continue
        teile += [f"## {schicht}", ""]
        for name, m in dieser:
            granularitaet = m.get("grain", "—")
            zeilen = m.get("row_count") or m.get("rows")
            kopf = f"### `{name}`"
            teile += [kopf, ""]
            teile.append(f"Eine Zeile ist: **{granularitaet}**."
                         + (f" {zeilen:,} Zeilen.".replace(",", "'") if zeilen else ""))
            teile += ["", "| Spalte | Typ | Bedeutung |", "| --- | --- | --- |"]
            for spalte, typ in m.get("schema", {}).items():
                teile.append(
                    f"| `{spalte}` | `{typ}` | {beschreibung(name, spalte)} |"
                )
            teile.append("")
    return "\n".join(teile).rstrip("\n") + "\n"


def main() -> int:
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    ZIEL.write_text(baue(), encoding="utf-8")
    print(f"{ZIEL.relative_to(PROJECT_ROOT)} geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
