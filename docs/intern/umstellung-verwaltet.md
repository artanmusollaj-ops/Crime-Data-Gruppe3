# Umstellung auf den verwalteten Betrieb (S-10): der Ablauf

**Entschieden am 28.11.2026: umstellen.** Christian will den Wochenlauf
über die Konsole testen. Geht der Probelauf schief, folgt der Rückweg
(Schritt 6), und der Lauf wird von Hand über den alten Weg nachgeholt.
Schritt 0 ist der PR „S-10: Der Wochenlauf geht über die Konsole“ vom
28.11.2026. Er hängt auch die Sperre in `pipeline` ein (Punkt 4).

Ursprünglich: **Vorbereitung, kein Entscheid.** Diese Datei hält fest, wie `srv01` vom
Cron-Datenlauf auf den Konsolen-Worker umgestellt wird, wie der erste Lauf
geprüft wird und wie es zurückgeht. Ob umgestellt wird, entscheidet die
Besprechung am Freitag, 27.11.2026. Der Punkt steht als S-10 in
[`offene-punkte.md`](offene-punkte.md); die Befehle selbst stammen aus
[`ENGINEERING_KONSOLE.md`](ENGINEERING_KONSOLE.md), Abschnitt „Auf den
verwalteten Betrieb umstellen“.

Geschrieben am 24.11.2026 aus dem Repository (`main` 097340a). Auf `srv01`
ist dafür nichts geprüft und nichts geändert.

## Was beim Vorbereiten auffiel

1. **Am 30.11. läuft nichts.** Der 30.11. ist der fünfte Montag. `mode_for_day`
   gibt für den 29. bis 31. `skip` zurück, und `srv01-konsole-datenlauf.sh`
   liest dieselbe Regel. Der nächste geplante Lauf ist der vom **7.12.**,
   ein Delta, und das ist bereits der Lauf für den Abgabestand.
   → Der Probelauf muss **von Hand** am Wochenende laufen (Schritt 4).
2. **Der Weg über das Qualitätstor lief auf srv01 noch nie.** Einen
   Kandidaten gebaut und veröffentlicht hat die Konsole dort einmal: am
   18.11.2026, Artans Mapping-Probe „Freigabe Test 03“, freigegeben von einer
   Person (Release `approved-9d265b70…-435090e1`). Einen geplanten Batch mit
   Ingestion und Freigabe durch das Qualitätstor gab es noch nicht. E-5 nennt
   die Abnahme mit einem echten Job weiter als offen.
3. **S-6 ist erledigt und hätte nicht blockiert.** Das Token steht
   spätestens seit dem 18.11.2026 in der `.env`. Ein Wochenlauf
   veröffentlicht ohnehin ohne Git (`release_flow.requires_git` gilt nur für
   Mapping und Einstellungen), und das Qualitätstor gibt ihn ohne zweite
   Person frei (`auto_approval`).
4. **Die Sperre erreicht den Cron-Lauf nicht** (24.11.2026, aus
   `docker-compose.srv01.yml`). `enable-managed` schreibt den Marker nach
   `/app/data/admin/managed.json`, und dort hängt im Worker und im Dienst
   `admin` das Volume `konsole`. Der Dienst `pipeline` hängt `konsole` nicht
   ein. In seinem Container ist `/app/data/admin` der Ordner aus
   `arbeitsdaten`, ohne Marker. `storage.verwaltet` meldet dort also „nicht
   verwaltet“, und `srv01-datenlauf.sh` liefe nach der Umstellung weiter
   durch. `ENGINEERING_KONSOLE.md` und `storage-architektur.md` sagten bis zum
   25.11.2026 das Gegenteil: „der alte Datenlauf scheiterte ab dieser Minute“. Kein Test hält
   die Sperre über Container hinweg, `test_srv01_compose.py` prüft das Volume
   nur für `admin` und `worker`.
   Folgen: Der Tausch der Crontab-Zeilen ist der **einzige** Schutz. Bleibt
   die alte Zeile stehen, veröffentlicht der Cron-Lauf ohne Review. Danach
   weist die Konsole ihre nächste Veröffentlichung ab, weil der aktive Stand
   in S3 dann weder die Alt-Baseline noch ihr eigenes Release ist („SeaweedFS-
   Releasebasis weicht ab“).
   **Abhilfe für Schritt 0:** `konsole:/app/data/admin:ro` auch in `pipeline`
   einhängen, mit einem Test, der für jeden Dienst mit `arbeitsdaten` das
   Volume `konsole` verlangt. **Umgesetzt am 28.11.2026**
   (`test_wer_den_arbeitsraum_beschreibt_sieht_den_marker_der_konsole`).
   Damit bricht in Schritt 3 auch `pipeline` ab.
5. **Die tägliche Konsolensicherung ist seit dem 19.11. 830 MiB gross**
   (vorher 2,2 MiB). Gemessen am 24.11.2026 unter `backups/control/`: sieben
   Archive, zusammen 4,98 GiB. Kein Release ist darin (`releases_archived`
   leer). Das Archiv packt `admin/jobs/` ganz ein. Der Sprung kam einen Tag
   nach dem ersten Kandidaten vom 18.11., und dessen Ordner `jobs/<id>/data`
   trägt einen vollen Bronze-Abzug, Silver und Gold. `job_data.prune` behält
   ihn, weil er zum zuletzt aktivierten Konsolen-Release gehört.
   **Nachgemessen am 25.11.2026** im Volume `konsole` auf srv01: `jobs/`
   belegt 1,1 GiB, fast alles in einem Ordner, `jobs/9d265b70…/data`. Das ist
   der Job hinter `approved-9d265b70c6c34683b8cf7b5ae033f8a6-435090e1`, auf den
   `jobs/ANALYSE.json` zeigt. Darin liegen `bronze` 455 MiB, `releases`
   343 MiB, `silver` 209 MiB, `gold` 84 MiB und `serving` 3 MiB. Die übrigen
   acht Job-Ordner tragen kein `data` und wiegen je höchstens 2,5 MiB, der
   Rest des Volumes zusammen 14 MiB.
   Nach der Umstellung bringt jeder Wochenlauf einen neuen Job-Ordner.
   `ADMIN_JOB_DATA_KEEP` behält zwei (Vorgabe), damit wird jedes Archiv rund
   1,7 GB gross. Gesichert wird nach jedem Takt mit Arbeit, an einem Batch-Tag
   also mehrmals, und sieben Archive bleiben. Das sind rund **12 GB unter
   `backups/control/`**. Am 10.11.2026 lagen dort 11,2 GB, und der Eimer stand
   über seinem Kontingent auf nur-lesen; der Volllauf des Tages scheiterte.
   **Das Kontingent ist heute 24 GiB** (`quota:25769803776`, abgelesen am
   25.11.2026 mit `s3.bucket.list`). Belegt sind 9,7 GiB logisch, 40,4 %;
   gegen diese Zahl rechnet SeaweedFS das Kontingent. Physisch sind es
   11,0 GiB. Mit den rund 12 GB Sicherungen statt heute 5,0 GiB kämen etwa
   6,6 GiB dazu, also rund 16,3 GiB oder zwei Drittel des Kontingents, dazu
   je Wochenlauf ein Release von rund 0,3 GiB. Das läuft nicht über, lässt
   aber wenig Luft für einen zweiten Kandidaten oder einen Volllauf.
   Dasselbe Volume `konsole` geht ausserdem jede Nacht mit restic nach
   Backblaze (S-7).
   **Entschieden am 25.11.2026:** `jobs/*/data` bleibt aus dem Archiv
   (`object_store.backup`, Branch `konsolensicherung-ohne-jobdaten`), denn
   alles darin lässt sich aus Bronze im Eimer nachbauen. Das Archiv wiegt
   danach wieder wenige MiB, die Umstellung bringt unter `backups/control/`
   kein Wachstum mehr. Wirksam ist das erst mit dem nächsten eingesetzten
   Abbild; die sieben Archive mit 830 MiB fallen danach binnen einer Woche
   von selbst weg (`ADMIN_BACKUP_KEEP`).
6. **Drei Stellen im Repository rufen nach der Umstellung den alten Lauf
   auf.** Sie gehören in denselben PR wie der Crontab-Tausch (Schritt 0).

## Schritt 0 – vorher, im Repository (ein PR, vor dem Wochenende gemergt)

- `deploy/cron/urbancrime.crontab`: die Zeile für `srv01-datenlauf.sh`
  auskommentieren und die Zeile für `srv01-konsole-datenlauf.sh`
  einkommentieren. Die Takt-Zeile ist schon aktiv (S-8).
- [`abgabestand.md`](abgabestand.md), Schritt 1: Für den Lauf von Hand steht dort
  `docker/srv01-datenlauf.sh delta`. Das scheitert dann an
  `storage.verwaltet`. Ersatz ist `docker/srv01-konsole-datenlauf.sh delta`
  zum Einreihen, danach die Takte abwarten. Auch der Log-Verweis ändert sich:
  `scheduled-pipeline.log` zeigt dann nur noch das Einreihen, der Lauf selbst
  steht in `logs/konsole-takt.log`.
- `docker/srv01-abbild-einsetzen.sh:185` schlägt nach dem Einsetzen
  `srv01-datenlauf.sh delta` vor. Das wird auf das Einreihen umgestellt,
  oder der Vorschlag hängt am Marker.
- `docker-compose.srv01.yml`: `konsole:/app/data/admin:ro` in `pipeline`,
  dazu der Test (Punkt 4 oben).
- Punkt 5 ist schon erledigt (`object_store.backup` ohne `jobs/*/data`,
  25.11.); vor dem Wochenende muss nur das Abbild mit dieser Änderung
  eingesetzt sein.
- `offene-punkte.md` S-10, `ENGINEERING_KONSOLE.md`, `AENDERUNGEN.md`
  nachführen.

Dieser PR entsteht erst nach dem Entscheid am Freitag.

## Schritt 1 – Vorprüfung auf srv01 (nur lesen)

```bash
ssh netcup
cd /srv/docker/apps/urbancrime
git pull                                  # Crontab und Skripte aus Schritt 0
dc() { docker compose --env-file .env -f docker-compose.srv01.yml "$@"; }

# Kein Lauf aktiv, die Sperre ist frei
flock --nonblock logs/pipeline.lock true && echo frei
# Konsole initialisiert, keine offenen Aufträge
dc run --rm worker python -m platform_admin status \
  --project-root /app --data-root /app/data
# Das Abbild trägt den Code von main
grep PIPELINE_IMAGE .env
# Die aktuelle Crontab sichern
crontab -l > logs/crontab.vor-s10-$(date -u +%Y%m%dT%H%MZ)
```

Was im Volume `konsole` liegt, und das Kontingent des Eimers (Punkt 5):

```bash
dc run --rm --no-deps --entrypoint sh worker -c 'du -sh /app/data/admin/* /app/data/admin/jobs/*'
```


```text
weed shell> s3.bucket.list
```

Die Zeile `urban-crime` nennt `size`, `quota` und `usage`. So stand die
Meldung am 10.11.2026 im Eintrag zum vollen Eimer in `AENDERUNGEN.md`.

`enable-managed` prüft selbst, bricht sonst ab und ändert dann nichts:

- `ADMIN_OBJECT_STORE` stimmt mit `STORAGE_BACKEND` überein (beide `s3` in
  `docker-compose.srv01.yml`).
- Kein Auftrag steht auf QUEUED oder RUNNING.
- Der eingestellte Zeitraum deckt alle Jahre des aktiven Release ab.
  `config/platform_admin_settings.json` setzt 2021-01-01 bis 2027-01-01,
  das passt, sofern `init` mit dieser Datei lief.

## Schritt 2 – Umstellen (im selben Zug)

```bash
dc run --rm worker python -m platform_admin enable-managed \
  --project-root /app --data-root /app/data --operator christian
crontab deploy/cron/urbancrime.crontab
crontab -l | grep -v '^#' | grep datenlauf    # nur noch srv01-konsole-datenlauf.sh
```

`enable-managed` holt das aktive Release aus S3, schreibt
`/app/data/admin/managed.json` (Volume `urbancrime_konsole`) mit dem aktiven
Release als Alt-Baseline und gibt den Eintrag als JSON aus. Die Ausgabe
festhalten.

## Schritt 3 – Prüfen, dass der alte Weg gesperrt ist

```bash
dc run --rm pipeline python -m orchestration.release liste          # lesen geht
dc run --rm pipeline python -m orchestration.release holen aktuell  # muss abbrechen
dc run --rm worker   python -m orchestration.release holen aktuell  # muss abbrechen
```

Erwartet ist in beiden Containern der Abbruch mit „Verwalteter
Datenbestand: Aktion über die Engineering-Konsole …“. `release.py` ruft
`sperre()` vor dem ersten Schreiben auf. Im Worker-Container fehlt bei
`run --rm` mit eigenem Befehl das Token, das der Worker nur seinen
Kindprozessen gibt. Er bricht deshalb ab wie jeder andere Schreiber.

**Ohne die Abhilfe aus Punkt 4 bricht `pipeline` nicht ab.** Dann ist genau
das der Befund, und es geht nicht weiter. Seit dem 28.11.2026 ist sie im
Compose, wirksam nach `git pull` auf srv01, weil `run --rm` die Datei neu
liest. Die Probe richtet auch dann keinen
Schaden an: `holen aktuell` ist der Schritt, den der Cron-Lauf jede Woche
macht.

## Schritt 4 – Probelauf von Hand (Samstag)

```bash
/usr/bin/flock --wait 600 logs/pipeline.lock \
  docker/srv01-konsole-datenlauf.sh delta
tail -f logs/konsole-takt.log
```

Der Slot heisst `scheduled-<Datum>-delta`. Ein zweiter Aufruf am selben Tag
reiht nichts Neues ein. Danach arbeiten die Takte, jeder in einem eigenen
Container und mit bis zu einer Minute Abstand:

1. **Der Batch** (`platform_admin.batch.execute`): Vorprüfung und die
   Ingestion-Stufen, wie im Cron-Delta. Am Ende reiht er den Kandidaten ein.
2. **Der Kandidat** (`candidates.build`): lädt **alles** fertige Bronze aus
   S3 in einen eigenen Job-Ordner, am 24.11. 268 Dateien mit 465 MiB. Dann
   baut er Silver, Gold und Serving über alle Jahre neu, prüft die Qualität,
   erstellt den Impact-Bericht und gibt bei bestandenem Tor frei.
3. **Die Veröffentlichung** (`finish_publication`): Release nach S3,
   `AKTUELL.json`, Job-Zeiger, danach Serving, Drift, Sicherungssatz,
   Laufprotokoll und Betriebsstand.

**Wie lange das dauert.** Für Schritt 2 gibt es eine Messung auf srv01, den
Kandidaten vom 18.11.2026: eingereiht 20:57:05, Gold fertig 21:02:34,
Serving 21:02:40. Das sind **gut fünfeinhalb Minuten** samt Bronze-Abzug
und bis zu einer Minute Warten auf den Takt. Für Schritt 1 gilt die
Ingestion eines Cron-Deltas, ein paar Minuten (der ganze Cron-Delta mit
Ableitung dauerte rund fünf). Schritt 3 ist ein Takt mehr. Zusammen also
**etwa 15 bis 25 Minuten**, wenn keine Quelle ausfällt. Fällt eine aus, fasst
die Ingestion nach 30 und 60 Minuten nach, wie im Cron. Für den Samstag mit
Prüfen gut **eine Stunde** einplanen, mit Nachfassen bis zu zweieinhalb.

**Abnahme**, alle Punkte müssen grün sein:

- [ ] `releases/AKTUELL.json` zeigt ein Release `approved-…`
      (`python -m orchestration.release liste`, lokal mit der s3-`.env`)
- [ ] Freigegeben hat `quality-gate (automatic)`, keine Person
- [ ] Das Dashboard meldet dieses Release (`pruefe_stand` im Protokoll)
- [ ] `pipeline_run.json` und der Betriebsstand sind neu, im Betriebsblick
- [ ] Drift und Sicherungssatz gelaufen (WARNUNG ist zulässig, fehlen nicht)
- [ ] Die Zahl 2024 auf der Überblicksseite ist unverändert: 94,4 / 124,7
- [ ] `docker stats`: Der Worker blieb unter 1'280 MiB
- [ ] E-5, letzter Schritt: Notebook 34 und 37 auf dem Job-Ordner dieses
      Laufs ausführen (Job-Zeiger `jobs/ANALYSE.json`)

## Schritt 5 – Entscheid Sonntag

- **Alles grün:** So lassen. Der 7.12. läuft als Konsolen-Batch, und der
  Abgabestand folgt dem angepassten `abgabestand.md`.
- **Etwas rot und nicht bis Sonntagabend behoben:** zurück (Schritt 6).
  Der 7.12. läuft dann wie bisher über den Cron.

## Schritt 6 – Rückweg

```bash
crontab logs/crontab.vor-s10-<Zeit>                 # alte Zeilen zurück
dc run --rm --no-deps --entrypoint sh worker -c \
  'mv /app/data/admin/managed.json /app/data/admin/managed.json.zurueck-$(date -u +%Y%m%dT%H%MZ)'
```

Verschieben statt löschen, damit der Eintrag erhalten bleibt. Danach greift
`storage.verwaltet` nicht mehr, und der alte Datenlauf läuft wieder.

**Nach dem Rückweg setzt der Cron-Lauf sauber auf** (geprüft am
24.11.2026 im Code):

- Die Konsole legt ihr Release genau wie `storage.release` ab, unter
  `releases/release=<Kennung>/` mit `release.json` zuletzt. Den Zeiger
  `AKTUELL.json` schreibt sie mit derselben Funktion `storage.release.zeiger`.
  `release holen aktuell --einsetzen` und das Dashboard lesen es also wie
  jedes andere.
- Der nächste Cron-Lauf baut sein Release aus dem eigenen Bau und legt
  `AKTUELL.json` darauf. Auf das vorige Release baut er nicht auf, die
  Kennung `approved-…` stört ihn nicht.
- Bis dahin bleibt das Release `approved-…` das aktive. Das ist richtig so:
  Es hat das Qualitätstor bestanden. Wer sofort auf den Cron-Stand zurück
  will, nimmt `orchestration.release zuruecknehmen <alt> --grund "…"`,
  nachdem der Marker beiseite ist. Vorher sperrt es.
- Eine Kleinigkeit: `release liste` sortiert nach Kennung, nicht nach Zeit.
  `approved-…` steht deshalb immer unter allen Kennungen mit Datum. Den
  aktiven Stand zeigt die Marke `<- AKTUELL`, nicht die Position.
- Wer später wieder umstellt, bekommt mit `enable-managed` eine neue
  Alt-Baseline, nämlich das dann aktive Release.

## Nachgesehen

- **Sperre ohne Schreiben zeigen:** erledigt, siehe Schritt 3.
- **`aufraeumen`:** Weder die Crontab noch ein `docker/*.sh` ruft es
  planmässig auf. Dass es unter der Konsole gesperrt ist, stört den Betrieb
  also nicht. Von Hand aufräumen geht danach nur über die Konsole.
- **Rückweg:** Der Cron-Lauf setzt nach einem Konsolen-Release sauber auf,
  siehe Schritt 6.
- **Dauer:** etwa 15 bis 25 Minuten ohne Quellausfall, siehe Schritt 4.

## Für die Besprechung am 27.11.

Von den zwei Befunden oben braucht einer noch einen Entscheid:

1. **Die Sperre in `pipeline` einhängen** (Punkt 4): ja oder nein. Ohne sie
   schützt nur der Crontab-Tausch.
2. **Die Konsolensicherung schlank halten** (Punkt 5): erledigt am 25.11.,
   `jobs/*/data` bleibt aus dem Archiv. Offen ist nur, ob das Abbild vor dem
   Wochenende eingesetzt wird. Am 25.11. gemessen:
   Der Ordner `data` des Kandidaten vom 18.11. ist 1,1 GiB gross und macht
   fast das ganze Archiv aus. Das Kontingent ist 24 GiB, belegt sind 9,7 GiB.
   Mit Umstellung und ohne Entscheid wären es rund 16 GiB. Die 830 MiB je
   Archiv liegen heute schon dort, ohne Umstellung.
