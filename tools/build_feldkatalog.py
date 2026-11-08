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
from storage import TABELLENSCHICHTEN  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ZIEL = PROJECT_ROOT / "docs" / "feldkatalog.md"

# serving seit 17.9.2026: die vier Vergleichstabellen aus build_comparison.
# Die Liste steht kanonisch in ``storage.backend``; hier ist sie die Auswahl
# daraus. Die Reihenfolge ist dieselbe und bestimmt die Abschnitte im Katalog.
SCHICHTEN = TABELLENSCHICHTEN

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
    "vintage": "Der Jahrgang der ACS-5-Jahres-Schätzung, aus der die Werte "
               "dieser Zeile stammen. Teil des Schlüssels: Ein Tract steht "
               "hier so oft, wie Vintages geladen sind.",
    "population": "Einwohnerzahl aus der ACS-5-Jahres-Schätzung. Der Nenner "
                  "jeder Rate. `0` kommt vor - Wasserflächen, Flughäfen, "
                  "Industriegebiete. In Gold liegt sie **je Vintage** in "
                  "`dim_tract_acs`, nicht in `dim_tract`.",
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
    "source_offense_description": "Die Deliktbezeichnung der Quelle. Detroit "
                                  "liefert sie in einem Feld; für Chicago "
                                  "stehen **beide IUCR-Hälften**, getrennt "
                                  "durch `: ` — `BATTERY: SIMPLE`. Die zweite "
                                  "allein war bei 23,7 % der Chicagoer Zeilen "
                                  "mehrdeutig (Silver-Vertrag 3). Bleibt "
                                  "stehen, damit jede Zuordnung nachprüfbar "
                                  "ist.",
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
    # --- source_change: die Bewegung der Quellen -------------------------
    #
    # Eine Zeile ist ein geaendertes Feld, nicht eine geaenderte Zeile. Ein
    # Delikt, an dem sich drei Felder bewegt haben, steht dreimal darin.
    ("source_change", "vorher_run_id"):
        "Der **aeltere** der beiden Vollabzuege, gegen den verglichen wurde.",
    ("source_change", "run_id"):
        "Der **neuere** der beiden Vollabzuege. Zusammen mit "
        "`vorher_run_id` ist das das Vergleichspaar; verglichen werden nur "
        "aufeinanderfolgende Paare, damit jede Bewegung genau einmal zaehlt.",
    ("source_change", "vorher_am"):
        "Wann der aeltere Vollabzug begann - die untere Grenze des Fensters, "
        "in dem die Aenderung geschah.",
    ("source_change", "beobachtet_am"):
        "Wann der neuere Vollabzug begann - die obere Grenze. Nicht der "
        "Zeitpunkt der Aenderung: Der liegt irgendwo dazwischen, und genau "
        "dafuer gibt es `zuerst_gesehen_am`.",
    ("source_change", "art"):
        "Welche Art von Bewegung. `geaendert`: etwas ausserhalb von Rauschen "
        "und Zeitstempeln hat sich bewegt. `beruehrt`: **nur** Zeitstempel - "
        "die Quelle hat die Zeile angefasst, ohne dass sich fachlich etwas "
        "aenderte. `neu` und `verschwunden`: der Schluessel steht im einen "
        "Schnappschuss und im anderen nicht. `unveraendert`: eine "
        "Markierungszeile ohne `offense_id` fuer ein Paar, in dem sich nichts "
        "bewegt hat - ohne sie waere *nichts gefunden* nicht von *noch nicht "
        "verglichen* zu unterscheiden.",
    ("source_change", "feld"):
        "Das Quellfeld, das sich bewegt hat - in den Begriffen der Quelle, "
        "nicht in denen von Silver. Leer bei `neu`, `verschwunden` und "
        "`unveraendert`: Dort bewegt sich kein einzelnes Feld.",
    ("source_change", "wert_alt"):
        "Der Wert im aelteren Schnappschuss, getrimmt und als Text. "
        "Getrimmt wird jedes Feld: Von 160 Aenderungen an "
        "`offense_description` waren 150 reine Leerzeichen, weil die Quelle "
        "angefangen hatte, auf feste Breite aufzufuellen.",
    ("source_change", "wert_neu"):
        "Der Wert im neueren Schnappschuss, gleich behandelt.",
    ("source_change", "zuerst_gesehen_in"):
        "Das **erste** Delta zwischen den beiden Vollabzuegen, das diesen "
        "Schluessel trug. Es grenzt die Aenderung ein: Bei Monatsabstand wird "
        "aus *irgendwann in dreissig Tagen* ein Tag. Leer, wenn `datierung` "
        "nicht `delta` ist.",
    ("source_change", "zuerst_gesehen_am"):
        "Wann dieses Delta lief - die **obere Schranke** fuer den Zeitpunkt "
        "der Aenderung, nicht der Zeitpunkt selbst.",
    ("source_change", "datierung"):
        "Wie verlaesslich die Datierung ist, in drei Zustaenden. `delta`: Ein "
        "Delta im Fenster trug den Schluessel. `kein_delta`: Deltas lagen "
        "vor, keines trug ihn - das kann heissen, dass die Quelle die "
        "Aenderung nicht angemeldet hat, dass sie nach dem letzten Delta "
        "geschah, oder dass die Zeile schon weg war; die drei sind von hier "
        "aus nicht zu trennen. `nicht_datierbar`: kein lesbares Delta liegt "
        "im Fenster. Leer bei der Markierungszeile - ohne Schluessel gibt es "
        "nichts zu datieren. **Diese Spalte klebt**: Sie nennt den besten "
        "Befund, der je bestimmt wurde, nicht den heutigen. Nachgerechnet "
        "wird, was besser wird - `delta` schlaegt `kein_delta` schlaegt "
        "`nicht_datierbar` -, und nie abwaerts. Sonst haette das Aufraeumen "
        "der Deltas eine einmal bestimmte Datierung wieder geloescht.",
    # Seit Vertrag 4 (8.11.2026): der Zusammenhang. Er klebt wie die
    # Datierung - einmal bestimmt, bleibt er, auch ohne den Schnappschuss.
    ("source_change", "quellcode"):
        "Der Deliktcode der Zeile, wie die Quelle ihn fuehrt: Chicagos `iucr`, "
        "Detroits `state_offense_code`. Aus dem **aelteren** Schnappschuss - "
        "dem Stand, der sich geaendert hat oder verschwunden ist -, bei `neu` "
        "aus dem juengeren. Ohne ihn liesse sich nie mehr sagen, *was* "
        "verschwunden ist: Der Inhalt einer geloeschten Zeile steht in keinem "
        "spaeteren Stand. Leer, wenn der Schnappschuss schon aufgeraeumt war, "
        "als die Spalte dazukam.",
    ("source_change", "quellkategorie"):
        "Die lesbare Deliktart der Quelle: Chicagos `primary_type`, Detroits "
        "`offense_category`. Gleiche Herkunft wie `quellcode`.",
    ("source_change", "bestand_vorher"):
        "Wie viele Schluessel der aeltere Schnappschuss traegt - der Nenner "
        "jeder Rate. Steht in jeder Zeile des Paares, auch in der "
        "Markierungszeile.",
    ("source_change", "bestand_nachher"):
        "Wie viele Schluessel der neuere Schnappschuss traegt.",

    # --- source_movement: die Quellbewegung im Release ----------------------
    ("source_movement", "previous_run_id"):
        "Der aeltere Vollabzug des Paares (`silver/source_change.vorher_run_id`).",
    ("source_movement", "run_id"):
        "Der neuere Vollabzug des Paares.",
    ("source_movement", "previous_snapshot_at"):
        "Wann der aeltere Vollabzug begann - die untere Grenze des Fensters.",
    ("source_movement", "snapshot_at"):
        "Wann der neuere Vollabzug begann - die obere Grenze. Eine Bewegung "
        "geschah irgendwann dazwischen.",
    ("source_movement", "change_type"):
        "`changed` (Inhalt bewegt), `touched` (nur Zeitstempel bewegt), "
        "`added` (neu im juengeren Abzug), `removed` (fehlt im juengeren "
        "Abzug), `unchanged` (Markierungszeile eines ruhigen Paares). Die "
        "Arten aus Silver, uebersetzt; eine unbekannte bricht den Bau ab.",
    ("source_movement", "field"):
        "Das bewegte Quellfeld in den Begriffen der Quelle. Leer bei "
        "`added`, `removed` und `unchanged`.",
    ("source_movement", "is_stamp"):
        "Ob `field` ein Zeitstempel der Quelle ist (Detroit `updated_at`, "
        "`updated_in_ibr_at`, `case_status_updated_at`; Chicago "
        "`updated_on`). Ein bewegter Stempel ist keine Inhaltsaenderung. "
        "Leer, wo kein Feld steht.",
    ("source_movement", "value_old"):
        "Der Wert im aelteren Abzug, getrimmt und als Text.",
    ("source_movement", "value_new"):
        "Der Wert im neueren Abzug, gleich behandelt.",
    ("source_movement", "source_offense_category"):
        "Die lesbare Deliktart der Quelle (Chicagos `primary_type`, Detroits "
        "`offense_category`) - fuer eine verschwundene Zeile die einzige "
        "Auskunft darueber, was sie war.",
    ("source_movement", "nibrs_code"):
        "Die Deliktart auf dem gemeinsamen Vokabular: `source_offense_code` "
        "ueber den heute gueltigen Crosswalk samt Overrides, derselbe wie "
        "fuer `fact_offense`. Erst damit lassen sich die Loeschungen beider "
        "Staedte nach Delikt vergleichen.",
    ("source_movement", "previous_rows"):
        "Schluessel im aelteren Abzug - der Nenner einer Loesch- oder "
        "Aenderungsrate. Je Paar einmal zaehlen, nicht je Zeile.",
    ("source_movement", "snapshot_rows"):
        "Schluessel im neueren Abzug.",
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
        "zählte Detroit 3,8 % zu hoch.",
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
    ("dim_tract", "reference_vintage"):
        "Aus diesem ACS-Vintage stammen Stadtzuordnung, Name, Fläche und "
        "Schwerpunkt. Sie werden **nicht je Jahrgang neu gerechnet**: Ein Tract "
        "soll dauerhaft eine Stadt haben, sonst springt eine Rate aus einem "
        "Grund, der nichts mit Kriminalität zu tun hat. Die Einwohnerzahlen "
        "liegen dagegen je Vintage in `dim_tract_acs` - verbunden wird über "
        "`geoid` **und** `vintage`.",
    ("dim_tract", "city_area_share"):
        "Welcher Anteil der Tractfläche in der Stadt liegt, 0 bis 1. Ueber 0,5 "
        "gehört der Tract zur Stadt (Mehrheitsregel). Der Wert bleibt "
        "erhalten, damit sich auch flächengewichtet rechnen lässt.",
    ("dim_tract", "tract_name"): "Bezeichnung des Tracts.",

    # --- dim_tract_geo: der Umriss, fuer die Karte ------------------------
    #
    # Eigene Tabelle und keine Spalte an dim_tract: Die Dimension deckt beide
    # Countys ab (6'282 Zeilen) und waere mit Umrissen 26 MB statt 194 KB.
    # Diese hier traegt nur die 1'055 Tracts mit Stadt.
    ("dim_tract_geo", "tract_name"): "Bezeichnung des Tracts.",

    # --- rate_tract: die Rate je Tract, fuer die Karte --------------------
    #
    # Keine Gold-Tabelle: Eine Rate je Tract ist eine Aggregation, und Gold
    # aggregiert nicht. Sie entsteht in serving.build_comparison aus
    # derselben Abfrage, die gold_pipeline.raten_je_tract dem Waechter der
    # Ratenkachel stellt - nicht aus einer zweiten.
    #
    # Warum sie ueberhaupt gebraucht wird: Kibanas Karte faerbt eine Flaeche
    # nach einem Feld und kann zwischen zwei verbundenen Feldern nicht
    # rechnen. Eine Karte nach Fallzahlen waere irrefuehrend - die
    # Einwohnerzahl je Tract reicht von 35 bis 13'521 (2024, Median 2'861).
    ("rate_tract", "stadt"):
        "Die **meldende** Stadt (`reporting_city`), nicht die Stadtzuordnung "
        "des Tracts. Auf Tract-Ebene ist die Frage *wer hat das gemeldet*; "
        "`geo_status = 'inside_city'` stellt ohnehin sicher, dass der Tract "
        "im Gebiet dieser Stadt liegt.",
    ("rate_tract", "faelle"):
        "Faelle im Bezugsjahr - Taten mit `counts_case`. Die Fallebene steht "
        "vorn, weil Chicago je Fall nur das schwerste Delikt erfasst und "
        "Detroit jedes.",
    ("rate_tract", "rate_fallebene"):
        "Faelle je 1'000 Einwohner im Bezugsjahr, auf eine Nachkommastelle. "
        "**Die Zahl, nach der die Karte einfaerbt.**",
    ("rate_tract", "taten"):
        "Taten im Bezugsjahr - jede Zeile von `fact_offense`, ohne den "
        "Fallfilter.",
    ("rate_tract", "rate_tatebene"):
        "Taten je 1'000 Einwohner im Bezugsjahr. Daneben zu lesen, nicht "
        "statt der Fallebene: Der Unterschied zwischen beiden ist der "
        "Erfassungsunterschied der zwei Staedte, nicht ein Unterschied der "
        "Kriminalitaet.",
    ("rate_tract", "einwohner"):
        "Der Nenner: `dim_tract_acs.population` im Vintage, auf den die Tat "
        "zeigt (`population_vintage`). **Tracts ohne Einwohner fehlen in "
        "dieser Tabelle** - fuer sie ist keine Rate definiert, und eine "
        "gezeigte Null liesse sich als Sicherheit lesen, wo in Wirklichkeit "
        "niemand wohnt: Flughaefen, Parks, Gewerbegebiete.",
    ("dim_tract_geo", "boundary_wkt"):
        "Der **Umriss** des Tracts als WKT in EPSG:4269, vereinfacht mit "
        "Douglas-Peucker 0,00002 Grad - rund zwei Meter, und die Flaeche je "
        "Tract verliert dabei 0,0002 Prozent. WKT und nicht WKB oder "
        "GeoJSON, weil Elasticsearch eine WKT-Zeichenkette fuer `geo_shape` "
        "unmittelbar annimmt; alles andere muesste der Lader erst wandeln. "
        "**Keine Kennzahl steht hier** - wer die Flaeche einfaerben will, "
        "verbindet ueber `geoid` mit `fact_offense` und `dim_tract_acs`.",
    ("dim_date", "year_is_complete"):
        "Ob der Jahrgang dieses Tages **ganz** in den Daten liegt — also ob die "
        "Spanne den 1. Januar und den 31. Dezember einschliesst. **Ein "
        "Jahresvergleich filtert darauf**: 2026 hat am 3.10. neun Monate, und "
        "neun Monate gegen zwölf gestellt ergeben einen Rückgang, den es nicht "
        "gibt. Eine Lücke *innerhalb* des Jahres fällt hier nicht auf; die "
        "misst `year_coverage` im Manifest von `fact_offense`, mit "
        "`days_with_offenses` gegen `days_in_year`.",
    ("dim_tract_acs", "geoid"):
        "GEOID des Tracts. Zusammen mit `vintage` der Schlüssel dieser Tabelle.",
    ("fact_offense", "population_vintage"):
        "Welcher ACS-Jahrgang der **Nenner dieser Zeile** ist. Bis 2024 das "
        "eigene Jahr, darüber der jüngste vorhandene: Eine Rate für 2025 ruht "
        "auf der Bevölkerung von 2024. Das steht hier in den Daten statt in "
        "einer Fussnote. Verbunden wird `dim_tract_acs` über `tract_geoid` "
        "**und** diese Spalte - wer nur den Tract verbindet, bekommt je Tract "
        "so viele Zeilen, wie Vintages geladen sind.",
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
            "Davon im Zeitfenster der Daten **dieser Stadt** (`min(date)` bis "
            "`max(date)` der Faktentabelle je `reporting_city`, seit Vertrag 3). "
            "Kleiner als `days_in_period` heisst **Teilperiode** - die Woche ab "
            "30.12. hat zwei Tage, nicht sieben."
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


def manifeste() -> list[tuple[str, str, dict, int]]:
    """Jede gebaute Tabelle mit ihrem Manifest, nach Schicht und Name sortiert.

    **Eine Tabelle, ein Eintrag** - auch wenn sie unter mehreren ``vintage=``
    liegt. ``manifeste.tabellen`` findet je Vintage ein Manifest, und das ist
    dort richtig: Jedes beschreibt seinen eigenen Stand. Fuer einen *Katalog*
    ist es falsch. Am 4.10.2026, nach dem Bau mit vier ACS-Vintages, stand
    ``place`` viermal und ``tract`` viermal im Dokument, mit gleichen Spalten
    und verschiedenen Zeilenzahlen - "285 Spalten in 21 Tabellen" statt 192 in
    15. Der Katalog sagt, was eine Spalte **bedeutet**; das haengt nicht am
    Jahrgang.

    Zusammengelegt wird nur, was zusammenpasst: Weichen die Spalten zweier
    Vintages voneinander ab, bricht der Lauf ab und nennt die Tabelle. Dann ist
    nicht der Katalog zu glaetten, sondern ein Stand neu zu bauen.

    Die vierte Stelle je Eintrag ist die Zahl der Vintages - das Dokument
    schreibt sie neben die Zeilenzahl, damit "25'128 Zeilen" nicht wie eine
    Zeile je Tract aussieht.
    """
    je: dict[tuple[str, str], list] = {}
    for tab in tabellen(PROJECT_ROOT / "data", SCHICHTEN):
        schluessel = (tab.schicht, tab.name)
        if schluessel not in je:
            je[schluessel] = [dict(tab.manifest), 1]
            continue
        erster, anzahl = je[schluessel]
        if erster.get("schema") != tab.manifest.get("schema"):
            raise SystemExit(
                f"{tab.schicht}/{tab.name} hat in zwei Vintages verschiedene "
                "Spalten. Der Katalog beschreibt eine Tabelle, nicht einen "
                "Stand - zuerst neu bauen."
            )
        zeilen = tab.manifest.get("row_count") or tab.manifest.get("rows") or 0
        bisher = erster.get("row_count") or erster.get("rows") or 0
        erster["row_count"] = bisher + zeilen
        erster.pop("rows", None)
        je[schluessel] = [erster, anzahl + 1]
    return [(schicht, name, m, n)
            for (schicht, name), (m, n) in sorted(je.items())]


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
        for schicht, name, m, _ in tabellen
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

    spalten_gesamt = sum(len(m.get("schema", {})) for _, _, m, _ in tabellen)
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
        dieser = [(n, m, v) for s, n, m, v in tabellen if s == schicht]
        if not dieser:
            continue
        teile += [f"## {schicht}", ""]
        for name, m, vintages in dieser:
            granularitaet = m.get("grain", "—")
            zeilen = m.get("row_count") or m.get("rows")
            kopf = f"### `{name}`"
            teile += [kopf, ""]
            # Ueber mehrere Vintages ist die Zeilenzahl eine Summe. Ohne den
            # Zusatz liest sie sich wie eine Zeile je Schluessel, und genau
            # das ist sie dann nicht.
            ueber = (f" {zeilen:,} Zeilen über {vintages} Vintages."
                     if vintages > 1 else f" {zeilen:,} Zeilen.")
            teile.append(f"Eine Zeile ist: **{granularitaet}**."
                         + (ueber.replace(",", "'") if zeilen else ""))
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
