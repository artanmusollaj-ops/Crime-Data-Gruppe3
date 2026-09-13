# Feldkatalog

Was jede Spalte in Silver und Gold bedeutet. **Erzeugt, nicht geschrieben** — Spaltennamen und Typen kommen aus den Manifesten der
gebauten Tabellen, die Bedeutung aus [`tools/build_feldkatalog.py`](../tools/build_feldkatalog.py).

```bash
python tools/build_feldkatalog.py
```

**133 Spalten in 9 Tabellen.** Kommt eine dazu, scheitert der Lauf und nennt sie: Wer eine Spalte hinzufügt,
soll einen Satz darüber schreiben müssen. `tests/test_feldkatalog.py` prüft, dass der Katalog vollständig und reproduzierbar ist.

Die Rohschichten stehen hier nicht: **Bronze deutet nicht**, seine Spalten sind die der Quelle. Was sie bedeuten, sagen die
Quellnotebooks 01, 11, 21 und 22.

## silver

### `crime_offense`

Eine Zeile ist: **eine Anklage; je Tat ist eine Zeile mit counts markiert, je Fall eine mit counts_case**. 347'957 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `city` | `VARCHAR` | Stadt, kleingeschrieben: `chicago` oder `detroit`. |
| `offense_id` | `VARCHAR` | Schlüssel der Zeile. Chicagos `id`, Detroits `incident_entry_id`. |
| `event_id` | `VARCHAR` | Schlüssel des Vorfalls. Ein Vorfall kann mehrere Delikte umfassen - und ist deshalb **kein** Zeilenschlüssel. |
| `occurred_at_utc` | `TIMESTAMP` | Tatzeitpunkt in UTC. Die Achse, auf der sich beide Städte vergleichen lassen. |
| `occurred_at_local` | `TIMESTAMP` | Tatzeitpunkt in Ortszeit der Stadt. Für die Frage, was *in der Stadt* für eine Uhrzeit war. |
| `occurred_date_local` | `DATE` | Tatdatum in Ortszeit. Der Schlüssel für den Join auf `weather_day`. |
| `source_offense_code` | `VARCHAR` | Der Deliktcode, wie die Quelle ihn führt: Chicagos `iucr`, Detroits `state_offense_code` (MICR). |
| `source_offense_description` | `VARCHAR` | Die Deliktbezeichnung der Quelle, unverändert. Bleibt stehen, damit jede Zuordnung nachprüfbar ist. |
| `nibrs_code` | `VARCHAR` | NIBRS-Deliktcode des FBI, etwa `13A`. Die gemeinsame Sprache beider Städte - erst über ihn wird IUCR mit MICR vergleichbar. |
| `nibrs_description` | `VARCHAR` | Bezeichnung des NIBRS-Codes, etwa *Aggravated Assault*. |
| `nibrs_group` | `VARCHAR` | `A` oder `B`. Group A meldet NIBRS vollständig, Group B nur bei Festnahme. |
| `crime_against` | `VARCHAR` | Wogegen sich die Tat richtet: `Person`, `Property` oder `Society`. Aus der NIBRS-Codeliste. |
| `nibrs_match` | `VARCHAR` | Woher die Zuordnung stammt, etwa `nibrs_definition` oder `micr_manual_1110_2024`. `mapping_status` fasst das zusammen. |
| `nibrs_mapped` | `BOOLEAN` | Ob überhaupt ein NIBRS-Code gefunden wurde. Feiner beantwortet das `mapping_status`. |
| `mapping_status` | `VARCHAR` | Wie gut die NIBRS-Zuordnung belegt ist: `exact` (ein amtliches Dokument), `ambiguous` (wir haben entschieden), `fallback_90Z` (Auffangcode), `unmapped`. |
| `latitude` | `DOUBLE` | Breitengrad des Tatorts, WGS84. `NULL`, wo die Quelle keine Koordinate liefert. |
| `longitude` | `DOUBLE` | Längengrad des Tatorts, WGS84. |
| `tract_geoid` | `VARCHAR` | GEOID des Census Tracts, in dem der Punkt liegt - aus dem eigenen räumlichen Join, nicht aus der Quelle. |
| `located` | `BOOLEAN` | Ob die Zeile einem Tract zugeordnet werden konnte. **Warum nicht**, sagt `geo_status` in Gold. |
| `arrest` | `BOOLEAN` | Ob es zu einer Festnahme kam. Nur Chicago liefert das; bei Detroit `NULL`. |
| `unfounded` | `BOOLEAN` | Ob der Fall als unbegründet zurückgezogen wurde. Nur Detroit führt das; die Zeilen bleiben erhalten und werden gekennzeichnet statt entfernt. |
| `offense_group_id` | `VARCHAR` | Schlüssel der **Tat**: Vorfall plus Deliktbeschreibung. Detroits mehrere Anklagen zu einer Tat teilen ihn. |
| `counts` | `BOOLEAN` | **Die zählende Zeile je Tat.** Detroit liefert je Vorfall mehrere Anklagen; genau eine trägt `true`. Gold nimmt nur diese - sonst zählte Detroit 3,9 % zu hoch. |
| `counts_reason` | `VARCHAR` | Warum diese Zeile zählt oder nicht: `eine_zeile_ist_ein_delikt` (Chicago), `anklage_ist_die_tat`, `schwerste_anklage`, `weitere_anklage_zur_selben_tat`. |
| `counts_case` | `BOOLEAN` | **Die zählende Zeile je Fall** - die mit dem schwersten Delikt (Rangfolge `FALLKORN_RANG`, für beide Städte gleich). Chicago führt je Vorfall ein Delikt, Detroit jedes; wer auf Chicagos Zählweise vergleicht, filtert hierauf. |

### `place`

Eine Zeile ist: **ein Ort (Census Place)**. 2'206 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `geoid` | `VARCHAR` | Census-GEOID der Raumeinheit, die sie eindeutig macht. Der Schlüssel, über den Delikte, Einwohner und Geometrie zusammenfinden. |
| `state_fips` | `VARCHAR` | Zwei Ziffern des Bundesstaats: `17` Illinois, `26` Michigan. |
| `state_name` | `VARCHAR` | Name des Bundesstaats, kleingeschrieben. |
| `place_fips` | `VARCHAR` | Fünf Ziffern des Orts innerhalb des Bundesstaats. |
| `name` | `VARCHAR` | Kurzname des Orts, etwa *Chicago*. |
| `name_long` | `VARCHAR` | Vollständiger Name mit Rechtsform, etwa *Chicago city*. |
| `lsad_code` | `VARCHAR` | Code der Rechtsform (Legal/Statistical Area Description), etwa `25` für *city*. |
| `lsad_text` | `VARCHAR` | Die Rechtsform ausgeschrieben. |
| `class_code` | `VARCHAR` | FIPS-Klasse des Orts, etwa `C1` für eine eingemeindete Gemeinde. |
| `land_area_m2` | `BIGINT` | Landfläche in Quadratmetern, aus TIGER/Line. Ohne Wasser - für eine Flächendichte die richtige Grösse. |
| `water_area_m2` | `BIGINT` | Wasserfläche in Quadratmetern. Getrennt geführt, weil ein Tract am Seeufer sonst künstlich gross wirkt. |
| `centroid_lat` | `DOUBLE` | Breitengrad des Flächenschwerpunkts. Für eine Karte, die Punkte statt Flächen zeigt. |
| `centroid_lon` | `DOUBLE` | Längengrad des Flächenschwerpunkts. |
| `geometry` | `BLOB` | Der Umriss als WKB. Kein Browser liest das - für eine Karte schreibt `serving.export_geojson` daraus GeoJSON. |
| `quality_flags` | `VARCHAR[]` | Auffälligkeiten, die **benannt und nicht entfernt** werden - etwa `MISSING_MEDIAN_INCOME` oder `SUSPECT_SNOWFALL`. Leer, wenn nichts auffiel. |

### `tract`

Eine Zeile ist: **ein Census Tract**. 6'282 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `geoid` | `VARCHAR` | Census-GEOID der Raumeinheit, die sie eindeutig macht. Der Schlüssel, über den Delikte, Einwohner und Geometrie zusammenfinden. |
| `state_fips` | `VARCHAR` | Zwei Ziffern des Bundesstaats: `17` Illinois, `26` Michigan. |
| `state_name` | `VARCHAR` | Name des Bundesstaats, kleingeschrieben. |
| `county_fips` | `VARCHAR` | Drei Ziffern des County innerhalb des Bundesstaats: `031` Cook (Chicago), `163` Wayne (Detroit). |
| `tract_code` | `VARCHAR` | Sechs Ziffern des Tracts innerhalb des County. |
| `name` | `VARCHAR` | Bezeichnung des Tracts, etwa *Census Tract 8400*. |
| `land_area_m2` | `BIGINT` | Landfläche in Quadratmetern, aus TIGER/Line. Ohne Wasser - für eine Flächendichte die richtige Grösse. |
| `water_area_m2` | `BIGINT` | Wasserfläche in Quadratmetern. Getrennt geführt, weil ein Tract am Seeufer sonst künstlich gross wirkt. |
| `centroid_lat` | `DOUBLE` | Breitengrad des Flächenschwerpunkts. Für eine Karte, die Punkte statt Flächen zeigt. |
| `centroid_lon` | `DOUBLE` | Längengrad des Flächenschwerpunkts. |
| `geometry` | `BLOB` | Der Umriss als WKB. Kein Browser liest das - für eine Karte schreibt `serving.export_geojson` daraus GeoJSON. |
| `population` | `BIGINT` | Einwohnerzahl aus der ACS-5-Jahres-Schätzung. Der Nenner jeder Rate. `0` kommt vor - Wasserflächen, Flughäfen, Industriegebiete. |
| `median_household_income_usd` | `BIGINT` | Medianes Haushaltseinkommen in Dollar, ACS. `NULL`, wo die Schätzung zu unsicher ist - in Wayne County öfter als in Cook County. |
| `population_below_poverty` | `BIGINT` | Absolute Zahl der Menschen unter der Armutsgrenze. Bleibt erhalten, auch wo `poverty_rate` `NULL` ist. |
| `poverty_rate` | `DOUBLE` | Anteil der Menschen unter der Armutsgrenze, 0 bis 1. `NULL` bei null Einwohnern statt einer Division durch null. |
| `quality_flags` | `VARCHAR[]` | Auffälligkeiten, die **benannt und nicht entfernt** werden - etwa `MISSING_MEDIAN_INCOME` oder `SUSPECT_SNOWFALL`. Leer, wenn nichts auffiel. |

### `weather_day`

Eine Zeile ist: **eine Stadt an einem Tag**. 55'449 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `city` | `VARCHAR` | Stadt, kleingeschrieben: `chicago` oder `detroit`. |
| `date` | `DATE` | Kalendertag in Ortszeit der Stadt. |
| `station_id` | `VARCHAR` | GHCN-Kennung der Wetterstation, etwa `USW00094846` (Chicago O'Hare). |
| `station_name` | `VARCHAR` | Name der Station, wie NOAA ihn führt. |
| `temp_max_c` | `DOUBLE` | Tageshöchsttemperatur in Grad Celsius. GHCN liefert Zehntel; hier aufgelöst. |
| `temp_min_c` | `DOUBLE` | Tagestiefsttemperatur in Grad Celsius. |
| `precipitation_mm` | `DOUBLE` | Niederschlag in Millimetern. **`NULL` heisst nicht gemessen, `0` heisst trocken** - der Unterschied entscheidet jede Wetterauswertung. |
| `snowfall_mm` | `DOUBLE` | Schneefall in Millimetern. GHCN führt ihn bereits in Millimetern, anders als Temperatur und Niederschlag. |
| `precipitation_trace` | `BOOLEAN` | Spurenmenge Niederschlag - messbar, aber unter der Auflösung. `precipitation_mm = 0` mit diesem Flag heisst **nicht** trocken. |
| `snowfall_trace` | `BOOLEAN` | Spurenmenge Schnee, analog. |
| `quality_flags` | `VARCHAR[]` | Auffälligkeiten, die **benannt und nicht entfernt** werden - etwa `MISSING_MEDIAN_INCOME` oder `SUSPECT_SNOWFALL`. Leer, wenn nichts auffiel. |

## gold

### `dim_city_day`

Eine Zeile ist: **eine Stadt an einem Tag**. 732 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `city` | `VARCHAR` | Stadt, kleingeschrieben: `chicago` oder `detroit`. |
| `date` | `DATE` | Kalendertag in Ortszeit der Stadt. |
| `station_id` | `VARCHAR` | GHCN-Kennung der Wetterstation, etwa `USW00094846` (Chicago O'Hare). |
| `station_name` | `VARCHAR` | Name der Station, wie NOAA ihn führt. |
| `temp_max_c` | `DOUBLE` | Tageshöchsttemperatur in Grad Celsius. GHCN liefert Zehntel; hier aufgelöst. |
| `temp_min_c` | `DOUBLE` | Tagestiefsttemperatur in Grad Celsius. |
| `precipitation_mm` | `DOUBLE` | Niederschlag in Millimetern. **`NULL` heisst nicht gemessen, `0` heisst trocken** - der Unterschied entscheidet jede Wetterauswertung. |
| `snowfall_mm` | `DOUBLE` | Schneefall in Millimetern. GHCN führt ihn bereits in Millimetern, anders als Temperatur und Niederschlag. |
| `quality_flags` | `VARCHAR[]` | Auffälligkeiten, die **benannt und nicht entfernt** werden - etwa `MISSING_MEDIAN_INCOME` oder `SUSPECT_SNOWFALL`. Leer, wenn nichts auffiel. |

### `dim_date`

Eine Zeile ist: **ein Kalendertag**. 366 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `date` | `DATE` | Der Kalendertag. **Jeder Tag steht hier**, auch einer ohne Delikt - sonst zeigte eine Zeitreihe eine Lücke als Nicht-Ereignis. |
| `year` | `BIGINT` | Kalenderjahr. |
| `month` | `BIGINT` | Monat als Zahl, 1 bis 12. |
| `quarter` | `BIGINT` | Quartal, 1 bis 4. |
| `day_of_month` | `BIGINT` | Tag im Monat, 1 bis 31. |
| `day_of_week` | `BIGINT` | Wochentag als Zahl. |
| `day_name` | `VARCHAR` | Wochentag ausgeschrieben, englisch. |
| `month_name` | `VARCHAR` | Monat ausgeschrieben, englisch. |
| `month_start` | `DATE` | Erster Tag des Monats - zum Gruppieren, ohne in der Abfrage zu rechnen. |
| `is_weekend` | `BOOLEAN` | Samstag oder Sonntag. |
| `day_of_year` | `BIGINT` | Tag im Jahr, 1 bis 366. |

### `dim_offense`

Eine Zeile ist: **ein NIBRS-Delikt**. 85 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `nibrs_code` | `VARCHAR` | NIBRS-Deliktcode des FBI, etwa `13A`. Die gemeinsame Sprache beider Städte - erst über ihn wird IUCR mit MICR vergleichbar. |
| `nibrs_description` | `VARCHAR` | Bezeichnung des NIBRS-Codes, etwa *Aggravated Assault*. |
| `nibrs_category` | `VARCHAR` | Die **amtliche** Deliktgliederung aus dem NIBRS User Manual 2025.0: 28 Group-A- und 10 Group-B-Kategorien. Danach wird gruppiert, nicht nach `nibrs_family`. |
| `nibrs_family` | `VARCHAR` | Die ersten beiden Zeichen des Codes. **Keine amtliche Gliederung** - zum Gruppieren gehört `nibrs_category`. |
| `nibrs_group` | `VARCHAR` | `A` oder `B`. Group A meldet NIBRS vollständig, Group B nur bei Festnahme. |
| `crime_against` | `VARCHAR` | Wogegen sich die Tat richtet: `Person`, `Property` oder `Society`. Aus der NIBRS-Codeliste. |
| `federal_only` | `BOOLEAN` | Delikte, die nur Bundesbehörden melden. |
| `retired` | `BOOLEAN` | Codes, die das FBI zurückgezogen hat, die die MICR-Quellen aber weiter führen. Sie stehen hier, damit kein Filter über die Dimension Fälle verliert. |
| `replaced_by` | `VARCHAR` | Der heutige Code, wenn es einen gibt - belegt über die ILCS-Tabelle der Illinois State Police. |
| `resolution` | `VARCHAR` | Was der Code heute bedeutet: `current`, `replaced`, `not_an_offense` oder `unresolved`. Ein `unresolved`-Code in den Falldaten lässt den Gold-Bau scheitern. |
| `retirement_note` | `VARCHAR` | Der Beleg für die Auflösung, mit Statut. |

### `dim_tract`

Eine Zeile ist: **ein Census Tract**. 6'282 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `geoid` | `VARCHAR` | Census-GEOID der Raumeinheit, die sie eindeutig macht. Der Schlüssel, über den Delikte, Einwohner und Geometrie zusammenfinden. |
| `city` | `VARCHAR` | Stadt, der dieser Tract zugerechnet wird - oder `NULL`. **Der Filter, den jede Auswertung braucht**: `dim_tract` enthält alle Tracts beider Countys, auch die ausserhalb der Städte. |
| `city_geoid` | `VARCHAR` | GEOID der Stadt aus `silver/place`. |
| `city_area_share` | `DOUBLE` | Welcher Anteil der Tractfläche in der Stadt liegt, 0 bis 1. Ueber 0,5 gehört der Tract zur Stadt (Mehrheitsregel). Der Wert bleibt erhalten, damit sich auch flächengewichtet rechnen lässt. |
| `state_fips` | `VARCHAR` | Zwei Ziffern des Bundesstaats: `17` Illinois, `26` Michigan. |
| `state_name` | `VARCHAR` | Name des Bundesstaats, kleingeschrieben. |
| `county_fips` | `VARCHAR` | Drei Ziffern des County innerhalb des Bundesstaats: `031` Cook (Chicago), `163` Wayne (Detroit). |
| `tract_name` | `VARCHAR` | Bezeichnung des Tracts. |
| `population` | `BIGINT` | Einwohnerzahl aus der ACS-5-Jahres-Schätzung. Der Nenner jeder Rate. `0` kommt vor - Wasserflächen, Flughäfen, Industriegebiete. |
| `median_household_income_usd` | `BIGINT` | Medianes Haushaltseinkommen in Dollar, ACS. `NULL`, wo die Schätzung zu unsicher ist - in Wayne County öfter als in Cook County. |
| `poverty_rate` | `DOUBLE` | Anteil der Menschen unter der Armutsgrenze, 0 bis 1. `NULL` bei null Einwohnern statt einer Division durch null. |
| `land_area_m2` | `BIGINT` | Landfläche in Quadratmetern, aus TIGER/Line. Ohne Wasser - für eine Flächendichte die richtige Grösse. |
| `centroid_lat` | `DOUBLE` | Breitengrad des Flächenschwerpunkts. Für eine Karte, die Punkte statt Flächen zeigt. |
| `centroid_lon` | `DOUBLE` | Längengrad des Flächenschwerpunkts. |

### `fact_offense`

Eine Zeile ist: **eine Tat**. 344'617 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `offense_id` | `VARCHAR` | Schlüssel der Zeile. Chicagos `id`, Detroits `incident_entry_id`. |
| `event_id` | `VARCHAR` | Schlüssel des Vorfalls. Ein Vorfall kann mehrere Delikte umfassen - und ist deshalb **kein** Zeilenschlüssel. |
| `reporting_city` | `VARCHAR` | Die Stadt, deren Polizei den Fall gemeldet hat. **Nicht dasselbe wie `dim_tract.city`** - die Stadtpolizei erfasst auch jenseits der Stadtgrenze. |
| `occurred_at_utc` | `TIMESTAMP` | Tatzeitpunkt in UTC. Die Achse, auf der sich beide Städte vergleichen lassen. |
| `occurred_at_local` | `TIMESTAMP` | Tatzeitpunkt in Ortszeit der Stadt. Für die Frage, was *in der Stadt* für eine Uhrzeit war. |
| `date` | `DATE` | Tatdatum in Ortszeit. Schlüssel auf `dim_date`. |
| `hour_of_day` | `BIGINT` | Tatstunde in Ortszeit, 0 bis 23. |
| `tract_geoid` | `VARCHAR` | GEOID des Census Tracts, in dem der Punkt liegt - aus dem eigenen räumlichen Join, nicht aus der Quelle. |
| `nibrs_code` | `VARCHAR` | NIBRS-Deliktcode des FBI, etwa `13A`. Die gemeinsame Sprache beider Städte - erst über ihn wird IUCR mit MICR vergleichbar. |
| `nibrs_family` | `VARCHAR` | Die ersten beiden Zeichen des Codes. **Keine amtliche Gliederung** - zum Gruppieren gehört `nibrs_category`. |
| `source_offense_code` | `VARCHAR` | Der Deliktcode, wie die Quelle ihn führt: Chicagos `iucr`, Detroits `state_offense_code` (MICR). |
| `source_offense_description` | `VARCHAR` | Die Deliktbezeichnung der Quelle, unverändert. Bleibt stehen, damit jede Zuordnung nachprüfbar ist. |
| `latitude` | `DOUBLE` | Breitengrad des Tatorts, WGS84. `NULL`, wo die Quelle keine Koordinate liefert. |
| `longitude` | `DOUBLE` | Längengrad des Tatorts, WGS84. |
| `located` | `BOOLEAN` | Ob die Zeile einem Tract zugeordnet werden konnte. **Warum nicht**, sagt `geo_status` in Gold. |
| `mapping_status` | `VARCHAR` | Wie gut die NIBRS-Zuordnung belegt ist: `exact` (ein amtliches Dokument), `ambiguous` (wir haben entschieden), `fallback_90Z` (Auffangcode), `unmapped`. |
| `geo_status` | `VARCHAR` | Warum eine Zeile in einer Tract-Auswertung fehlt - oder dass sie nicht fehlt: `inside_city`, `outside_city` (Tract gehört einer anderen Gemeinde), `no_tract`, `missing_coordinate`. |
| `arrest` | `BOOLEAN` | Ob es zu einer Festnahme kam. Nur Chicago liefert das; bei Detroit `NULL`. |
| `unfounded` | `BOOLEAN` | Ob der Fall als unbegründet zurückgezogen wurde. Nur Detroit führt das; die Zeilen bleiben erhalten und werden gekennzeichnet statt entfernt. |
| `offense_group_id` | `VARCHAR` | Schlüssel der **Tat**: Vorfall plus Deliktbeschreibung. Detroits mehrere Anklagen zu einer Tat teilen ihn. |
| `counts_case` | `BOOLEAN` | **Die zählende Zeile je Fall** - die mit dem schwersten Delikt (Rangfolge `FALLKORN_RANG`, für beide Städte gleich). Chicago führt je Vorfall ein Delikt, Detroit jedes; wer auf Chicagos Zählweise vergleicht, filtert hierauf. |
