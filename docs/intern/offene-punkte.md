# Offene Punkte

Was liegen geblieben ist, an **einer** Stelle — mit wem es gehört, seit wann
es offen ist und wo der Beleg steht. Angelegt am 19.10.2026.

**Warum es dieses Dokument gibt.** Bis hierher standen offene Punkte an drei
Orten: die Anforderungen in [`fr-stand.md`](fr-stand.md), zurückgestellte
Befunde in `_bmad-output/initiative-ln2/deferred-work.md` (nicht im
Repository, seit dem 15.10. nicht mehr gepflegt, zur Hälfte erledigt), und
alles Betriebliche verstreut in den Einträgen von
[`AENDERUNGEN.md`](AENDERUNGEN.md). Auf die Frage „was ist eigentlich noch
offen?" gab es keine Antwort ohne Suche.

**Was hier nicht steht:** die Anforderungen des PRD. Die führt
[`fr-stand.md`](fr-stand.md), mit Beleg je Zeile und einem Wächter, der sie
gegen das PRD hält — ein zweites Register daneben wäre die Stelle, an der
beide auseinanderlaufen. Stand am 22.11.2026: 51 erfüllt, 4 teilweise,
**9 offen**, 1 zurückgestellt.

**Die Regel.** Jeder offene Punkt hat **eine Kennung, einen Verantwortlichen
und einen Beleg.** Ein Punkt ohne Verantwortlichen ist keiner, sondern ein
Wunsch. `tests/test_offene_punkte.py` hält das. Erledigtes wird nicht
gelöscht, sondern unten mit Datum und Ort vermerkt — wer später fragt, ob
etwas je offen war, findet die Antwort hier.

**Wer:** *Christian* (Silver, Gold, Betrieb, Server), *Artan* (Dokumentation,
Präsentation), *beide*, wenn es eine gemeinsame Entscheidung ist.

---

## Entscheidungen

Punkte, an denen nichts zu bauen ist, bevor jemand entschieden hat.

| Nr | Punkt | Wer | seit | wo belegt |
| --- | --- | --- | --- | --- |
| E-5 | **Wie lesen Notebooks im verwalteten Betrieb?** Artans `serving.release_reader` lenkte sie auf das aktive Release, das aber kein Silver und kein Bronze enthält: Notebook 34 liess 13 von 17 Zellen still leer, 37 brach ab. Nicht übernommen. Lokal unter Windows und Linux/Docker geprüft: [Analysesitzungen mit Sperre und Herkunftsnachweis](notebook-analysesitzungen.md), [Prüfnachweis](e5-pruefnachweis.md). **Auf srv01 abgenommen am 14.11.2026 für den Cron-Datenlauf:** Beide Notebooks liefen vollständig und fehlerfrei auf Release `2026-11-14T09-09-47Z` (Commit `abda4e0`), 37 mit echten Quelländerungen (113'745 Zeilen, 47'681 Delikte). Vorher waren drei Fehler zu beheben (#228–#230). Offen bleibt nur die Abnahme mit einem echten Konsolen-Job; sie gehört zu S-10. | Artan | 30.10.2026 | `AENDERUNGEN.md`, „Die Konsole ist im Repository" |

## Auf dem Server

Handgriffe auf `srv01`, die ausserhalb dieses Repositories liegen.

| Nr | Punkt | Wer | seit | wo belegt |
| --- | --- | --- | --- | --- |
| S-4 | **`christian` in die Gruppe `adm`.** Ohne sie ist das systemd-Journal nur mit `sudo` lesbar — dort stand die Meldung von restic, die 24 Nachtläufe lang niemand sah. `sudo usermod -aG adm christian`, neu anmelden. | Christian | 18.10.2026 | `AENDERUNGEN.md`, „Gesichert wird, was sich nicht nachrechnen lässt" |
| S-6 | **`ADMIN_GITHUB_TOKEN` in die `.env` des Stapels.** Der Rest ist am 31.10.2026 eingetragen: `CF_ACCESS_ISSUER` und `CF_ACCESS_AUD` (aus der Access-Weiterleitung abgelesen), `ADMIN_METRICS_TOKEN` (zufällig erzeugt), `ADMIN_ROLE_BINDINGS` für Christian und Artan. Fehlt nur das Token: Fine-grained, nur dieses Repository, Contents und Pull requests Lesen und Schreiben, Actions Lesen (der Entwicklungsmodus liest die Workflow-Läufe des PR-Heads; ein Recht „Checks“ gibt es für diese Tokens nicht); Administration Lesen erst ab `produktiv`, das die Schutzregeln liest. Das Repository gehört Artans persönlichem Konto, und ein Fine-grained-Token reicht nur an Repositories des eigenen Kontos oder einer Organisation — Artan erstellt es also; die Alternative ist ein klassisches Token mit `repo`, das an alle Repositories der Person reicht. Von Hand eintragen, nicht über den Chat. Ohne es legt die Konsole keine PRs an. | Christian | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“, Punkt 2 |
| S-10 | **Auf den verwalteten Betrieb umstellen**, wenn die Konsole läuft (S-8): `run --rm worker python -m platform_admin enable-managed …`, im selben Zug in `deploy/cron/urbancrime.crontab` die Datenlauf-Zeile aus- und die Zeile für `srv01-konsole-datenlauf.sh` einkommentieren, `crontab` neu laden. Danach scheitert der alte Datenlauf an `storage.verwaltet` — die beiden Zeilen gehören zusammen getauscht. Den ersten Montag danach im Betriebsblick prüfen: Protokoll, Drift, Sicherungssatz. Dazu der letzte Schritt von E-5: Notebook 34 und 37 auf dem Datenordner des ersten Konsolen-Jobs ausführen, Job-Zeiger und Löschregel für Job-Ordner sind seit dem 14.11.2026 gebaut (`platform_admin.job_data`, #232). | Christian | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“; `tests/test_srv01_konsole_takt.py` |

## Im Code

| Nr | Punkt | Wer | seit | wo belegt |
| --- | --- | --- | --- | --- |
| C-6 | **Eine Karte je Deliktfamilie.** Möglich, kostet aber eine Dimension in `serving/rate_tract`. Kein Fehler, eine Erweiterung. | Christian | 15.10.2026 | `deferred-work.md` Nr. 27 |
| C-7 | **Die Konsole im Betriebsblick.** `admin` liegt noch nicht im Netz `monitoring`, und Prometheus holt `/metrics` nicht ab; Artans Grafana-Brett ist nicht übernommen. Mit der Einrichtung (S-8) nachziehen, wie bei `start` mit Alias `urbancrime-admin`. | Christian | 30.10.2026 | `AENDERUNGEN.md`, „Die Konsole hat einen Platz auf srv01" |

---

## Erledigt

Aus `deferred-work.md` übernommen und abgehakt. Die Nummern sind die
Reihenfolge der Einträge dort.

| aus | Punkt | erledigt | wo |
| --- | --- | --- | --- |
| Nr. 2, 4, 5, 20 | ungesicherte und veraltete Testzahlen in `README.md` und `architektur-ist-und-ziel.md` | bis 18.10.2026 | alle Stellen sind jetzt bewacht (`test_abgabedokumente.py`, `test_architektur_dokument.py`, `test_unterstroemungen.py`); die Frischklon-Zahl wird je Änderung gemessen |
| Nr. 6, 7 | Frischklon-Zahl | 4.10.2026 | dort schon vermerkt |
| Nr. 8, 9, 12 | laufender Stapel und Zeitplan auf `srv01` unbelegt | 11.10.2026 | dort schon vermerkt |
| Nr. 10 | Elasticsearch-Datenträger in die Serversicherung | **verworfen** am 18.10.2026 | Er ist abgeleitet und aus dem Release in Minuten neu ladbar; er wurde aus `backup.volumes` *entfernt*, nicht hinzugefügt (`storage-architektur.md`, „Gesichert wird, was sich nicht nachrechnen lässt") |
| Nr. 11 | Testzahl in `AGENTS.md` | 18.10.2026 | wird je Änderung nachgezogen |
| Nr. 13 | `docker/srv01-datenlauf.sh` nicht im Repository | vor dem 17.10.2026 | liegt in `docker/`, mit Wächtern in `tests/test_srv01_datenlauf.py` |
| Nr. 14 | ob die Strecke auf `srv01` je durchlief | 17.10.2026 | grüner Lauf, Release `2026-10-17T13-21-03Z` |
| Nr. 15, 21 | FR-16, Zeitfenster | 11.10.2026 | dort schon vermerkt |
| Nr. 17 | die öffentliche Seite (FR-31 bis FR-33) | 18.10.2026 | FR-33 zuletzt, `fr-stand.md` |
| Nr. 18 | FR-27-Angaben für die älteren Kacheln | 17.11.2026 | alle 18 Lens-Kacheln tragen sie, FR-27 steht in `fr-stand.md` auf ● |
| Nr. 22, 23, 25 | Tunnel-Route, S3-Schlüssel, Karte | dort schon vermerkt | |
| Nr. 24 | Lauf vom 12.10. nach 26 von 39 Stufen abgebrochen | 17.10.2026 | überholt durch den grünen Lauf |
| E-1 | ob die Dokumentzahlen auf den Serverstand gehen | **ja** — entschieden am 12.11.2026, nachgezogen auf den Volllauf vom 10.11.2026 (Release `2026-11-10T13-47-23Z`) | Detroit 134,0 je 1'000 (Tatebene, 2024), Fallebene 124,7; die zwölf Läufe als `LN2` gepinnt. `AENDERUNGEN.md`, „Die Dokumente stehen auf dem Stand vom 10.11.2026“ |
| E-2 | ob die Fall- oder die Tatebene vorn steht | **Fallebene** — beschlossen am 5.10.2026 (E5 im PRD), in den Dokumenten seit dem 12.11.2026: Kopftabellen, Konzept 5.2/5.4/9, `eine-zahl.md`, Einseiter, Einstiegsseite, Driftbericht | `AENDERUNGEN.md`, „Die Fallebene steht vorn" |
| E-3 | ob die Versionierung des Eimers `urban-crime` abgeschaltet wird | **ja** — am 12.11.2026 auf `srv01` ausgesetzt (`s3.bucket.versioning -suspend`; ganz abschalten kennt S3 nicht) | `storage-architektur.md`, „Der Eimer war versioniert" |
| E-4 | was der Konsolen-Worker vom Datenlauf übernimmt | **alles** — entschieden und umgesetzt am 30.10.2026 | Drift und Sicherungssatz nach dem Serving, Laufprotokoll und Betriebsstand nach jedem Takt, Montagsrhythmus über `srv01-konsole-datenlauf.sh`, Wochenläufe vom Qualitätstor freigegeben; Paritätswächter `test_the_worker_covers_every_step_of_the_cron_run`. `AENDERUNGEN.md`, „Der Worker übernimmt den Datenlauf“ |
| S-7 | `urbancrime_konsole` in `backup.volumes` | 31.10.2026 | `/srv/docker/config/srv01.yaml`, `required: true`, neben `urbancrime_sicherung`; die alte Fassung liegt daneben als `srv01.yaml.vor-konsole-*` |
| S-5 | Tunnel-Route `urbancrime-admin.datenwerft.ch` | 31.10.2026 | von aussen gemessen: 302 auf dieselbe Access-Anwendung wie Kibana (`kid=7b915eae…`), ein zufälliger Name hat kein DNS; von innen über Traefik `/healthz` 200, `/api/state` ohne Anmeldung 401 |
| S-8 | Takt eingeschaltet | 31.10.2026 | Abbild `554fd02` mit dem Fix gegen den HEAD-403 eingesetzt; Probetakt grün, die Kontrollsicherung `backups/control/…tar.gz` geschrieben, Worker `ok`; danach die Takt-Zeile einkommentiert und `crontab` neu geladen, die alte Fassung liegt als `logs/crontab.vor-takt-*`. Die Datenlauf-Zeile bleibt bis S-10 |
| S-9 | `admin` nachgemessen | 31.10.2026 | Auf `srv01` 52 MiB in Ruhe, Spitze 66 MiB. Der Impact-Download hätte die 160 MiB gesprengt (lokal 223 MiB beim ungünstigsten Archiv). Er streamt jetzt und bleibt bei 46 MiB, die Grenze bleibt |
| C-10 | `comparison_month` misst Teilmonate je Stadt | 1.11.2026 | `serving.build_comparison` Vertrag 3: `days_in_window` am Fenster je `reporting_city`. Chicagos September 2026 ist damit eine Teilperiode (26 von 30 Tagen). Greift mit dem nächsten Release; das Dashboard rechnet bis dahin selbst je Stadt. `tests/serving/test_build_comparison.py::test_das_fenster_gilt_je_stadt` |
| C-11 | Das Dashboard rechnet die Rate auf der Tatebene | 14.11.2026 | Die Ratentafel im Überblick zählt Fälle (`count(*) FILTER (counts_case)`), die Tatebene steht als Hinweis daneben (E5). 2024 auf dem Release vom 10.11.2026: 94,5 und 124,7, daneben 94,5 und 134,0. `tests/serving/test_dashboard.py::test_die_balken_stehen_auf_der_fallebene_die_tatebene_daneben` |
| C-2 | Sechs `publish`-Aufrufe ohne `ordnung` | 22.11.2026 | Jeder Aufruf nennt einen eindeutigen Schlüssel, und `publish` prüft die Eindeutigkeit selbst. Zwei Neubauten in getrennten Prozessen mit 1 und 8 Threads: alle 24 Parquet-Dateien byteweise gleich. `tests/test_publish_ordnung.py` hält, dass kein Aufruf ohne `ordnung` dazukommt |
| S-1 | 3,91 GiB alte Fassungen entfernt | 10.11.2026, geschlossen am 23.11.2026 | Das Aufräumen vom 10.11.2026 (`--loeschen --fassungen --auch-fern`, zweiter Durchgang) hat sie entfernt; die Zeile blieb danach offen stehen. Der Trockenlauf vom 23.11.2026 auf `srv01` zeigt noch 28 alte Fassungen mit 169,5 MB, 8 Löschmarkierungen, 7 entbehrliche Releases mit 1'278 MB und 1 entbehrlichen Lauf mit 24,6 MB. **Bewusst nicht gelöscht:** `--fassungen` geht nur mit `--loeschen --auch-fern` und nähme die Releases mit. Rund 1,5 GB sind kein Druck, und vor der Abgabe gewinnt das Löschen nichts. Das nächste Aufräumen kommt nach der Abgabe |
| S-2 | Die `srv01`-CLI committet | 22.11.2026 | Commit `fad61f3` auf dem Branch `infra/urbancrime-monitoring` von `datenwerft/srv01-infrastructure`: `health.py` klappt die gruppierte restic-Ausgabe auf, `util.py` schreibt die Fehlermeldung ins Protokoll. Dazu zwei Tests, die am alten Code scheitern; die CLI-Suite läuft mit 100 Tests grün. Gemergt ist der Branch noch nicht |
| S-3 | Der Monitoring-Stapel committet | 22.11.2026 | Commit `26a855b` auf demselben Branch: Scrape `urbancrime`, die zweite `rule_files`-Zeile, die beiden Verzeichnis-Einhängungen und `grafana/provisioning/dashboards/urbancrime.yaml`. `promtool check config` meldet 9 Regeln, `docker compose config` ist gültig. Nicht dabei, weil nicht von diesem Vorhaben: die cAdvisor-Drosselung und der Scrape `seaweedfs`, die im Arbeitsstand daneben liegen |
| C-9 | Das eigene Dashboard auf `srv01`, Kibana abgelöst | 22.11.2026 abgehakt | Eingesetzt am 1.11.2026, Elasticsearch und Kibana am 6.11.2026 von `srv01` entfernt. Die beiden letzten Reste waren schon erledigt, nur nicht hier: Der Kibana-Tunnel läuft auf `srv01` (Dienst `kibana`, am 22.11.2026 seit sechs Tagen gesund, im Browser belegt am 15.11.2026), und die Einstiegsseite führt die Konsole seit dem 1.11.2026 als Zugang statt als „künftig“ |
| C-8 | Der Auslagerungstest wackelte auf CI | 22.11.2026 | Gemessen, je drei Versuche *mit* Auslagerung: Zwei Threads scheitern bis 130 MB immer, bei 140 MB zweimal von drei, ab 150 MB nie. Die alte Grenze lag also auf der Kante. Ein Thread kommt ab 90 MB durch. Der Test läuft jetzt mit einem Thread und 250 MB. Ohne Auslagerung scheitert er dort weiter sicher, weil die Abfrage rund 1 GB sortiert (`tests/storage/test_duckdb.py`) |
| C-5 | Detroits Abdeckungsquote nach Ingestionshäufigkeit gewichtet | 4.10.2026, abgehakt am 22.11.2026 | Der Anteil ist am 4.10.2026 aus `test_micr_nibrs_mapping.py` entfallen. Der Kommentar dort nennt den Grund (452'980 Zeilen für 253'838 Fälle, Faktor 1,78), und die Chicagoer Seite sagt dasselbe. Entdoppelt steht die Abdeckung im Manifest von `gold/fact_offense`, je Stadt (`coverage_percent_by_city`) und je Jahrgang (`mapping_by_year`) |
| C-3 | `build_kibana` löschte nie | 22.11.2026 | `raeume_auf` löscht nach dem Anlegen eigene Objekte, die im neuen Stand fehlen. Eigene erkennt es an der Kennung (`crime-`, `lens-crime-`, `karte-crime-`), fremde bleiben stehen. Es räumt nur aus `main` auf und nie in `lege_an`, weil die Live-Tests dort ein Probebrett anlegen. An einem laufenden Kibana noch nicht erprobt; der erste Start der Probe zeigt es |
| C-4 | Der Wächter über PR-Nummern sah die höchste nicht | 22.11.2026 | Die Obergrenze steht jetzt fest auf #152 und wird selbst geprüft. Fehlt der höchste Eintrag, wird der Test rot (Probe am Text gemacht). Dabei fiel auf: Ab #153 nennen die Überschriften den Branch, und für diese Pull Requests prüft der Wächter nichts. Ein Abgleich über die Commit-Titel trägt nicht, weil die Titel abweichen. Der Docstring sagt das jetzt |
| C-1 | Die Drift-Tabelle sagte nicht, welche Grösse die Toleranz reisst | 22.11.2026 | Das Panel „Abweichung je Groesse“ führt `drift_ueberschritten`, `drift` und `drift_prozent` je Grösse zusammen. Die Spalte „Toleranz“ zeigt „reisst“ rot, und die gerissenen Grössen stehen oben. Die Beschreibung nennt beide Regeln (Raten absolut 0,1, Zählungen 1 %). `tests/test_grafana_brett.py` hält sie gegen `orchestration.drift`. Wirksam auf `srv01` nach `git pull` dort, weil das Brett aus dem Repository eingehängt ist |
