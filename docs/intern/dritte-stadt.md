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

Die Reihenfolge ist die der Strecke. Jeder Punkt nennt die Stelle im Code.

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
12. **Das Dashboard:** `STAEDTE` und `STADTNAMEN` in
    [`serving/dashboard/__init__.py`](../../src/crime/serving/dashboard/__init__.py),
    dazu die Farben in `static/dashboard.css` (`--chicago`, `--detroit`).
13. **Kibana:** der Kartenausschnitt je Stadt (`KARTE_JE_STADT`) in
    [`serving/build_kibana.py`](../../src/crime/serving/build_kibana.py)
    (`karte_objekt` bricht ab, wenn eine Stadt fehlt).
14. **Die Register:** Fünf Register müssen mitgeführt werden, sonst bricht ein
    Test (siehe `AGENTS.md`). Dazu kommen ein Eintrag in den
    Vertragsversionen von `docs/intern/AENDERUNGEN.md`, die Notebooks und die
    Zahlen der Abgabedokumente samt ihren Referenzstand-Wächtern.

## 4. Was bewusst nicht vorbereitet ist

- **Keine Adapter für CKAN, Carto oder CSV-Dateien je Jahr.** Houston, San
  Diego, Phoenix, Philadelphia und San Antonio brauchten je einen. Dafür einen
  Adapter auf Vorrat zu schreiben, ohne eine Stadt, die ihn nutzt, hiesse
  Code ohne Prüfstein.
- **Keine allgemeine Silver-Normalisierung.** Die Felder der Städte
  unterscheiden sich in Namen, Granularität und Bedeutung (Abschnitt 1). Ein
  gemeinsames Schema dafür wäre eine Behauptung, die erst eine dritte Stadt
  prüfen könnte.
