# Eine dritte Stadt anbinden

Stand: 8.11.2026. **Eine dritte Stadt ist nicht geplant.** Die Arbeit vergleicht
Chicago und Detroit. Diese Anleitung hält fest, was vorbereitet ist und was im
Fall der Fälle noch fehlt, damit niemand die Arbeit ein zweites Mal macht.

Kurz gesagt:

- **Die Ingestion ist konfigurierbar.** Für eine Stadt auf Socrata oder ArcGIS
  genügt ein Eintrag in [`config/quellen.toml`](../../config/quellen.toml), ganz
  ohne neuen Code.
- **Silver, Census, Wetter und Serving sind es nicht.** Dort hat jede Stadt
  eigene Konstanten und eigene Regeln. Abschnitt 3 listet die Stellen auf.

## 1. Welche Städte in Frage kommen

Erhoben am 8.11.2026, direkt an den APIs. Gezählt werden die zehn grössten
US-Städte nach der Census-Schätzung 2024; Jacksonville liegt auf Platz 10 nur
knapp vor Fort Worth.

| Stadt | Plattform | Adapter vorhanden | Deliktcode | Zeile ist | Änderungsstempel |
|---|---|---|---|---|---|
| Chicago | Socrata `ijzp-q8t2` | ja (im Einsatz) | IUCR, `fbi_code` | Vorfall | `updated_on` |
| Detroit | ArcGIS `RMS_Crime_Incidents` | ja (im Einsatz) | MICR, `offense_category` | Tat | `updated_at` |
| New York | Socrata `qgea-i56i`, `5uac-w243` | ja | eigene Codes (`ky_cd`, `pd_cd`) | Anzeige | – |
| Los Angeles | Socrata `k7nn-b2ep` (NIBRS, ab 2024) | ja | NIBRS | Tat | – |
| Dallas | Socrata `qv6i-rri7` | ja | NIBRS und UCR | Vorfall | `upzdate` |
| Jacksonville | ArcGIS „Public Transparency Data View" | ja | NIBRS (numerisch) | Tat | – |
| Houston | CSV je Jahr, keine API | nein | NIBRS | Tat | – |
| San Diego | CSV je Jahr, keine API | nein | NIBRS | Tat | `approved_on` |
| Phoenix | CKAN-Datastore | nein | 11 UCR-Kategorien | Vorfall | – |
| Philadelphia | Carto-SQL | nein | UCR | Vorfall | – |
| San Antonio | CKAN (sperrt automatische Abrufe) | nein | NIBRS | Tat | ? |

**Am wenigsten Umbau verlangt Dallas.** Die Stadt liegt auf Socrata wie
Chicago, ist täglich aktuell und hat als einzige einen Änderungsstempel. Sie
liefert NIBRS direkt, die Delikte bräuchten also keinen eigenen Crosswalk.
Danach folgt **Jacksonville**: ArcGIS wie Detroit und ebenfalls NIBRS, aber
ohne Änderungsstempel und mit nur elf Feldern.

**Nicht erfüllt sind diese Bedingungen:**

- **Ganzzahlige ID:** Der Socrata-Adapter verlangt ein ganzzahliges `id_feld`,
  weil Keyset-Pagination und Snapshot darüber laufen. Dallas' `servnumid` ist
  ein solches Feld; ob es eindeutig ist, ist nicht geprüft.
- **Delta-Läufe:** Ohne Änderungsstempel gibt es keine Delta-Läufe. Jeder Lauf
  wäre ein voller Schnappschuss, und die Quellbewegung (`source_change`) ginge
  nur über den Vergleich ganzer Abzüge.

## 2. Was vorbereitet ist: die Ingestion

[`config/quellen.toml`](../../config/quellen.toml) beschreibt je Stadt, wo und wie
geladen wird. Gelesen wird die Datei von
[`storage.quellen`](../../src/crime/storage/quellen.py), und zwar streng: Ein
unbekannter Schlüssel bricht genauso ab wie ein fehlender oder einer vom
falschen Typ.

| Plattform | Adapter | Aufruf für einen weiteren Eintrag |
|---|---|---|
| `socrata` | [`chicago_pipeline/download_chicago.py`](../../src/crime/chicago_pipeline/download_chicago.py) | `python -m chicago_pipeline.download_chicago --source dallas --year 2024` |
| `arcgis` | [`detroit_pipeline/detroit_arcgis.py`](../../src/crime/detroit_pipeline/detroit_arcgis.py), [`extract_detroit.py`](../../src/crime/detroit_pipeline/extract_detroit.py) | `python -m detroit_pipeline.extract_detroit --source jacksonville --mode delta --years 2024` |

Die Module tragen noch den Namen der ersten Stadt. Ein Umbenennen hätte
Notebooks, die Konsole und die Stufenliste mitgezogen. Für eine Vorbereitung
war das den Bruch nicht wert.

**Ein Socrata-Eintrag** nennt Folgendes:

- `domain` und `datensatz`
- `id_feld` (ganzzahlig)
- `tatzeit_feld`: schneidet den Jahrgang
- `aenderungs_feld`: das Wasserzeichen
- das gepinnte Schema `felder`
- optional `boolesche_felder` und ein `ortsfeld` mit seinen `ortsunterfeldern`

Was nicht in `felder` steht, landet in `_extra`. Socratas eigene
`:`-Spalten werden verworfen.

**Ein ArcGIS-Eintrag** nennt Folgendes:

- `layer_url`, `datensatz` und `quellsystem`
- die `zeitzone`, in der Jahrgang und Tagesfenster geschnitten werden
- `tatzeit_feld` und `aenderungs_feld`
- `kategorie_feld`: wird nur als Prüfsumme gezählt
- `erstes_jahr`

Das Schema friert der Adapter aus den Layer-Metadaten ein. Jedes Feature
bleibt zusätzlich verlustfrei als JSON erhalten.

Ein Prozess lädt genau eine Quelle: `use_source` setzt die Modulwerte, die alle
Funktionen lesen. Die Strecke startet jede Stufe als eigenen Prozess, deshalb
stört das nicht.

**Nachweis, dass sich durch den Umzug nichts geändert hat:** Vor und nach der
Umstellung wurden dieselben Läufe aus festen Eingaben gebaut, jeweils in einem
eigenen Prozess:

- **Chicago:** Raw, Bronze und Manifest waren byteweise gleich.
- **Detroit:** Manifest, Zeilen und Raw-Antworten waren gleich.

Die Eingaben, die das entschieden haben, halten
`tests/storage/test_quellen.py`, `tests/chicago_pipeline/test_download_chicago.py`
(Abschnitt „The source descriptor") und
`tests/detroit_pipeline/test_quelle_detroit.py`.

## 3. Was noch fehlt, Schicht für Schicht

### Die vier Nähte (FR-41)

Vier Stellen nimmt eine dritte Stadt in jedem Fall in Anspruch. An jeder
dockt sie an, ohne dass sich an Chicago oder Detroit etwas ändert. Die
übrigen Punkte unten hängen an diesen vier oder kommen aus ihnen.

| Naht | Wo | Was die Stadt dort einträgt |
| --- | --- | --- |
| **Die Studienstadt** | [`silver_pipeline.STUDIENSTAEDTE`](../../src/crime/silver_pipeline/__init__.py) | ihre Place-GEOID und den amtlichen Namen. Gold leitet daraus `STADT_SCHLUESSEL` ab und Kibana seine Karten. Es gibt keine zweite Liste, die gepflegt werden müsste |
| **Die eigene Ingestion** | ein Eintrag in [`config/quellen.toml`](../../config/quellen.toml), gelesen von [`storage.quellen`](../../src/crime/storage/quellen.py) | Plattform, Adresse, Schlüssel- und Zeitfelder, das gepinnte Schema. Auf Socrata oder ArcGIS reicht das, für jede andere Plattform braucht sie einen Adapter (Abschnitt 2) |
| **Der eigene Crosswalk nach NIBRS** | `config/<code>_nibrs_mapping.csv`, erzeugt aus amtlichen Quellen wie `tools/build_iucr_nibrs_mapping.py`, und einzelne Korrekturen in `config/mapping_overrides.csv` | wie ihre Deliktcodes auf NIBRS fallen. Liefert sie NIBRS direkt, entfällt der Crosswalk (Punkt 9) |
| **Die Quellbewegung** | ein Eintrag in [`build_source_change.QUELLEN`](../../src/crime/silver_pipeline/build_source_change.py) | das Feld mit der fachlichen Identität, die Bronze-Form, die Felder, die nur Rauschen sind, und die Stempel, deren Bewegung keine Inhaltsänderung ist |

Was diese vier Nähte nicht abdecken, ist Code: die Abfrage je Stadt in
`build_crime_offense.build_query()` (Punkt 8) und die Stellen aus Abschnitt
3a. Eine Naht im eigentlichen Sinn ist das nicht.

Die Punkte unten folgen der Reihenfolge der Strecke, und jeder nennt die
Stelle im Code.

### Ingestion

1. **Den Eintrag in `config/quellen.toml` anlegen.** Danach die Felder an einem
   echten Abzug prüfen: Ist `id_feld` eindeutig und ganzzahlig? Füllt
   `aenderungs_feld` jede Zeile?
2. **Die Stufe in [`orchestration/run_all.py`](../../src/crime/orchestration/run_all.py)
   eintragen** (`STUFEN`), mit `--source` und `quelle="city=<stadt>"`. Dazu die
   Regel in [`orchestration/platzbedarf.py`](../../src/crime/orchestration/platzbedarf.py)
   (`REGEL_JE_QUELLE`, `"city=<stadt>": TATEN`). Ohne diese Regel bricht die
   Hochrechnung ab.
3. **Die Konsole ergänzen:** Sie kennt die Städte einzeln.
   - [`platform_admin/jobs.py`](../../src/crime/platform_admin/jobs.py): die
     Bezeichnung der Stufe und die Zeitzone von `daily_detroit`
   - [`platform_admin/sources.py`](../../src/crime/platform_admin/sources.py):
     `source_status` und `SOURCE_FILES`
4. **Die Drift-Wächter ergänzen:**
   [`orchestration/drift.py`](../../src/crime/orchestration/drift.py) zählt die
   Kennzahlen je Stadt einzeln auf.

4a. **Die Gebiete** (seit dem 25.11.2026): Polizeibezirke und Stadtteile
   lädt [`gebiete_pipeline/download_gebiete.py`](../../src/crime/gebiete_pipeline/download_gebiete.py)
   aus `AUSLIEFERUNGEN`, je Stadt und Ebene eine Zeile mit Adresse,
   Zählabfrage und Schlüsselfeld. Das ist **Code, kein Eintrag in
   `config/quellen.toml`**. Dazu in
   [`silver_pipeline/build_police_area.py`](../../src/crime/silver_pipeline/build_police_area.py)
   das Wort der Stadt für ihre Bezirke (`BEZEICHNUNG`, für Stadtteile die
   Ebene in `build_community_area.py`). Fehlen die Gebiete, bricht Gold ab
   („keine Polizeibezirke in der Stadt", `pruefe_polizeibezirke`).

### Census und Wetter

5. **TIGER und ACS:** Die Bundesstaaten stehen in
   [`census_pipeline/__init__.py`](../../src/crime/census_pipeline/__init__.py).
   Texas (48) oder Florida (12) müssten dazukommen, damit Tracts und Place
   geladen werden.
6. **Wetter:** In [`weather_pipeline/__init__.py`](../../src/crime/weather_pipeline/__init__.py)
   bekommt jede Stadt eine NOAA-Station, bisher Chicago O'Hare und Detroit
   Metro Airport.

### Silver

7. **Die Stadt in `silver_pipeline.STUDIENSTAEDTE` eintragen**, mit ihrer
   Place-GEOID. Gold leitet den Verbundschlüssel daraus ab, sonst nirgends.
8. **Die Delikte normalisieren:**
   [`silver_pipeline/build_crime_offense.py`](../../src/crime/silver_pipeline/build_crime_offense.py)
   hat je Stadt eine Quelle (`chicago_sources`, `detroit_sources`), eine
   Zeitzone (`TIMEZONES`) und einen Zweig in `build_query`. Dort werden
   Tatzeit, Ort, Fall- und Tatschlüssel gesetzt. Das ist die eigentliche Arbeit
   für eine neue Stadt. Ein Adapter bringt sie nicht mit, weil jede Polizei
   ihr Schema anders schneidet.
9. **Den Deliktcode zuordnen:**
   - Liefert die Stadt NIBRS direkt, wie Dallas, Los Angeles oder Jacksonville,
     braucht sie keinen Crosswalk. Zu prüfen bleibt, ob die Codes zu
     `config/nibrs_offense_codes_2025.csv` passen.
   - Eigene Codes wie in New York brauchen einen eigenen Crosswalk, erzeugt
     wie `iucr_nibrs_mapping.csv` und nie von Hand.
   - Einzelne Korrekturen gehören in `config/mapping_overrides.csv`.
10. **Die Quellbewegung:**
    [`silver_pipeline/build_source_change.py`](../../src/crime/silver_pipeline/build_source_change.py)
    kennt je Stadt den Schlüssel und die Kontextfelder. Ohne Änderungsstempel
    geht sie nur über den Vergleich voller Abzüge.

### Gold und Serving

11. **Gold** ([`gold_pipeline/build_gold.py`](../../src/crime/gold_pipeline/build_gold.py))
    leitet die Städte aus `STUDIENSTAEDTE` ab. Die Fallregel ist aber je Stadt
    beschrieben, weil Chicago nur das schwerste Delikt eines Falls führt und
    Detroit jedes. Eine neue Stadt muss sagen, welche Granularität sie liefert.
12. **Das Dashboard:** die Farben in `static/dashboard.css` (`--chicago`,
    `--detroit`) und in `static/gemeinsam.js` (`FARBE`). `STAEDTE` und
    `STADTNAMEN` in
    [`serving/dashboard/__init__.py`](../../src/crime/serving/dashboard/__init__.py)
    leiten sich seit dem 22.11.2026 aus `STUDIENSTAEDTE` ab, und die Leiste
    baut je Stadt eine Checkbox. Eine neue Stadt erscheint dort also von
    selbst.
13. **Kibana:** der Kartenausschnitt je Stadt (`KARTE_JE_STADT`) in
    [`serving/build_kibana.py`](../../src/crime/serving/build_kibana.py).
    Fehlt er, bricht der Bau der Kartentafel ab und nennt die Stadt. Das gilt
    erst seit dem 21.11.2026: Davor kamen die Karten aus `KARTE_JE_STADT`
    selbst, und eine Stadt ohne Eintrag bekam still keine Karte.
14. **Die Register:** Fünf Register müssen mitgeführt werden, sonst bricht ein
    Test (siehe `AGENTS.md`). Dazu kommen ein Eintrag in den
    Vertragsversionen von `docs/intern/AENDERUNGEN.md`, die Notebooks und die
    Zahlen der Abgabedokumente samt ihren Referenzstand-Wächtern.

### 3a. Stellen, die genau zwei Städte voraussetzen (FR-43)

Abschnitt 3 nennt, wo eine dritte Stadt einen Eintrag braucht. Die meisten
dieser Stellen brechen ab, wenn er fehlt. Die folgenden tun das nicht: Mit
einer dritten Stadt liefern sie still ein falsches oder unvollständiges
Ergebnis. Durchgesehen wurde am 21.11.2026 der Code unter `src/crime/`. Jede
Stelle trägt dort einen Kommentar mit „FR-43", und `grep -rn FR-43 src/`
findet sie alle.

| Stelle | Was mit einer dritten Stadt geschähe |
| --- | --- |
| `silver_pipeline/build_crime_offense.py`, Crosswalk-Abfrage | genau die IUCR- und die MICR-Datei. Ihre Codes blieben ohne Fehler `unmapped` |
| ebenda, Zonenprüfung im Abgleich | das `ELSE` meint Detroit. In einer anderen Zone ein falscher Zonenbefund, in derselben Zone keiner |
| ebenda, Prüfung „nicht mehr Ergebnis als Quelle" | je Stadt einzeln. Die dritte bliebe ungeprüft |
| ebenda, `comparability` | nur die Spalten `chicago` und `detroit`. Die dritte fehlt in diesem Teil des Manifests |
| `platform_admin/batch.py` | Ein Volllauf aus der Konsole liefe für sie als Delta, und ihre Läufe würden nicht als Beleg erfasst |
| `platform_admin/jobs.py` | Die Stadt wird aus dem Aufgabennamen gelesen, mit „Chicago" als Rückfall. Heute lehnt die Konsole unbekannte Aufgaben ab |
| `serving/dashboard/quellbewegung.py` | Der Test vergleicht genau ein Paar. Bei drei Städten fallen Vergleich und Faktor weg |
| `serving/dashboard/static/quellbewegung.js` | dieselbe Tafel, mit zwei Spalten |
| `serving/dashboard/static/gemeinsam.js`, `FARBE` | ohne Eintrag keine Farbe, und SVG zeichnet die Stadt schwarz |
| `serving/dashboard/static/geografie.js` | Die Rangliste der Tracts gibt es nur für Chicago und Detroit, ebenso die Behälter in `geografie.html` |

Nur in Texten, ohne Folgen für eine Zahl: die Zeile „Chicago · Detroit" und
„Die beiden Städte" in `serving/build_einstieg.py`, die Tract-Zahlen in
`static/datenqualitaet.js` und `BEZEICHNUNG` in
`silver_pipeline/build_police_area.py` — ohne Eintrag bleibt der Name eines
Bezirks leer, seine Nummer stimmt.

Laut sind dagegen, und deshalb nicht in der Tabelle: `CROSSWALKS` in
`gold_pipeline/build_gold.py` (die Prüfung auf verwaiste Codes bricht ab),
die Qualitätsprüfung in `platform_admin/checks.py`,
`platform_admin/run_evidence.py` („Unbekannte Stadt") und die Zeitzonen in
`serving/dashboard/zeitverlauf.py`.

Behoben statt kommentiert ist eine Stelle, nämlich die Kibana-Karten (Punkt
13). Kommentar und Anleitung versprachen dort einen Abbruch, den der Code
nicht auslösen konnte. Das halten `test_die_karten_kommen_aus_den_studienstaedten`
und `test_eine_stadt_ohne_ausschnitt_bricht_ab_und_wird_genannt`.

Seit dem 22.11.2026 ist auch `STAEDTE` im Dashboard behoben: Es leitet sich
aus `STUDIENSTAEDTE` ab, statt fest eingetragen zu sein
(`test_die_staedte_kommen_aus_den_studienstaedten`). Damit stehen noch zehn
Stellen in der Tabelle.

### 3b. Die vier Asymmetrien als Muster (FR-42)

Chicago und Detroit beschreiben dieselben Dinge mit verschiedenen Schlüsseln
und Formen. Jede der vier Asymmetrien wird an **einer** Stelle aufgefangen,
nicht in jedem Modul neu. Eine dritte Stadt füllt die Zeile aus, indem sie
die Frage in der vierten Spalte beantwortet.

| Asymmetrie | Chicago | Detroit | Wo aufgefangen | Die Frage an eine dritte Stadt |
| --- | --- | --- | --- | --- |
| **Lademodus** | Manifest `mode`, Werte `full_snapshot` oder `delta`. Ein Delta blickt 14 Tage hinter das Wasserzeichen `updated_on` zurück, die Deltas überlappen sich also | Manifest `extraction_mode`, Werte `FULL`, `DELTA` oder `INCREMENTAL`. Zeilen ohne `updated_at` kommen in jedem Delta mit | [`manifeste.Lauf.vollabzug`](../../src/crime/manifeste/__init__.py) und `VOLLABZUG`. Census, TIGER und NOAA nennen keinen Modus und gelten deshalb **nicht** als Vollabzug | Hat sie einen Änderungsstempel? Ohne ihn ist jeder Lauf ein Vollabzug (Abschnitt 1) |
| **Zeitschlüssel** | Tatzeit `date` als Ortszeit ohne Zone. Laufbeginn `started_at_utc`, Jahrgang `event_year` | Tatzeit `incident_occurred_at` in Epoch-Millisekunden UTC. Laufbeginn `started_at`, Jahrgang `year` | Die Tatzeit setzt Silver je Stadt in `build_query()`, mit `TIMEZONES`, in beide Richtungen: Chicago von Ortszeit nach UTC, Detroit von UTC nach Ortszeit. Laufbeginn und Jahrgang liest `manifeste.Lauf.begonnen_um` und `.jahrgang` | In welcher Zone liegt ihre Tatzeit, und gibt es Ortszeiten, die es nie gab oder die zweimal vorkommen? |
| **Bronze-Form** | flache Spalten, so wie Socrata sie liefert | ArcGIS-Features mit den Feldern in einem Struct `attributes`, zusätzlich jedes Feature verlustfrei als JSON | `build_source_change.Quelle.struct` (`None` heisst flach). In Silver liest der Zweig je Stadt die Felder an ihrem Ort | Flach oder verschachtelt? Das entscheidet die Plattform, nicht die Stadt |
| **Identitätsschlüssel und Granularität** | Zeile ist ein Vorfall: `id` ist der Tatschlüssel, `case_number` der Fall. Je Fall steht nur das schwerste Delikt da | Zeile ist ein Delikt: `incident_entry_id` ist der Tatschlüssel, `report_number` der Fall. Je Fall steht jedes Delikt da | Silver setzt `offense_id` und `event_id` je Stadt. `FALLKORN_RANG` wählt die Fallebene für beide gleich, und Gold beschreibt die Fallregel je Stadt (Punkt 11). Die Quellbewegung nimmt `Quelle.schluessel` | Welches Feld trägt die fachliche Identität, nicht die Zeilennummer der Antwort? Und ist eine Zeile ein Vorfall oder ein Delikt? |

Daneben gibt es zwei kleinere Unterschiede ohne fachliche Folge. Die Läufe
heissen `run_id` bei Chicago und `pipeline_run_id` bei Detroit, der Abschluss
`completed_at_utc` und `finished_at`. Der Status lautet `complete` und
`SUCCESS`. Auch diese Unterschiede fängt `manifeste` auf (`FERTIG`,
`Lauf.run_id`, `Lauf.abgeschlossen_um`).

## 4. Was bewusst nicht vorbereitet ist

- **Keine Adapter für CKAN, Carto oder CSV-Dateien je Jahr.** Houston, San
  Diego, Phoenix, Philadelphia und San Antonio brauchten je einen. Dafür einen
  Adapter auf Vorrat zu schreiben, ohne eine Stadt, die ihn nutzt, hiesse
  Code ohne Prüfstein.
- **Keine allgemeine Silver-Normalisierung.** Die Felder der Städte
  unterscheiden sich in Namen, Granularität und Bedeutung (Abschnitt 1). Ein
  gemeinsames Schema dafür wäre eine Behauptung, die erst eine dritte Stadt
  prüfen könnte.
