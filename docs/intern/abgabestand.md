# Abgabestand: der Ablauf am Tag, an dem gepinnt wird

Der Stand vom 20.11.2026 (Release `2026-11-20T10-08-03Z`) ist ein
**Zwischenstand**. Diese Datei hält fest, was am Tag des Abgabestands in
welcher Reihenfolge passiert. Dann muss nichts mehr erfunden werden. Ein Pin ist
endgültig: Was in `config/referenzstand.csv` steht, wird nie aufgeräumt. Erst
pinnen, wenn alle Schritte davor grün sind.

## Wann

Das Kolloquium ist am Samstag, 12.12.2026. Die Abgabe ist am Vortag um 14:00 Uhr
(`leistungsnachweise.md`, 10.5), und der letzte Arbeitstag ist damit
**Donnerstag, 10.12.** Der Abgabestand sollte zwei Tage früher stehen, damit
für die Nachweise und das Nachziehen Luft bleibt.

Bis dahin baut der Zeitplan auf `srv01` (`docker/srv01-datenlauf.sh auto`,
montags 04:30) noch diese Läufe:

| Montag | Tag im Monat | Lauf |
| --- | ---: | --- |
| 23.11. | 23 | Delta |
| 30.11. | 30 | keiner (Tag 29 bis 31 fällt aus) |
| 7.12. | 7 | Delta |

Einen Volllauf gibt es vor der Abgabe nicht mehr: Der nächste fällt auf
Montag, 14.12. **Vorschlag:** Der Montagslauf vom 7.12. wird zum Abgabestand,
abgeleitet wird am 8.12. Der Lauf kommt ohne Handgriff, und es bleiben zwei
Tage Reserve. Läuft er rot, ist der Rückweg ein Delta-Lauf von Hand am selben
Tag (Schritt 1). Die Entscheidung trifft Christian.

**Voraussetzung: das Abbild auf `srv01` trägt den gültigen Gold-Vertrag.**
Heute ist das Vertrag 12 (`gold_pipeline.build_gold.CONTRACT_VERSION`). Erfüllt
seit dem 25.11.2026: Das Release `2026-11-25T12-38-05Z` ist auf `srv01` mit
Vertrag 12 gebaut, mit Polizeibezirken und Stadtteilen. Kommt vor dem 7.12.
noch ein Vertrag dazu, muss das Abbild vorher eingesetzt sein
(`docker/srv01-abbild-einsetzen.sh`, nur auf Christians Anweisung). Danach
prüfen, dass `gold/fact_offense` im Release die gültige `contract_version`
nennt. Bis zum 25.11. stand hier Vertrag 10: Ohne ihn hätten am Chicagoer
Seeufer elf Tracts gefehlt.

## Die Schritte

### 1. Den Lauf auf `srv01` prüfen, oder einen anstossen

```bash
ssh netcup 'cd /srv/docker/apps/urbancrime && tail -20 logs/scheduled-pipeline.log'
python -m orchestration.release liste           # lokal, mit .env (s3): das jüngste Release oben
```

Ist der Montagslauf rot oder fehlt er, dann einen Delta-Lauf von Hand
starten, unter derselben Sperre wie der Zeitplan:

```bash
ssh netcup 'cd /srv/docker/apps/urbancrime && L=logs/abgabestand-$(date -u +%Y%m%dT%H%MZ).log && nohup setsid /usr/bin/flock --wait 600 logs/pipeline.lock docker/srv01-datenlauf.sh delta > $L 2>&1 < /dev/null &'
```

Danach ist das neue Release das aktive auf `srv01`, und das Dashboard hat es
spätestens eine Minute später geladen. Die Kennung notieren, unten heisst sie
`<release>`.

### 2. Den Stand lokal genau so herstellen

Die lokale `.env` steht auf `s3`. Ab hier läuft jeder Befehl, der baut oder
erzeugt, mit `STORAGE_BACKEND=local`, sonst publiziert er in den gemeinsamen
Eimer.

1. Den alten lokalen Stand beiseitelegen: `data/silver`, `data/gold`,
   `data/serving` und `data/pipeline_run.json`.
2. Silver, Gold, Serving und `pipeline_run.json` aus dem Arbeitsvolume von
   `srv01` holen. Das sind die Bytes, aus denen das Release entstand.
   Neu gebaut wird nichts.

   ```bash
   ssh netcup 'cd /srv/docker/apps/urbancrime && docker compose -f docker-compose.srv01.yml run --rm --no-deps -T pipeline sh -c "cd /app/data && tar czf - silver gold serving pipeline_run.json"' > /tmp/abgabestand.tgz
   tar xzf /tmp/abgabestand.tgz -C data
   ```

3. Die Bronze-Läufe holen, die Silver nennt (`derived_from`). `srv01` hält
   lokal nur einen Lauf, die Deltas liegen im Eimer. Mit der `.env`:

   ```bash
   python -m storage holen               # zeigt, was fehlt
   python -m storage holen --wirklich    # holt es, Manifest zuletzt
   ```

4. Das Release einsetzen, dann das lokale Elasticsearch neu laden:

   ```bash
   python -m orchestration.release holen <release> --einsetzen
   STORAGE_BACKEND=local python -m serving.load_elasticsearch
   ```

Gegenprobe: `silver/dataset=crime_offense/manifest.json` trägt denselben
`input_fingerprint` wie der Silver-Eintrag in `derived_from` von
`releases/release=<release>/release.json`.

### 3. Pinnen

Auf einem Branch von `main`:

```bash
STORAGE_BACKEND=local python -m orchestration.aufraeumen --pinnen Abgabe
```

Der Befehl leitet die Läufe aus den lokalen Manifesten ab und hängt sie an
`config/referenzstand.csv` an. Das Release selbst steht dort nicht von
allein: Die Zeile `<release>,releases,Abgabe,<Datum>` von Hand dazuschreiben,
so wie am 12.11. für `LN2`. Die Pins aus LN1, `stand-2026-10-03` und LN2
bleiben unverändert.

Auf `srv01` liest `orchestration.aufraeumen` das Register aus dem Abbild
(`/app/config`). Der Pin schützt die Läufe dort also erst, wenn ein Abbild
mit dieser Fassung eingesetzt ist. Bis dahin auf `srv01` nicht aufräumen.

### 4. Notebook 34 korrigieren, dann die Nachweise erneuern

Seit Gold-Vertrag 9 führt `dim_city_day` auch Tage ohne Wetter. Die Abfrage
„warme gegen kalte Tage“ in Notebook 34 bekommt deshalb eine dritte Gruppe
`NULL`. Die Korrektur ist eine Zeile:

```sql
WHERE f.reporting_city = 'chicago' AND w.temp_max_c IS NOT NULL GROUP BY 1
```

**Im selben Commit: der Text zu H6 in Notebook 36.** Die Markdown-Zellen 30
und 31 nennen fest „27 Sekunden“, „Faktor 22“ und „Median 27 s, Spannweite
27 bis 31 s“. Diese Werte stammen aus der Zeit mit einem Jahrgang. Die
Ausgabe darüber misst im Nachweis vom 14.11.2026 schon 24,2 s und Faktor 25
(gefunden am 21.11.2026). Den Text so fassen, dass er keine Zahl wiederholt,
die erst die Messung liefert, zum Beispiel „Der Median liegt rund eine
Grössenordnung unter dem Budget (Messung oben)“. Steht eine feste Zahl darin,
zeigt die HTML-Datei des neuen Nachweises sie neben einer Ausgabe, die anders
lautet. Der Code-Abdruck in `tests/test_nachweise.py` umfasst nur die
Codezellen, eine Änderung am Markdown macht den Nachweis also nicht rot. Der
Text muss aber **vor** `build_nachweise` stimmen, weil das HTML ihn so
festhält, wie er beim Bau dastand.

Beides geht **mit** dem neuen Nachweis in denselben Pull Request.
`tests/test_nachweise.py` hält den Code-Abdruck jedes Notebooks gegen seinen
Nachweis und ist dazwischen rot. `tools/build_nachweise.py` läuft nur von
einem sauberen Commit:

```bash
git commit -am "Notebook 34 zählt nur Tage mit Wetter, Notebook 36 nennt H6 ohne feste Zahl"
python tools/build_nachweise.py
```

Das Werkzeug baut in einer Kopie neu (Notebook 36 dreimal) und schreibt
`docs/nachweise/<datum>_<commit>/`. In `nachweis.json` muss
`release_passt_zum_arbeitsstand` auf `true` stehen, sonst ist der
Datenstand aus Schritt 2 nicht der, den die Notebooks gelesen haben.

### 5. Die erzeugten Dateien neu bauen

```bash
STORAGE_BACKEND=local python tools/build_feldkatalog.py
STORAGE_BACKEND=local python -m serving.build_einstieg
STORAGE_BACKEND=local python tools/build_platzbedarf.py
```

Die Grössenzeilen aus `platzbedarf.md` gehen von Hand in
`architektur-ist-und-ziel.md` und in den Einseiter. Die Wächter dazu nennen
jede Zelle, die abweicht.

### 6. Die Dokumente nachziehen

```bash
python -m pytest -m referenzstand
```

Jede rote Zahl einzeln ersetzen, nie mit `sed` über alle Dokumente. Dieselbe
Ziffernfolge kann eine andere Messung sein. Dazu kommen die Zahlen ohne
Wächter, die aus denselben Grössen folgen. Der Vergleich gegen das Release vom
20.11. findet sie (`tools/vergleiche_releases.py`). Danach ändern sich drei
Stellen im Wortlaut:

- „Zwischenstand vom 20.11.2026 … nicht der Abgabestand“ wird zu
  „Abgabestand vom …“. Diese Stellen stehen in `ln2_konzept.md`,
  `eine-zahl.md`, `zaehlperspektiven.md` (zweimal),
  `architektur-ist-und-ziel.md` und `datenhistorie.md`.
- In `eine-zahl.md` fällt „Gepinnt ist dieser Zwischenstand **nicht**“ weg.
- Der Kopf von `AENDERUNGEN.md` („Der Stand in Zahlen“) bekommt den neuen
  Stand. Der Eintrag dazu nennt das Release, die Pins und die Nachweise.
- **Was Vertrag 10 verschiebt** (lokal gemessen am 21.11.2026, Jahrgang
  2024). Chicago hat 793 statt 782 Tracts und 2'713'800 statt 2'661'953
  Einwohner. Die Fälle innerhalb der Stadt steigen von 251'483 auf 256'317,
  ausserhalb der Stadt sinken sie von 6'010 auf 1'176. Die Rate bleibt bei
  rund 94,4 je 1'000, weil Zähler und Nenner zusammen wachsen. Detroit ändert
  sich nicht. Die Wächter melden jede Stelle.
- **Zwei Stellen, die kein Wächter sieht.** Erstens: `ln2_konzept.md`,
  Absatz „Die Stadtgrenze: der Nenner, den es vorher nicht gab“, erklärt den
  Abstand zwischen Chicagos Mehrheitsregel und dem Zensus 2020 als
  „Unterschied zwischen einer ACS-Schätzung und einer Zählung, nicht ein
  Fehler der Regel“. Rund 52'000 der damals 84'000 Einwohner Abstand waren
  aber die Seeufer-Tracts. Den Satz mit den neuen Zahlen neu fassen, und
  dabei die Aussage von Notebook 34 zur Mehrheitsregel prüfen. Das ist
  Artans Dokument: ein Textvorschlag an ihn. Zweitens: Kapitel 9 („Grenzen“)
  führt 5'249 Chicagoer Delikte in Tracts, die „mehrheitlich zur
  Nachbargemeinde“ gehören, und eine um gut einen Punkt untertriebene Rate.
  Der grösste Teil davon lag in den Seeufer-Tracts, die nicht zu einer
  Nachbargemeinde gehören, sondern am Wasser scheiterten. Diese Limitation
  mit Notebook 34, Abschnitt 3.2, neu messen und neu fassen.
- `feldkatalog.md` neu erzeugen (Schritt 5). Die Beschreibung von
  `city_area_share` hat sich mit Vertrag 10 geändert.

Zum Schluss die volle Suite, einmal `python -m pytest` und einmal
`python -m pytest -m referenzstand`. Beide müssen grün sein.

### 7. Einsetzen und festhalten

1. Pull Request, CI grün, Merge (Christian).
2. Das Abbild mit dem neuen `config/referenzstand.csv` auf `srv01` einsetzen
   (`docker/srv01-abbild-einsetzen.sh`). Erst damit gilt der Pin auch dort.
3. `orchestration.sicherungssatz` läuft am Ende jedes Datenlaufs und hat das
   Release als aktuelles schon im Volume `urbancrime_sicherung`. Mit dem
   Abbild aus 7.2 bleibt es dort auch als gepinntes, wenn später ein neueres
   Release aktiv wird.
4. In `leistungsnachweise.md`, 10.5, das Kästchen „Referenzstand als Release
   veröffentlicht“ abhaken. Das Dokument gehört Artan, also gibt Christian ihm
   Bescheid.

## Was nicht dazugehört

- **Kein neuer Datenlauf nach dem Pin.** Der Montagslauf vom 14.12. kommt
  nach dem Kolloquium und stört nicht. Ein Lauf von Hand zwischen Pin und
  Abgabe macht dagegen ein neueres Release zum aktiven. Dann zeigen Dashboard
  und Startseite einen anderen Stand als die Dokumente.
  `python -m orchestration.release zuruecknehmen <release> --grund "..."`
  holt den Zeiger zurück.
- **Kein `aufraeumen --loeschen` auf `srv01`, bevor das Abbild aus 7.2
  eingesetzt ist.** Bis dahin kennt es den Pin dort nicht.
