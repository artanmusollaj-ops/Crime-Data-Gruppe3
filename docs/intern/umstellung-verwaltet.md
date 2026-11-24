# Umstellung auf den verwalteten Betrieb (S-10): der Ablauf

**Vorbereitung, kein Entscheid.** Diese Datei hält fest, wie `srv01` vom
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
2. **Noch nie lief ein echter Konsolen-Batch auf srv01.** S-8 hatte nur einen
   leeren Probetakt (31.10.). E-5 sagt ausdrücklich: offen ist „die Abnahme
   mit einem echten Konsolen-Job“. Der Lauf am Wochenende ist also der erste.
3. **S-6 blockiert nicht.** Ein Wochenlauf veröffentlicht ohne Git
   (`release_flow.requires_git` gilt nur für Mapping und Einstellungen), und
   das Qualitätstor gibt ihn ohne zweite Person frei (`auto_approval`).
   Ohne Token legt die Konsole nur keine PRs an.
4. **Drei Stellen im Repository rufen nach der Umstellung den gesperrten
   Lauf auf.** Sie gehören in denselben PR wie der Crontab-Tausch (Schritt 0).

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
```

Erwartet ist der Abbruch mit „Verwalteter Datenbestand: Aktion über die
Engineering-Konsole …“. `release.py` ruft `sperre()` vor dem ersten
Schreiben auf. Selbst wenn der Abbruch ausbleibt, richtet die Probe keinen
Schaden an: `holen aktuell` ist genau der Schritt, den der Cron-Lauf jede
Woche macht. Dann stimmt aber der Marker nicht, und es geht nicht weiter.

## Schritt 4 – Probelauf von Hand (Samstag)

```bash
/usr/bin/flock --wait 600 logs/pipeline.lock \
  docker/srv01-konsole-datenlauf.sh delta
tail -f logs/konsole-takt.log
```

Der Slot heisst `scheduled-<Datum>-delta`. Ein zweiter Aufruf am selben Tag
reiht nichts Neues ein. Danach erledigen die Takte jede Minute einen Teil:
Quellen laden, Kandidaten bauen, Qualitätstor, Freigabe, Veröffentlichung,
Serving, Drift, Sicherungssatz, Laufprotokoll. Ein Delta dauerte im Cron
rund fünf Minuten. Unter der Konsole wird es länger, weil jeder Takt ein
eigener Container ist.

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

**Offen:** Ein schon veröffentlichtes Release `approved-…` bleibt das aktive.
Zurück auf das Cron-Release ginge über `orchestration.release holen
<alt> --einsetzen`. Ob ein Cron-Lauf nach einem Konsolen-Release sauber aufsetzt, steht unten
unter „Noch offen“.

## Nachgesehen

- **Sperre ohne Schreiben zeigen:** erledigt, siehe Schritt 3.
- **`aufraeumen`:** Weder die Crontab noch ein `docker/*.sh` ruft es
  planmässig auf. Dass es unter der Konsole gesperrt ist, stört den Betrieb
  also nicht. Von Hand aufräumen geht danach nur über die Konsole.

## Noch offen, vor Freitag zu klären

- Ob ein Cron-Lauf nach einem Konsolen-Release `approved-…` sauber aufsetzt.
  Das betrifft nur den Rückweg.
- Wie lange ein Delta unter Takten dauert. Das bestimmt, wie viel Zeit
  Samstag einzuplanen ist.
