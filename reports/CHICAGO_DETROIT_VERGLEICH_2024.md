# Chicago–Detroit: Juni 2024 und 9. November 2024

Auswertung erstellt: 2026-09-11T13:36:05.774200+00:00. Live-Quellstand, nicht historischer Stand von 2024.

## Methode und Aussagegrenzen

Das ZIP enthält Code, Konfigurationen und Referenzdokumente, aber keine Falldaten. Die vier Zeitpartitionen wurden separat aus den öffentlichen APIs geladen. Keine Projektdateien wurden verändert. Chicago wurde über API-Count, sortierte Pagination und eindeutige IDs geprüft; Detroit über die vollständige Object-ID-Liste, sortierte Pagination und exakten ID-Mengenvergleich. Die API stellt dabei keinen transaktional fixierten historischen Snapshot bereit.

Hauptkennzahl: eindeutige Fallnummer je Stadt, Zeitraum und Vergleichskategorie (Chicago case_number, Detroit report_number). Zusätzlich werden eindeutige Deliktzeilen ausgewiesen. Ein Report kann in mehreren Kategorien vorkommen; Unterkategorien dürfen nicht blind zur Gesamtfallzahl addiert werden. Alle Fälle ohne Koordinaten bleiben enthalten. Detroit UNFOUNDED ist ausgeschlossen; Chicago liefert in den abgefragten Feldern keinen gleichwertigen Status. Keine Filterung auf Verhaftung/Aufklärung.

Die Zahlen wenden zunächst die Mappingtabellen des gelieferten Projekts an. Dies ist ein reproduzierbares Projektszenario, kein amtlich zertifizierter Crosswalk und keine amtliche NIBRS-Statistik. Besonders Simple Assault muss fachlich nachgeprüft werden. Absolute Fallzahlen sind keine bevölkerungsbezogenen Risiken und erlauben keine Aussage, welche Stadt gefährlicher ist.

## Zeitfenster (Start inklusive, Ende exklusiv)

| Zeitraum | Chicago: lokales date-Feld | Detroit: UTC-Filter auf incident_occurred_at |
|---|---|---|
| Juni | 2024-06-01 00:00 bis 2024-07-01 00:00 | 2024-06-01 04:00Z bis 2024-07-01 04:00Z |
| 9. November | 2024-11-09 00:00 bis 2024-11-10 00:00 | 2024-11-09 05:00Z bis 2024-11-10 05:00Z |

## Vergleich: eindeutige Fälle

### Juni 2024

| Kategorie | Chicago | Detroit | Chicago minus Detroit |
|---|---:|---:|---:|
| ASSAULT (13A + 13B) | 6413 | 2108 | +4305 |
| Aggravated Assault (13A) | 1613 | 708 | +905 |
| Simple Assault (13B) | 4800 | 1412 | +3388 |
| Intimidation (13C), separat | 369 | 88 | +281 |
| Assault breit (13A + 13B + 13C) | 6782 | 2196 | +4586 |
| Kraftfahrzeugdiebstahl (240) | 2084 | 748 | +1336 |
| Brandstiftung (200) | 49 | 40 | +9 |

Deliktzeilen, ohne UNFOUNDED (zur Kontrolle, nicht mit Fallzahlen verwechseln):

| Kategorie | Chicago | Detroit |
|---|---:|---:|
| ASSAULT (13A + 13B) | 6413 | 2125 |
| Aggravated Assault (13A) | 1613 | 713 |
| Simple Assault (13B) | 4800 | 1412 |
| Intimidation (13C), separat | 369 | 88 |
| Assault breit (13A + 13B + 13C) | 6782 | 2213 |
| Kraftfahrzeugdiebstahl (240) | 2084 | 748 |
| Brandstiftung (200) | 49 | 40 |

### 9. November 2024

| Kategorie | Chicago | Detroit | Chicago minus Detroit |
|---|---:|---:|---:|
| ASSAULT (13A + 13B) | 192 | 76 | +116 |
| Aggravated Assault (13A) | 56 | 33 | +23 |
| Simple Assault (13B) | 136 | 45 | +91 |
| Intimidation (13C), separat | 11 | 6 | +5 |
| Assault breit (13A + 13B + 13C) | 203 | 82 | +121 |
| Kraftfahrzeugdiebstahl (240) | 53 | 12 | +41 |
| Brandstiftung (200) | 1 | 0 | +1 |

Deliktzeilen, ohne UNFOUNDED (zur Kontrolle, nicht mit Fallzahlen verwechseln):

| Kategorie | Chicago | Detroit |
|---|---:|---:|
| ASSAULT (13A + 13B) | 192 | 78 |
| Aggravated Assault (13A) | 56 | 33 |
| Simple Assault (13B) | 136 | 45 |
| Intimidation (13C), separat | 11 | 6 |
| Assault breit (13A + 13B + 13C) | 203 | 84 |
| Kraftfahrzeugdiebstahl (240) | 53 | 12 |
| Brandstiftung (200) | 1 | 0 |

## Vollständigkeit und Qualität

| Stadt | Zeitraum | Quellzeilen | Ohne Projekt-Code-Mapping | UNFOUNDED, alle Kategorien |
|---|---|---:|---:|---:|
| chicago | june | 23245 | 0 | 0 |
| chicago | nov9 | 715 | 0 | 0 |
| detroit | june | 7558 | 0 | 10 |
| detroit | nov9 | 271 | 0 | 2 |

Alle vier Downloads: keine doppelten Offense-IDs und keine fehlenden Fallnummern. Null-Tatdaten sind durch die zeitliche Abfrage nicht enthalten und wurden daher nicht global untersucht.

## Mappingvorschlag

- ASSAULT: 13A und 13B als vorläufige Sammelkategorie; 13C separat zeigen. Für eine breitere Assault-Offenses-Sicht 13A/13B/13C zusammenführen und auf Fallnummer erneut deduplizieren.
- Detroit: 1301 → 13B; 1302/1304 → 13A; 1303 → 13C. Chicago: IUCR-Einzelcode statt primary_type verwenden, insbesondere BATTERY mit berücksichtigen.
- VEHICLE_THEFT: Detroit 2401 → 240. Chicago 0910–0938 nur gemäß den tatsächlich vorhandenen Crosswalk-Einträgen, nicht als pauschaler numerischer Bereich. Mietfahrzeug-Code 1206 separat als strittige Erweiterung behandeln.
- ARSON: Detroit 2000 sowie der im Projekt ergänzte Arrest-Charge-Code 2099 → 200. Chicago 1010/1020/1025/1090. 5003 bleibt prüfpflichtig.

## Mappingprobleme und konkrete Auswirkungen

1. **ASSAULT ist keine identische Quellkategorie.** Chicago enthält relevante BATTERY-Zeilen. Ein bloßer Namensvergleich ist fachlich ungeeignet.

2. **Simple Assault versus Intimidation:** Das Projekt ordnet Chicago 0560 (ASSAULT / SIMPLE), 0545 und 0554 dem Code 13B zu. Die knappen Quellbeschreibungen belegen einen körperlichen Angriff nicht eindeutig; der MICR-Text trennt körperlichen Angriff (13001) von Einschüchterung ohne körperlichen Angriff/gefährliche Waffe (13003). Diese Chicago-Codes brauchen einen verifizierten Crosswalk. Betroffen: 1.319 Zeilen im Juni und 36 am 9. November. Eine mögliche Verschiebung von 13B nach 13C verändert die enge ASSAULT-Zahl, nicht die breite 13A/13B/13C-Zahl. Keine automatische Umklassifizierung allein anhand dieses Hinweises.

3. **Ermessenszuordnung Child Abuse:** IUCR 1750 → 13B ist im Projekt selbst als nibrs_ermessen markiert: 31 Zeilen im Juni, eine am 9. November. Auch alters-/schutzstatusbezogenes AGGRAVATED allein beweist keine Waffe oder schwere Verletzung; 0485 und 0495 sollten nachgeprüft werden (58 Juni-Zeilen, eine am 9. November).

4. **Car Theft ist enger als Motor Vehicle Theft:** Detroit 2401 unterscheidet im veröffentlichten Code nicht zuverlässig Pkw, Lkw und Motorräder. Deshalb ist nur Kraftfahrzeugdiebstahl breit direkt auswertbar. Chicago-Pkw-Untermenge 0910/0920/0930: 1.986 Fälle im Juni, 51 am 9. November; keine gleichwertige Detroit-Pkw-Zahl ableitbar. Versuche sind enthalten.

5. **Mietfahrzeuge:** Chicago 1206 (THEFT BY LESSEE, MOTOR VEHICLE) trägt eine Ermessenszuordnung nach 240. Es sind 38 Juni-Fälle und null am 9. November. Ohne diese Erweiterung ergibt Chicago 2.046 statt 2.084 Fahrzeugdiebstahlfälle im Juni. Detroit 2403 bezeichnet Fahrzeugbetrug und darf nicht pauschal dazuaddiert werden. Carjacking gehört zu Raub; Detroit 2402 zu gestohlenem Eigentum, nicht automatisch zu neuem Fahrzeugdiebstahl.

6. **Brandstiftung:** Versuche einbeziehen (Chicago 1090: vier Juni-Fälle, null am 9. November); Detroit-Arson-Definition schließt Versuche ein. Chicago 1030/1035 sind Besitz von Spreng-/Brandmitteln und nicht automatisch Brandstiftung. 5003 (OTHER ARSON / EXPLOSIVE INCIDENT) ist zu unspezifisch für eine ungeprüfte Zuordnung; in diesen beiden Zeiträumen nicht beobachtet.

7. **Detroit-Textwidersprüche:** state_offense_code hat in diesem Vergleich Vorrang vor offense_description; Abweichungen werden nicht stillschweigend repariert. Beispiele vom 9. November:

| report_number | incident_entry_id | Code | offense_description | charge_description |
|---|---|---|---|---|
| 2411090247 | 1206928-1304 | 1304 | ROBBERY | NON-FATAL SHOOTING |
| 2411090177 | 1206842-1301 | 1301 | HOMICIDE - JUSTIFIABLE | ASSAULT AND BATTERY/SIMPLE ASSAULT |
| 2411090273 | 1207188-1302 | 1302 | WEAPONS OFFENSE - OTHER | AGGRAVATED / FELONIOUS ASSAULT |

Code, Kategorie und charge_description stimmen bei diesen drei Beispielen überein. Das stützt die codebasierte Entscheidung, beweist aber nicht den Grund des abweichenden Textes. Quality Flag SOURCE_CODE_DESCRIPTION_CONFLICT vorsehen.

Zusätzlich wurden im Juni 14 Abweichungen von der erwarteten spezifischen Codebeschreibung innerhalb der betrachteten Detroit-Kategorien gefunden: sieben bei Assault (darunter eine allgemeinere Assault-Beschreibung bei 1304) und sieben bei Fahrzeugdiebstahl. Dies ist eine Textplausibilitätsprüfung, kein Beweis, dass der Code falsch ist.

Bei Detroit-Arson stammen acht der 40 Juni-Fälle aus `2099`, die übrigen 32 aus `2000`. Ein Mapping ausschließlich von `2000` würde also acht Fälle auslassen. `2099` ist im Projekt als ergänzter Arrest-Charge-Code dokumentiert und sollte mit eigener Herkunft/Review-Kennzeichnung erhalten bleiben.

Bei Detroit wurden innerhalb der Zielkategorien im Juni zwei `UNFOUNDED`-Simple-Assault-Zeilen ausgeschlossen; am 9. November eine Fahrzeugdiebstahlzeile (13 Quellzeilen vor, 12 nach Statusfilter).

## Konsequenz für Silver

Im gelieferten ZIP existiert bereits src/crime/silver_pipeline/build_crime_offense.py mit Code-Mapping, Zeitzonenumrechnung und Offense-Deduplikation. Für den Vergleich fehlt nicht grundsätzlich Silver; entscheidend sind fachliche Freigabe des Crosswalks und eine eigene Event-Kategorie-Zählsicht. Mapping-Version, Prüfflag und Herkunft behalten; UNKNOWN/AMBIGUOUS nicht als Nullfälle behandeln. UNFOUNDED bei der analytischen Sicht bewusst ausschließen. Keine Auswahl nur des schwersten Delikts pro Report.

## Quellen

- Chicago Live-Daten: https://data.cityofchicago.org/resource/ijzp-q8t2.json
- Detroit Live-Daten: https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/RMS_Crime_Incidents/FeatureServer/0/query
- Geliefertes ZIP: config/iucr_nibrs_mapping.csv; config/micr_nibrs_mapping.csv; tools/build_iucr_nibrs_mapping.py.
- Geliefertes MICR User and Technical Manual 1.11.0, Oktober 2024, gedruckte Seiten 18–21 (Definitionen).
- Gelieferte NIBRS Technical Specification 2025, Anhang A: 13A/13B/13C, 200, 240. Verwendung der 2025-Codeliste für 2024 muss als Mapping-Version dokumentiert werden.

## Anhang: tatsächlich beobachtete Codes

| Stadt | Zeitraum | Quellcode | NIBRS laut Projekt | Kategorie | Beschreibung | Mapping-Herkunft | Deliktzeilen ohne UNFOUNDED |
|---|---|---|---|---|---|---|---:|
| chicago | june | 041A | 13A | BATTERY | AGGRAVATED - HANDGUN | nibrs_definition | 212 |
| chicago | june | 041B | 13A | BATTERY | AGGRAVATED - OTHER FIREARM | nibrs_definition | 4 |
| chicago | june | 0420 | 13A | BATTERY | AGGRAVATED - KNIFE / CUTTING INSTRUMENT | nibrs_definition | 93 |
| chicago | june | 0430 | 13A | BATTERY | AGGRAVATED - OTHER DANGEROUS WEAPON | nibrs_definition | 212 |
| chicago | june | 0440 | 13B | BATTERY | AGGRAVATED - HANDS, FISTS, FEET, NO / MINOR INJURY | nibrs_definition | 31 |
| chicago | june | 0453 | 13A | BATTERY | AGGRAVATED POLICE OFFICER - OTHER DANGEROUS WEAPON | nibrs_definition | 6 |
| chicago | june | 0454 | 13B | BATTERY | AGGRAVATED P.O. - HANDS, FISTS, FEET, NO / MINOR INJURY | nibrs_definition | 66 |
| chicago | june | 0460 | 13B | BATTERY | SIMPLE | nibrs_definition | 1466 |
| chicago | june | 0461 | 13A | BATTERY | AGGRAVATED P.O. - HANDS, FISTS, FEET, SERIOUS INJURY | nibrs_definition | 10 |
| chicago | june | 0462 | 13A | BATTERY | AGG. PROTECTED EMPLOYEE - HANDS, FISTS, FEET, SERIOUS INJURY | nibrs_definition | 2 |
| chicago | june | 0479 | 13A | BATTERY | AGGRAVATED - HANDS, FISTS, FEET, SERIOUS INJURY | nibrs_definition | 13 |
| chicago | june | 0483 | 13A | BATTERY | AGGRAVATED PROTECTED EMPLOYEE - OTHER DANGEROUS WEAPON | nibrs_definition | 5 |
| chicago | june | 0484 | 13B | BATTERY | PROTECTED EMPLOYEE - HANDS, FISTS, FEET, NO / MINOR INJURY | nibrs_definition | 41 |
| chicago | june | 0485 | 13A | BATTERY | AGGRAVATED OF A CHILD | nibrs_definition | 5 |
| chicago | june | 0486 | 13B | BATTERY | DOMESTIC BATTERY SIMPLE | nibrs_definition | 1846 |
| chicago | june | 0488 | 13A | BATTERY | AGGRAVATED DOMESTIC BATTERY - HANDGUN | nibrs_definition | 1 |
| chicago | june | 0495 | 13A | BATTERY | AGGRAVATED OF A SENIOR CITIZEN | nibrs_definition | 53 |
| chicago | june | 0496 | 13A | BATTERY | AGGRAVATED DOMESTIC BATTERY - KNIFE / CUTTING INSTRUMENT | nibrs_definition | 37 |
| chicago | june | 0497 | 13A | BATTERY | AGGRAVATED DOMESTIC BATTERY - OTHER DANGEROUS WEAPON | nibrs_definition | 109 |
| chicago | june | 0498 | 13A | BATTERY | AGG. DOMESTIC BATTERY - HANDS, FISTS, FEET, SERIOUS INJURY | nibrs_definition | 89 |
| chicago | june | 051A | 13A | ASSAULT | AGGRAVATED - HANDGUN | nibrs_definition | 480 |
| chicago | june | 051B | 13A | ASSAULT | AGGRAVATED - OTHER FIREARM | nibrs_definition | 19 |
| chicago | june | 0520 | 13A | ASSAULT | AGGRAVATED - KNIFE / CUTTING INSTRUMENT | nibrs_definition | 154 |
| chicago | june | 0530 | 13A | ASSAULT | AGGRAVATED - OTHER DANGEROUS WEAPON | nibrs_definition | 90 |
| chicago | june | 0545 | 13B | ASSAULT | PROTECTED EMPLOYEE - HANDS, FISTS, FEET, NO / MINOR INJURY | nibrs_definition | 17 |
| chicago | june | 0550 | 13A | ASSAULT | AGGRAVATED POLICE OFFICER - HANDGUN | nibrs_definition | 3 |
| chicago | june | 0551 | 13A | ASSAULT | AGGRAVATED POLICE OFFICER - OTHER FIREARM | nibrs_definition | 2 |
| chicago | june | 0552 | 13A | ASSAULT | AGGRAVATED POLICE OFFICER - KNIFE / CUTTING INSTRUMENT | nibrs_definition | 1 |
| chicago | june | 0553 | 13A | ASSAULT | AGGRAVATED POLICE OFFICER - OTHER DANGEROUS WEAPON | nibrs_definition | 3 |
| chicago | june | 0554 | 13B | ASSAULT | AGGRAVATED POLICE OFFICER - HANDS, FISTS, FEET, NO INJURY | nibrs_definition | 14 |
| chicago | june | 0555 | 13A | ASSAULT | AGGRAVATED PROTECTED EMPLOYEE - HANDGUN | nibrs_definition | 1 |
| chicago | june | 0558 | 13A | ASSAULT | AGGRAVATED PROTECTED EMPLOYEE - OTHER DANGEROUS WEAPON | nibrs_definition | 9 |
| chicago | june | 0560 | 13B | ASSAULT | SIMPLE | nibrs_definition | 1288 |
| chicago | june | 0580 | 13C | STALKING | SIMPLE | nibrs_definition | 27 |
| chicago | june | 0581 | 13C | STALKING | AGGRAVATED | nibrs_definition | 1 |
| chicago | june | 0583 | 13C | STALKING | CYBERSTALKING | nibrs_definition | 6 |
| chicago | june | 0910 | 240 | MOTOR VEHICLE THEFT | AUTOMOBILE | nibrs_definition | 1476 |
| chicago | june | 0915 | 240 | MOTOR VEHICLE THEFT | TRUCK, BUS, MOTOR HOME | nibrs_definition | 8 |
| chicago | june | 0917 | 240 | MOTOR VEHICLE THEFT | CYCLE, SCOOTER, BIKE WITH VIN | nibrs_definition | 37 |
| chicago | june | 0918 | 240 | MOTOR VEHICLE THEFT | CYCLE, SCOOTER, BIKE NO VIN | nibrs_definition | 10 |
| chicago | june | 0920 | 240 | MOTOR VEHICLE THEFT | ATTEMPT - AUTOMOBILE | nibrs_definition | 329 |
| chicago | june | 0927 | 240 | MOTOR VEHICLE THEFT | ATTEMPT - CYCLE, SCOOTER, BIKE WITH VIN | nibrs_definition | 1 |
| chicago | june | 0930 | 240 | MOTOR VEHICLE THEFT | THEFT / RECOVERY - AUTOMOBILE | nibrs_definition | 181 |
| chicago | june | 0935 | 240 | MOTOR VEHICLE THEFT | THEFT / RECOVERY - TRUCK, BUS, MOBILE HOME | nibrs_definition | 1 |
| chicago | june | 0937 | 240 | MOTOR VEHICLE THEFT | THEFT / RECOVERY - CYCLE, SCOOTER, BIKE WITH VIN | nibrs_definition | 3 |
| chicago | june | 1020 | 200 | ARSON | BY FIRE | nibrs_definition | 41 |
| chicago | june | 1025 | 200 | ARSON | AGGRAVATED | nibrs_definition | 4 |
| chicago | june | 1090 | 200 | ARSON | ATTEMPT ARSON | nibrs_definition | 4 |
| chicago | june | 1206 | 240 | DECEPTIVE PRACTICE | THEFT BY LESSEE, MOTOR VEHICLE | nibrs_ermessen | 38 |
| chicago | june | 1750 | 13B | OFFENSE INVOLVING CHILDREN | CHILD ABUSE | nibrs_ermessen | 31 |
| chicago | june | 2820 | 13C | OTHER OFFENSE | TELEPHONE THREAT | nibrs_definition | 309 |
| chicago | june | 2850 | 13C | PUBLIC PEACE VIOLATION | BOMB THREAT | nibrs_definition | 8 |
| chicago | june | 2851 | 13C | PUBLIC PEACE VIOLATION | ARSON THREAT | nibrs_definition | 4 |
| chicago | june | 3960 | 13C | INTIMIDATION | INTIMIDATION | nibrs_definition | 13 |
| chicago | june | 3961 | 13C | INTIMIDATION | INTIMIDATION OF LAW ENFORCEMENT OFFICIAL | nibrs_definition | 1 |
| chicago | nov9 | 041A | 13A | BATTERY | AGGRAVATED - HANDGUN | nibrs_definition | 6 |
| chicago | nov9 | 0420 | 13A | BATTERY | AGGRAVATED - KNIFE / CUTTING INSTRUMENT | nibrs_definition | 2 |
| chicago | nov9 | 0430 | 13A | BATTERY | AGGRAVATED - OTHER DANGEROUS WEAPON | nibrs_definition | 5 |
| chicago | nov9 | 0440 | 13B | BATTERY | AGGRAVATED - HANDS, FISTS, FEET, NO / MINOR INJURY | nibrs_definition | 1 |
| chicago | nov9 | 0460 | 13B | BATTERY | SIMPLE | nibrs_definition | 37 |
| chicago | nov9 | 0461 | 13A | BATTERY | AGGRAVATED P.O. - HANDS, FISTS, FEET, SERIOUS INJURY | nibrs_definition | 2 |
| chicago | nov9 | 0479 | 13A | BATTERY | AGGRAVATED - HANDS, FISTS, FEET, SERIOUS INJURY | nibrs_definition | 2 |
| chicago | nov9 | 0486 | 13B | BATTERY | DOMESTIC BATTERY SIMPLE | nibrs_definition | 61 |
| chicago | nov9 | 0495 | 13A | BATTERY | AGGRAVATED OF A SENIOR CITIZEN | nibrs_definition | 1 |
| chicago | nov9 | 0497 | 13A | BATTERY | AGGRAVATED DOMESTIC BATTERY - OTHER DANGEROUS WEAPON | nibrs_definition | 6 |
| chicago | nov9 | 0498 | 13A | BATTERY | AGG. DOMESTIC BATTERY - HANDS, FISTS, FEET, SERIOUS INJURY | nibrs_definition | 1 |
| chicago | nov9 | 051A | 13A | ASSAULT | AGGRAVATED - HANDGUN | nibrs_definition | 17 |
| chicago | nov9 | 051B | 13A | ASSAULT | AGGRAVATED - OTHER FIREARM | nibrs_definition | 1 |
| chicago | nov9 | 0520 | 13A | ASSAULT | AGGRAVATED - KNIFE / CUTTING INSTRUMENT | nibrs_definition | 6 |
| chicago | nov9 | 0530 | 13A | ASSAULT | AGGRAVATED - OTHER DANGEROUS WEAPON | nibrs_definition | 6 |
| chicago | nov9 | 0545 | 13B | ASSAULT | PROTECTED EMPLOYEE - HANDS, FISTS, FEET, NO / MINOR INJURY | nibrs_definition | 1 |
| chicago | nov9 | 0550 | 13A | ASSAULT | AGGRAVATED POLICE OFFICER - HANDGUN | nibrs_definition | 1 |
| chicago | nov9 | 0560 | 13B | ASSAULT | SIMPLE | nibrs_definition | 35 |
| chicago | nov9 | 0580 | 13C | STALKING | SIMPLE | nibrs_definition | 1 |
| chicago | nov9 | 0910 | 240 | MOTOR VEHICLE THEFT | AUTOMOBILE | nibrs_definition | 40 |
| chicago | nov9 | 0917 | 240 | MOTOR VEHICLE THEFT | CYCLE, SCOOTER, BIKE WITH VIN | nibrs_definition | 2 |
| chicago | nov9 | 0920 | 240 | MOTOR VEHICLE THEFT | ATTEMPT - AUTOMOBILE | nibrs_definition | 4 |
| chicago | nov9 | 0930 | 240 | MOTOR VEHICLE THEFT | THEFT / RECOVERY - AUTOMOBILE | nibrs_definition | 7 |
| chicago | nov9 | 1020 | 200 | ARSON | BY FIRE | nibrs_definition | 1 |
| chicago | nov9 | 1750 | 13B | OFFENSE INVOLVING CHILDREN | CHILD ABUSE | nibrs_ermessen | 1 |
| chicago | nov9 | 2820 | 13C | OTHER OFFENSE | TELEPHONE THREAT | nibrs_definition | 9 |
| chicago | nov9 | 2850 | 13C | PUBLIC PEACE VIOLATION | BOMB THREAT | nibrs_definition | 1 |
| detroit | june | 1301 | 13B | ASSAULT | ASSAULT AND BATTERY/SIMPLE ASSAULT | micr_manual_1110_2024 | 1412 |
| detroit | june | 1302 | 13A | AGGRAVATED ASSAULT | AGGRAVATED / FELONIOUS ASSAULT | micr_manual_1110_2024 | 662 |
| detroit | june | 1302 | 13A | AGGRAVATED ASSAULT | ASSAULT AND BATTERY/SIMPLE ASSAULT | micr_manual_1110_2024 | 3 |
| detroit | june | 1302 | 13A | AGGRAVATED ASSAULT | KIDNAPPING / ABDUCTION | micr_manual_1110_2024 | 1 |
| detroit | june | 1302 | 13A | AGGRAVATED ASSAULT | MURDER / NON-NEGLIGENT MANSLAUGHTER (VOLUNTARY) | micr_manual_1110_2024 | 1 |
| detroit | june | 1303 | 13C | ASSAULT | INTIMIDATION / STALKING | micr_manual_1110_2024 | 88 |
| detroit | june | 1304 | 13A | AGGRAVATED ASSAULT | AGGRAVATED / FELONIOUS ASSAULT | micr_manual_1110_2024 | 1 |
| detroit | june | 1304 | 13A | AGGRAVATED ASSAULT | MURDER / NON-NEGLIGENT MANSLAUGHTER (VOLUNTARY) | micr_manual_1110_2024 | 1 |
| detroit | june | 1304 | 13A | AGGRAVATED ASSAULT | NON-FATAL SHOOTING | micr_manual_1110_2024 | 44 |
| detroit | june | 2000 | 200 | ARSON | ARSON | micr_manual_1110_2024 | 32 |
| detroit | june | 2099 | 200 | ARSON | ARSON | micr_arrest_charge_1110_2024 | 8 |
| detroit | june | 2401 | 240 | STOLEN VEHICLE | AGGRAVATED / FELONIOUS ASSAULT | micr_manual_1110_2024 | 2 |
| detroit | june | 2401 | 240 | STOLEN VEHICLE | ASSAULT AND BATTERY/SIMPLE ASSAULT | micr_manual_1110_2024 | 2 |
| detroit | june | 2401 | 240 | STOLEN VEHICLE | BURGLARY - FORCED ENTRY | micr_manual_1110_2024 | 1 |
| detroit | june | 2401 | 240 | STOLEN VEHICLE | LARCENY - OTHER | micr_manual_1110_2024 | 2 |
| detroit | june | 2401 | 240 | STOLEN VEHICLE | MOTOR VEHICLE THEFT | micr_manual_1110_2024 | 741 |
| detroit | nov9 | 1301 | 13B | ASSAULT | ASSAULT AND BATTERY/SIMPLE ASSAULT | micr_manual_1110_2024 | 44 |
| detroit | nov9 | 1301 | 13B | ASSAULT | HOMICIDE - JUSTIFIABLE | micr_manual_1110_2024 | 1 |
| detroit | nov9 | 1302 | 13A | AGGRAVATED ASSAULT | AGGRAVATED / FELONIOUS ASSAULT | micr_manual_1110_2024 | 30 |
| detroit | nov9 | 1302 | 13A | AGGRAVATED ASSAULT | WEAPONS OFFENSE - OTHER | micr_manual_1110_2024 | 1 |
| detroit | nov9 | 1303 | 13C | ASSAULT | INTIMIDATION / STALKING | micr_manual_1110_2024 | 6 |
| detroit | nov9 | 1304 | 13A | AGGRAVATED ASSAULT | NON-FATAL SHOOTING | micr_manual_1110_2024 | 1 |
| detroit | nov9 | 1304 | 13A | AGGRAVATED ASSAULT | ROBBERY | micr_manual_1110_2024 | 1 |
| detroit | nov9 | 2401 | 240 | STOLEN VEHICLE | MOTOR VEHICLE THEFT | micr_manual_1110_2024 | 12 |
