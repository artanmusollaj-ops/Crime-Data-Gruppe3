# Feldkatalog

Was jede Spalte in Silver und Gold bedeutet. **Erzeugt, nicht geschrieben** — Spaltennamen und Typen kommen aus den Manifesten der
gebauten Tabellen, die Bedeutung aus [`tools/build_feldkatalog.py`](../tools/build_feldkatalog.py).

```bash
python tools/build_feldkatalog.py
```

**225 Spalten in 18 Tabellen.** Kommt eine dazu, scheitert der Lauf und nennt sie: Wer eine Spalte hinzufügt,
soll einen Satz darüber schreiben müssen. `tests/test_feldkatalog.py` prüft, dass der Katalog vollständig und reproduzierbar ist.

Die Rohschichten stehen hier nicht: **Bronze deutet nicht**, seine Spalten sind die der Quelle. Was sie bedeuten, sagen die
Quellnotebooks 01, 11, 21 und 22.

## silver

### `crime_offense`

Eine Zeile ist: **eine Anklage; je Tat ist eine Zeile mit counts markiert, je Fall eine mit counts_case**. 1'909'461 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `city` | `VARCHAR` | Stadt, kleingeschrieben: `chicago` oder `detroit`. |
| `offense_id` | `VARCHAR` | Schlüssel der Zeile. Chicagos `id`, Detroits `incident_entry_id`. |
| `event_id` | `VARCHAR` | Schlüssel des Vorfalls. Ein Vorfall kann mehrere Delikte umfassen - und ist deshalb **kein** Zeilenschlüssel. |
| `occurred_at_utc` | `TIMESTAMP` | Tatzeitpunkt in UTC. Die Achse, auf der sich beide Städte vergleichen lassen. |
| `occurred_at_local` | `TIMESTAMP` | Tatzeitpunkt in Ortszeit der Stadt. Für die Frage, was *in der Stadt* für eine Uhrzeit war. |
| `occurred_date_local` | `DATE` | Tatdatum in Ortszeit. Der Schlüssel für den Join auf `weather_day`. |
| `local_time_nonexistent` | `BOOLEAN` | Die Ortszeit gab es **nicht** - der Wechsel zur Sommerzeit. DuckDB rechnet sie als Winterzeit um. |
| `local_time_ambiguous` | `BOOLEAN` | Die Ortszeit gab es **zweimal** - der Wechsel zurück von der Sommerzeit. Betrifft nur Chicago, das Wanduhrzeit ohne Zone liefert; Detroit liefert einen Zeitpunkt und hat den Fall nicht. |
| `source_offense_code` | `VARCHAR` | Der Deliktcode, wie die Quelle ihn führt: Chicagos `iucr`, Detroits `state_offense_code` (MICR). |
| `source_offense_description` | `VARCHAR` | Die Deliktbezeichnung der Quelle. Detroit liefert sie in einem Feld; für Chicago stehen **beide IUCR-Hälften**, getrennt durch `: ` — `BATTERY: SIMPLE`. Die zweite allein war bei 23,7 % der Chicagoer Zeilen mehrdeutig (Silver-Vertrag 3). Bleibt stehen, damit jede Zuordnung nachprüfbar ist. |
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
| `counts` | `BOOLEAN` | **Die zählende Zeile je Tat.** Detroit liefert je Vorfall mehrere Anklagen; genau eine trägt `true`. Gold nimmt nur diese - sonst zählte Detroit 3,8 % zu hoch. |
| `counts_reason` | `VARCHAR` | Warum diese Zeile zählt oder nicht: `eine_zeile_ist_ein_delikt` (Chicago), `anklage_ist_die_tat`, `schwerste_anklage`, `weitere_anklage_zur_selben_tat`. |
| `counts_case` | `BOOLEAN` | **Die zählende Zeile je Fall** - die mit dem schwersten Delikt (Rangfolge `FALLKORN_RANG`, für beide Städte gleich). Chicago führt je Vorfall ein Delikt, Detroit jedes; wer auf Chicagos Zählweise vergleicht, filtert hierauf. |

### `place`

Eine Zeile ist: **ein Ort (Census Place)**. 8'833 Zeilen über 4 Vintages.

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

### `source_change`

Eine Zeile ist: **ein geaendertes Feld einer Zeile zwischen zwei Schnappschuessen**. 95'484 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `city` | `VARCHAR` | Stadt, kleingeschrieben: `chicago` oder `detroit`. |
| `offense_id` | `VARCHAR` | Schlüssel der Zeile. Chicagos `id`, Detroits `incident_entry_id`. |
| `vorher_run_id` | `VARCHAR` | Der **aeltere** der beiden Vollabzuege, gegen den verglichen wurde. |
| `run_id` | `VARCHAR` | Der **neuere** der beiden Vollabzuege. Zusammen mit `vorher_run_id` ist das das Vergleichspaar; verglichen werden nur aufeinanderfolgende Paare, damit jede Bewegung genau einmal zaehlt. |
| `vorher_am` | `TIMESTAMP` | Wann der aeltere Vollabzug begann - die untere Grenze des Fensters, in dem die Aenderung geschah. |
| `beobachtet_am` | `TIMESTAMP` | Wann der neuere Vollabzug begann - die obere Grenze. Nicht der Zeitpunkt der Aenderung: Der liegt irgendwo dazwischen, und genau dafuer gibt es `zuerst_gesehen_am`. |
| `art` | `VARCHAR` | Welche Art von Bewegung. `geaendert`: etwas ausserhalb von Rauschen und Zeitstempeln hat sich bewegt. `beruehrt`: **nur** Zeitstempel - die Quelle hat die Zeile angefasst, ohne dass sich fachlich etwas aenderte. `neu` und `verschwunden`: der Schluessel steht im einen Schnappschuss und im anderen nicht. `unveraendert`: eine Markierungszeile ohne `offense_id` fuer ein Paar, in dem sich nichts bewegt hat - ohne sie waere *nichts gefunden* nicht von *noch nicht verglichen* zu unterscheiden. |
| `feld` | `VARCHAR` | Das Quellfeld, das sich bewegt hat - in den Begriffen der Quelle, nicht in denen von Silver. Leer bei `neu`, `verschwunden` und `unveraendert`: Dort bewegt sich kein einzelnes Feld. |
| `wert_alt` | `VARCHAR` | Der Wert im aelteren Schnappschuss, getrimmt und als Text. Getrimmt wird jedes Feld: Von 160 Aenderungen an `offense_description` waren 150 reine Leerzeichen, weil die Quelle angefangen hatte, auf feste Breite aufzufuellen. |
| `wert_neu` | `VARCHAR` | Der Wert im neueren Schnappschuss, gleich behandelt. |
| `zuerst_gesehen_in` | `VARCHAR` | Das **erste** Delta zwischen den beiden Vollabzuegen, das diesen Schluessel trug. Es grenzt die Aenderung ein: Bei Monatsabstand wird aus *irgendwann in dreissig Tagen* ein Tag. Leer, wenn `datierung` nicht `delta` ist. |
| `zuerst_gesehen_am` | `TIMESTAMP` | Wann dieses Delta lief - die **obere Schranke** fuer den Zeitpunkt der Aenderung, nicht der Zeitpunkt selbst. |
| `datierung` | `VARCHAR` | Wie verlaesslich die Datierung ist, in drei Zustaenden. `delta`: Ein Delta im Fenster trug den Schluessel. `kein_delta`: Deltas lagen vor, keines trug ihn - das kann heissen, dass die Quelle die Aenderung nicht angemeldet hat, dass sie nach dem letzten Delta geschah, oder dass die Zeile schon weg war; die drei sind von hier aus nicht zu trennen. `nicht_datierbar`: kein lesbares Delta liegt im Fenster. Leer bei der Markierungszeile - ohne Schluessel gibt es nichts zu datieren. **Diese Spalte klebt**: Sie nennt den besten Befund, der je bestimmt wurde, nicht den heutigen. Nachgerechnet wird, was besser wird - `delta` schlaegt `kein_delta` schlaegt `nicht_datierbar` -, und nie abwaerts. Sonst haette das Aufraeumen der Deltas eine einmal bestimmte Datierung wieder geloescht. |
| `quellcode` | `VARCHAR` | Der Deliktcode der Zeile, wie die Quelle ihn fuehrt: Chicagos `iucr`, Detroits `state_offense_code`. Aus dem **aelteren** Schnappschuss - dem Stand, der sich geaendert hat oder verschwunden ist -, bei `neu` aus dem juengeren. Ohne ihn liesse sich nie mehr sagen, *was* verschwunden ist: Der Inhalt einer geloeschten Zeile steht in keinem spaeteren Stand. Leer, wenn der Schnappschuss schon aufgeraeumt war, als die Spalte dazukam. |
| `quellkategorie` | `VARCHAR` | Die lesbare Deliktart der Quelle: Chicagos `primary_type`, Detroits `offense_category`. Gleiche Herkunft wie `quellcode`. |
| `bestand_vorher` | `BIGINT` | Wie viele Schluessel der aeltere Schnappschuss traegt - der Nenner jeder Rate. Steht in jeder Zeile des Paares, auch in der Markierungszeile. |
| `bestand_nachher` | `BIGINT` | Wie viele Schluessel der neuere Schnappschuss traegt. |
| `jahrgang` | `INTEGER` | Der Tatjahrgang, den beide Abzuege des Paares tragen - verglichen wird nur innerhalb eines Jahrgangs. Aus dem Manifest des Laufs, nicht aus der Datei. Leer bei Abzuegen aus der Zeit vor der Jahrgangstrennung. |

### `tract`

Eine Zeile ist: **ein Census Tract**. 25'128 Zeilen über 4 Vintages.

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
| `population` | `BIGINT` | Einwohnerzahl aus der ACS-5-Jahres-Schätzung. Der Nenner jeder Rate. `0` kommt vor - Wasserflächen, Flughäfen, Industriegebiete. In Gold liegt sie **je Vintage** in `dim_tract_acs`, nicht in `dim_tract`. |
| `median_household_income_usd` | `INTEGER` | Medianes Haushaltseinkommen in Dollar, ACS. `NULL`, wo die Schätzung zu unsicher ist - in Wayne County öfter als in Cook County. |
| `population_below_poverty` | `INTEGER` | Absolute Zahl der Menschen unter der Armutsgrenze. Bleibt erhalten, auch wo `poverty_rate` `NULL` ist. |
| `poverty_rate` | `DOUBLE` | Anteil der Menschen unter der Armutsgrenze, 0 bis 1. `NULL` bei null Einwohnern statt einer Division durch null. |
| `quality_flags` | `VARCHAR[]` | Auffälligkeiten, die **benannt und nicht entfernt** werden - etwa `MISSING_MEDIAN_INCOME` oder `SUSPECT_SNOWFALL`. Leer, wenn nichts auffiel. |

### `weather_day`

Eine Zeile ist: **eine Stadt an einem Tag**. 55'573 Zeilen.

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

Eine Zeile ist: **eine Stadt an einem Tag**. 4'272 Zeilen.

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

### `dim_date`

Eine Zeile ist: **ein Kalendertag**. 2'140 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `date` | `DATE` | Der Kalendertag. **Jeder Tag steht hier**, auch einer ohne Delikt - sonst zeigte eine Zeitreihe eine Lücke als Nicht-Ereignis. |
| `year` | `SMALLINT` | Kalenderjahr. |
| `month` | `TINYINT` | Monat als Zahl, 1 bis 12. |
| `quarter` | `TINYINT` | Quartal, 1 bis 4. |
| `day_of_month` | `TINYINT` | Tag im Monat, 1 bis 31. |
| `day_of_week` | `TINYINT` | Wochentag als Zahl. |
| `day_name` | `VARCHAR` | Wochentag ausgeschrieben, englisch. |
| `month_name` | `VARCHAR` | Monat ausgeschrieben, englisch. |
| `month_start` | `DATE` | Erster Tag des Monats - zum Gruppieren, ohne in der Abfrage zu rechnen. |
| `is_weekend` | `BOOLEAN` | Samstag oder Sonntag. |
| `day_of_year` | `SMALLINT` | Tag im Jahr, 1 bis 366. |
| `year_is_complete` | `BOOLEAN` | Ob der Jahrgang dieses Tages **ganz** in den Daten liegt — also ob die Spanne den 1. Januar und den 31. Dezember einschliesst. **Ein Jahresvergleich filtert darauf**: 2026 hat am 3.10. neun Monate, und neun Monate gegen zwölf gestellt ergeben einen Rückgang, den es nicht gibt. Eine Lücke *innerhalb* des Jahres fällt hier nicht auf; die misst `year_coverage` im Manifest von `fact_offense`, mit `days_with_offenses` gegen `days_in_year`. |

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
| `reference_vintage` | `SMALLINT` | Aus diesem ACS-Vintage stammen Stadtzuordnung, Name, Fläche und Schwerpunkt. Sie werden **nicht je Jahrgang neu gerechnet**: Ein Tract soll dauerhaft eine Stadt haben, sonst springt eine Rate aus einem Grund, der nichts mit Kriminalität zu tun hat. Die Einwohnerzahlen liegen dagegen je Vintage in `dim_tract_acs` - verbunden wird über `geoid` **und** `vintage`. |
| `land_area_m2` | `BIGINT` | Landfläche in Quadratmetern, aus TIGER/Line. Ohne Wasser - für eine Flächendichte die richtige Grösse. |
| `centroid_lat` | `DOUBLE` | Breitengrad des Flächenschwerpunkts. Für eine Karte, die Punkte statt Flächen zeigt. |
| `centroid_lon` | `DOUBLE` | Längengrad des Flächenschwerpunkts. |

### `dim_tract_acs`

Eine Zeile ist: **ein Census Tract in einem ACS-Vintage**. 25'128 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `geoid` | `VARCHAR` | GEOID des Tracts. Zusammen mit `vintage` der Schlüssel dieser Tabelle. |
| `vintage` | `SMALLINT` | Der Jahrgang der ACS-5-Jahres-Schätzung, aus der die Werte dieser Zeile stammen. Teil des Schlüssels: Ein Tract steht hier so oft, wie Vintages geladen sind. |
| `population` | `BIGINT` | Einwohnerzahl aus der ACS-5-Jahres-Schätzung. Der Nenner jeder Rate. `0` kommt vor - Wasserflächen, Flughäfen, Industriegebiete. In Gold liegt sie **je Vintage** in `dim_tract_acs`, nicht in `dim_tract`. |
| `median_household_income_usd` | `INTEGER` | Medianes Haushaltseinkommen in Dollar, ACS. `NULL`, wo die Schätzung zu unsicher ist - in Wayne County öfter als in Cook County. |
| `poverty_rate` | `DOUBLE` | Anteil der Menschen unter der Armutsgrenze, 0 bis 1. `NULL` bei null Einwohnern statt einer Division durch null. |

### `dim_tract_geo`

Eine Zeile ist: **der Umriss eines Census Tract**. 1'055 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `geoid` | `VARCHAR` | Census-GEOID der Raumeinheit, die sie eindeutig macht. Der Schlüssel, über den Delikte, Einwohner und Geometrie zusammenfinden. |
| `city` | `VARCHAR` | Stadt, kleingeschrieben: `chicago` oder `detroit`. |
| `tract_name` | `VARCHAR` | Bezeichnung des Tracts. |
| `boundary_wkt` | `VARCHAR` | Der **Umriss** des Tracts als WKT in EPSG:4269, vereinfacht mit Douglas-Peucker 0,00002 Grad - rund zwei Meter, und die Flaeche je Tract verliert dabei 0,0002 Prozent. WKT und nicht WKB oder GeoJSON, weil Elasticsearch eine WKT-Zeichenkette fuer `geo_shape` unmittelbar annimmt; alles andere muesste der Lader erst wandeln. **Keine Kennzahl steht hier** - wer die Flaeche einfaerben will, verbindet ueber `geoid` mit `fact_offense` und `dim_tract_acs`. |

### `fact_offense`

Eine Zeile ist: **eine Tat**. 1'887'009 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `offense_id` | `VARCHAR` | Schlüssel der Zeile. Chicagos `id`, Detroits `incident_entry_id`. |
| `event_id` | `VARCHAR` | Schlüssel des Vorfalls. Ein Vorfall kann mehrere Delikte umfassen - und ist deshalb **kein** Zeilenschlüssel. |
| `reporting_city` | `VARCHAR` | Die Stadt, deren Polizei den Fall gemeldet hat. **Nicht dasselbe wie `dim_tract.city`** - die Stadtpolizei erfasst auch jenseits der Stadtgrenze. |
| `occurred_at_utc` | `TIMESTAMP` | Tatzeitpunkt in UTC. Die Achse, auf der sich beide Städte vergleichen lassen. |
| `occurred_at_local` | `TIMESTAMP` | Tatzeitpunkt in Ortszeit der Stadt. Für die Frage, was *in der Stadt* für eine Uhrzeit war. |
| `date` | `DATE` | Tatdatum in Ortszeit. Schlüssel auf `dim_date`. |
| `hour_of_day` | `TINYINT` | Tatstunde in Ortszeit, 0 bis 23. |
| `local_time_ambiguous` | `BOOLEAN` | Die Ortszeit gab es **zweimal** - der Wechsel zurück von der Sommerzeit. Betrifft nur Chicago, das Wanduhrzeit ohne Zone liefert; Detroit liefert einen Zeitpunkt und hat den Fall nicht. |
| `tract_geoid` | `VARCHAR` | GEOID des Census Tracts, in dem der Punkt liegt - aus dem eigenen räumlichen Join, nicht aus der Quelle. |
| `population_vintage` | `SMALLINT` | Welcher ACS-Jahrgang der **Nenner dieser Zeile** ist. Bis 2024 das eigene Jahr, darüber der jüngste vorhandene: Eine Rate für 2025 ruht auf der Bevölkerung von 2024. Das steht hier in den Daten statt in einer Fussnote. Verbunden wird `dim_tract_acs` über `tract_geoid` **und** diese Spalte - wer nur den Tract verbindet, bekommt je Tract so viele Zeilen, wie Vintages geladen sind. |
| `nibrs_code` | `VARCHAR` | NIBRS-Deliktcode des FBI, etwa `13A`. Die gemeinsame Sprache beider Städte - erst über ihn wird IUCR mit MICR vergleichbar. |
| `nibrs_family` | `VARCHAR` | Die ersten beiden Zeichen des Codes. **Keine amtliche Gliederung** - zum Gruppieren gehört `nibrs_category`. |
| `source_offense_code` | `VARCHAR` | Der Deliktcode, wie die Quelle ihn führt: Chicagos `iucr`, Detroits `state_offense_code` (MICR). |
| `source_offense_description` | `VARCHAR` | Die Deliktbezeichnung der Quelle. Detroit liefert sie in einem Feld; für Chicago stehen **beide IUCR-Hälften**, getrennt durch `: ` — `BATTERY: SIMPLE`. Die zweite allein war bei 23,7 % der Chicagoer Zeilen mehrdeutig (Silver-Vertrag 3). Bleibt stehen, damit jede Zuordnung nachprüfbar ist. |
| `latitude` | `DOUBLE` | Breitengrad des Tatorts, WGS84. `NULL`, wo die Quelle keine Koordinate liefert. |
| `longitude` | `DOUBLE` | Längengrad des Tatorts, WGS84. |
| `located` | `BOOLEAN` | Ob die Zeile einem Tract zugeordnet werden konnte. **Warum nicht**, sagt `geo_status` in Gold. |
| `mapping_status` | `VARCHAR` | Wie gut die NIBRS-Zuordnung belegt ist: `exact` (ein amtliches Dokument), `ambiguous` (wir haben entschieden), `fallback_90Z` (Auffangcode), `unmapped`. |
| `geo_status` | `VARCHAR` | Warum eine Zeile in einer Tract-Auswertung fehlt - oder dass sie nicht fehlt: `inside_city`, `outside_city` (Tract gehört einer anderen Gemeinde), `no_tract`, `missing_coordinate`. |
| `arrest` | `BOOLEAN` | Ob es zu einer Festnahme kam. Nur Chicago liefert das; bei Detroit `NULL`. |
| `unfounded` | `BOOLEAN` | Ob der Fall als unbegründet zurückgezogen wurde. Nur Detroit führt das; die Zeilen bleiben erhalten und werden gekennzeichnet statt entfernt. |
| `offense_group_id` | `VARCHAR` | Schlüssel der **Tat**: Vorfall plus Deliktbeschreibung. Detroits mehrere Anklagen zu einer Tat teilen ihn. |
| `counts_case` | `BOOLEAN` | **Die zählende Zeile je Fall** - die mit dem schwersten Delikt (Rangfolge `FALLKORN_RANG`, für beide Städte gleich). Chicago führt je Vorfall ein Delikt, Detroit jedes; wer auf Chicagos Zählweise vergleicht, filtert hierauf. |

## serving

### `comparison_day`

Eine Zeile ist: **eine Stadt, ein Tag, eine NIBRS-Kategorie**. 76'429 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `reporting_city` | `VARCHAR` | Die meldende Stadt - `chicago` oder `detroit`. |
| `date` | `DATE` | Tatdatum in Ortszeit. |
| `nibrs_category` | `VARCHAR` | Die amtliche NIBRS-Kategorie aus `dim_offense`; `unmapped` für die Taten ohne Code, damit sie zählbar bleiben. |
| `nibrs_family` | `VARCHAR` | Die ersten beiden Zeichen des Codes. **Keine amtliche Gliederung** - zum Gruppieren gehört `nibrs_category`. |
| `offenses` | `BIGINT` | **Taten.** Summiert sich je Stadt auf `fact_offense` - jede Tat trägt genau eine Kategorie. |
| `cases` | `BIGINT` | **Fälle.** Summe von `counts_case`; genau eine Zeile je Fall, deshalb ebenfalls additiv über Kategorien. |

### `comparison_month`

Eine Zeile ist: **eine Stadt, ein Monat, eine NIBRS-Kategorie**. 3'633 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `reporting_city` | `VARCHAR` | Die meldende Stadt - `chicago` oder `detroit`. |
| `month` | `DATE` | Monatserster. |
| `month_end` | `DATE` | Monatsletzter. |
| `nibrs_category` | `VARCHAR` | Die amtliche NIBRS-Kategorie aus `dim_offense`; `unmapped` für die Taten ohne Code, damit sie zählbar bleiben. |
| `nibrs_family` | `VARCHAR` | Die ersten beiden Zeichen des Codes. **Keine amtliche Gliederung** - zum Gruppieren gehört `nibrs_category`. |
| `offenses` | `BIGINT` | **Taten.** Summiert sich je Stadt auf `fact_offense` - jede Tat trägt genau eine Kategorie. |
| `cases` | `BIGINT` | **Fälle.** Summe von `counts_case`; genau eine Zeile je Fall, deshalb ebenfalls additiv über Kategorien. |
| `days_in_period` | `BIGINT` | Kalendertage der Periode: 7 je Woche, 28 bis 31 je Monat. |
| `days_in_window` | `BIGINT` | Davon im Zeitfenster der Daten **dieser Stadt** (`min(date)` bis `max(date)` der Faktentabelle je `reporting_city`, seit Vertrag 3). Kleiner als `days_in_period` heisst **Teilperiode** - die Woche ab 30.12. hat zwei Tage, nicht sieben. |

### `comparison_week`

Eine Zeile ist: **eine Stadt, eine Woche ab Montag, eine NIBRS-Kategorie**. 14'275 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `reporting_city` | `VARCHAR` | Die meldende Stadt - `chicago` oder `detroit`. |
| `week_start` | `DATE` | Montag der Woche (ISO). |
| `week_end` | `DATE` | Sonntag der Woche - auch wenn er ausserhalb des Fensters liegt. |
| `nibrs_category` | `VARCHAR` | Die amtliche NIBRS-Kategorie aus `dim_offense`; `unmapped` für die Taten ohne Code, damit sie zählbar bleiben. |
| `nibrs_family` | `VARCHAR` | Die ersten beiden Zeichen des Codes. **Keine amtliche Gliederung** - zum Gruppieren gehört `nibrs_category`. |
| `offenses` | `BIGINT` | **Taten.** Summiert sich je Stadt auf `fact_offense` - jede Tat trägt genau eine Kategorie. |
| `cases` | `BIGINT` | **Fälle.** Summe von `counts_case`; genau eine Zeile je Fall, deshalb ebenfalls additiv über Kategorien. |
| `days_in_period` | `BIGINT` | Kalendertage der Periode: 7 je Woche, 28 bis 31 je Monat. |
| `days_in_window` | `BIGINT` | Davon im Zeitfenster der Daten **dieser Stadt** (`min(date)` bis `max(date)` der Faktentabelle je `reporting_city`, seit Vertrag 3). Kleiner als `days_in_period` heisst **Teilperiode** - die Woche ab 30.12. hat zwei Tage, nicht sieben. |

### `partition_quality`

Eine Zeile ist: **eine Stadt, ein Monat**. 142 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `reporting_city` | `VARCHAR` | Die meldende Stadt - `chicago` oder `detroit`. |
| `month` | `DATE` | Monatserster - die Partition, über die die Anteile gerechnet sind. |
| `offenses` | `BIGINT` | Taten in dieser Stadt und diesem Monat. |
| `share_exact` | `DOUBLE` | Anteil `mapping_status = exact` in Prozent. |
| `share_ambiguous` | `DOUBLE` | Anteil `mapping_status = ambiguous` in Prozent. |
| `share_fallback_90z` | `DOUBLE` | Anteil `mapping_status = fallback_90Z` in Prozent. |
| `share_unmapped` | `DOUBLE` | Anteil `mapping_status = unmapped` in Prozent. |
| `share_inside_city` | `DOUBLE` | Anteil `geo_status = inside_city` in Prozent. |
| `share_outside_city` | `DOUBLE` | Anteil `geo_status = outside_city` in Prozent. |
| `share_no_tract` | `DOUBLE` | Anteil `geo_status = no_tract` in Prozent. |
| `share_missing_coordinate` | `DOUBLE` | Anteil `geo_status = missing_coordinate` in Prozent. |
| `local_time_ambiguous` | `BIGINT` | Zahl der Taten in der doppelten Stunde beim Zurückstellen der Uhr (nur Chicago). Eine Zahl, kein Anteil. |

### `rate_tract`

Eine Zeile ist: **ein Census Tract mit Einwohnern im Bezugsjahr 2024 (gold_pipeline.RATENJAHR)**. 1'045 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `stadt` | `VARCHAR` | Die **meldende** Stadt (`reporting_city`), nicht die Stadtzuordnung des Tracts. Auf Tract-Ebene ist die Frage *wer hat das gemeldet*; `geo_status = 'inside_city'` stellt ohnehin sicher, dass der Tract im Gebiet dieser Stadt liegt. |
| `geoid` | `VARCHAR` | Census-GEOID der Raumeinheit, die sie eindeutig macht. Der Schlüssel, über den Delikte, Einwohner und Geometrie zusammenfinden. |
| `faelle` | `BIGINT` | Faelle im Bezugsjahr - Taten mit `counts_case`. Die Fallebene steht vorn, weil Chicago je Fall nur das schwerste Delikt erfasst und Detroit jedes. |
| `rate_fallebene` | `DOUBLE` | Faelle je 1'000 Einwohner im Bezugsjahr, auf eine Nachkommastelle. **Die Zahl, nach der die Karte einfaerbt.** |
| `taten` | `BIGINT` | Taten im Bezugsjahr - jede Zeile von `fact_offense`, ohne den Fallfilter. |
| `rate_tatebene` | `DOUBLE` | Taten je 1'000 Einwohner im Bezugsjahr. Daneben zu lesen, nicht statt der Fallebene: Der Unterschied zwischen beiden ist der Erfassungsunterschied der zwei Staedte, nicht ein Unterschied der Kriminalitaet. |
| `einwohner` | `BIGINT` | Der Nenner: `dim_tract_acs.population` im Vintage, auf den die Tat zeigt (`population_vintage`). **Tracts ohne Einwohner fehlen in dieser Tabelle** - fuer sie ist keine Rate definiert, und eine gezeigte Null liesse sich als Sicherheit lesen, wo in Wirklichkeit niemand wohnt: Flughaefen, Parks, Gewerbegebiete. |

### `source_movement`

Eine Zeile ist: **ein bewegtes Feld einer Zeile zwischen zwei Vollabzuegen; je neuer und je verschwundener Zeile eine Zeile ohne Feld; je ruhigem Paar eine Markierungszeile ohne offense_id**. 95'484 Zeilen.

| Spalte | Typ | Bedeutung |
| --- | --- | --- |
| `city` | `VARCHAR` | Stadt, kleingeschrieben: `chicago` oder `detroit`. |
| `offense_id` | `VARCHAR` | Schlüssel der Zeile. Chicagos `id`, Detroits `incident_entry_id`. |
| `previous_run_id` | `VARCHAR` | Der aeltere Vollabzug des Paares (`silver/source_change.vorher_run_id`). |
| `run_id` | `VARCHAR` | Der neuere Vollabzug des Paares. |
| `previous_snapshot_at` | `TIMESTAMP` | Wann der aeltere Vollabzug begann - die untere Grenze des Fensters. |
| `snapshot_at` | `TIMESTAMP` | Wann der neuere Vollabzug begann - die obere Grenze. Eine Bewegung geschah irgendwann dazwischen. |
| `change_type` | `VARCHAR` | `changed` (Inhalt bewegt), `touched` (nur Zeitstempel bewegt), `added` (neu im juengeren Abzug), `removed` (fehlt im juengeren Abzug), `unchanged` (Markierungszeile eines ruhigen Paares). Die Arten aus Silver, uebersetzt; eine unbekannte bricht den Bau ab. |
| `field` | `VARCHAR` | Das bewegte Quellfeld in den Begriffen der Quelle. Leer bei `added`, `removed` und `unchanged`. |
| `is_stamp` | `BOOLEAN` | Ob `field` ein Zeitstempel der Quelle ist (Detroit `updated_at`, `updated_in_ibr_at`, `case_status_updated_at`; Chicago `updated_on`). Ein bewegter Stempel ist keine Inhaltsaenderung. Leer, wo kein Feld steht. |
| `value_old` | `VARCHAR` | Der Wert im aelteren Abzug, getrimmt und als Text. |
| `value_new` | `VARCHAR` | Der Wert im neueren Abzug, gleich behandelt. |
| `source_offense_code` | `VARCHAR` | Der Deliktcode, wie die Quelle ihn führt: Chicagos `iucr`, Detroits `state_offense_code` (MICR). |
| `source_offense_category` | `VARCHAR` | Die lesbare Deliktart der Quelle (Chicagos `primary_type`, Detroits `offense_category`) - fuer eine verschwundene Zeile die einzige Auskunft darueber, was sie war. |
| `nibrs_code` | `VARCHAR` | Die Deliktart auf dem gemeinsamen Vokabular: `source_offense_code` ueber den heute gueltigen Crosswalk samt Overrides, derselbe wie fuer `fact_offense`. Erst damit lassen sich die Loeschungen beider Staedte nach Delikt vergleichen. |
| `previous_rows` | `BIGINT` | Schluessel im aelteren Abzug - der Nenner einer Loesch- oder Aenderungsrate. Je Paar einmal zaehlen, nicht je Zeile. |
| `snapshot_rows` | `BIGINT` | Schluessel im neueren Abzug. |
| `event_year` | `INTEGER` | Der Tatjahrgang des Paares (`silver/source_change.jahrgang`). Das Brett filtert danach. |
