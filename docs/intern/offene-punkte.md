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
beide auseinanderlaufen. Stand am 19.10.2026: 38 erfüllt, 15 teilweise,
**10 offen**, 2 zurückgestellt.

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
| S-1 | **3,91 GiB alte Fassungen entfernen**, danach SeaweedFS kompaktieren. Für die Serversicherung zählt es nicht mehr (`seaweedfs_data` ist aus der Policy), für Platte und SeaweedFS-Kontingent schon. `aufraeumen --loeschen --auch-fern --fassungen`, dann `/vol/vacuum`. | Christian | 18.10.2026 | `AENDERUNGEN.md`, „Ein Löschen, das nie etwas freigegeben hat" |
| S-2 | **Die `srv01`-CLI committen.** Zwei Änderungen liegen ungesichert in `/srv/docker/tools/srv01-cli/`: `health.py` klappt die gruppierte restic-Ausgabe auf (vorher meldete `doctor` bei jedem Lauf „No valid Restic snapshot found"), `util.py` schreibt den Fehlertext ins Protokoll. Sicherungskopien liegen in `/tmp/*.bak`. | Christian | 18.10.2026 | `AENDERUNGEN.md`, „FR-17 ist belegt, nicht beschrieben" |
| S-3 | **Den Monitoring-Stapel committen.** Geändert: `prometheus/prometheus.yaml` (Scrape, zweite `rule_files`-Zeile), `compose.yaml` (zwei Einhängungen), neu `grafana/provisioning/dashboards/urbancrime.yaml`. | Christian | 18.10.2026 | `storage-architektur.md`, „Der Meldeweg" und „Das Brett in Grafana" |
| S-4 | **`christian` in die Gruppe `adm`.** Ohne sie ist das systemd-Journal nur mit `sudo` lesbar — dort stand die Meldung von restic, die 24 Nachtläufe lang niemand sah. `sudo usermod -aG adm christian`, neu anmelden. | Christian | 18.10.2026 | `AENDERUNGEN.md`, „Gesichert wird, was sich nicht nachrechnen lässt" |
| S-6 | **`ADMIN_GITHUB_TOKEN` in die `.env` des Stapels.** Der Rest ist am 31.10.2026 eingetragen: `CF_ACCESS_ISSUER` und `CF_ACCESS_AUD` (aus der Access-Weiterleitung abgelesen), `ADMIN_METRICS_TOKEN` (zufällig erzeugt), `ADMIN_ROLE_BINDINGS` für Christian und Artan. Fehlt nur das Token: Fine-grained, nur dieses Repository, Contents und Pull requests Lesen und Schreiben, Actions Lesen (der Entwicklungsmodus liest die Workflow-Läufe des PR-Heads; ein Recht „Checks“ gibt es für diese Tokens nicht); Administration Lesen erst ab `produktiv`, das die Schutzregeln liest. Das Repository gehört Artans persönlichem Konto, und ein Fine-grained-Token reicht nur an Repositories des eigenen Kontos oder einer Organisation — Artan erstellt es also; die Alternative ist ein klassisches Token mit `repo`, das an alle Repositories der Person reicht. Von Hand eintragen, nicht über den Chat. Ohne es legt die Konsole keine PRs an. | Christian | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“, Punkt 2 |
| S-10 | **Auf den verwalteten Betrieb umstellen**, wenn die Konsole läuft (S-8): `run --rm worker python -m platform_admin enable-managed …`, im selben Zug in `deploy/cron/urbancrime.crontab` die Datenlauf-Zeile aus- und die Zeile für `srv01-konsole-datenlauf.sh` einkommentieren, `crontab` neu laden. Danach scheitert der alte Datenlauf an `storage.verwaltet` — die beiden Zeilen gehören zusammen getauscht. Den ersten Montag danach im Betriebsblick prüfen: Protokoll, Drift, Sicherungssatz. Dazu der letzte Schritt von E-5: Notebook 34 und 37 auf dem Datenordner des ersten Konsolen-Jobs ausführen, mit Artans Job-Zeiger und Löschregel für Job-Ordner. | Christian | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“; `tests/test_srv01_konsole_takt.py` |

## Im Code

| Nr | Punkt | Wer | seit | wo belegt |
| --- | --- | --- | --- | --- |
| C-1 | **Die Drift-Tabelle im Brett sagt nicht, welche Grösse die Toleranz reisst.** Sie zeigt nur Prozent; Detroits Rate steht dort mit 0,23 % und sieht harmlos aus, weil die Toleranz für Raten absolut gilt (0,1). `drift_ueberschritten` wird ausgegeben, aber kein Panel zeigt es. Am 19.10. bewusst offen gelassen. | Christian | 19.10.2026 | `docker/grafana-brett/urbancrime.json`, Panel „Abweichung je Grösse" |
| C-2 | **Sechs `publish`-Aufrufe ohne `ordnung`.** Gold, `comparison`, `place`, `source_change`, `weather_day`, `tract`. Ohne feste Ordnung hängt die Zeilenfolge an der Einfügereihenfolge, und zwei Bauten in getrennten Prozessen sind nicht byteweise gleich (gemessen an Gold: 14'947'218 gegen 15'001'199 Bytes, gleicher Inhalt). `crime_offense` und `build_kibana` haben sie. | Christian | 3.10.2026 | `deferred-work.md` Nr. 3; `grep -rn "publish(" src/crime` |
| C-3 | **`build_kibana` löscht nie.** Eine umbenannte Kachel bleibt als verwaistes Objekt in Kibana liegen. | Christian | 15.10.2026 | `deferred-work.md` Nr. 26 |
| C-4 | **Der Wächter über fehlende PR-Nummern sieht die höchste nicht.** `test_keine_pull_request_nummer_faellt_durch` prüft bis zur höchsten genannten Nummer; fehlt genau sie, liegt sie ausserhalb des Bereichs. | Christian | 11.10.2026 | `deferred-work.md` Nr. 16 |
| C-5 | **Detroits Abdeckungsquote ist nach Ingestionshäufigkeit gewichtet.** Der Docstring ist seit dem 4.10. richtig („keine Statistik"), die Quote in `test_abdeckung_der_faelle_ist_ausgewiesen` zählt mehrfach geladene Zeilen aber weiter mehrfach. Die Chicagoer Entsprechung bekam sie deshalb nicht. | Christian | 3.10.2026 | `deferred-work.md` Nr. 1; `tests/config/test_micr_nibrs_mapping.py` |
| C-6 | **Eine Karte je Deliktfamilie.** Möglich, kostet aber eine Dimension in `serving/rate_tract`. Kein Fehler, eine Erweiterung. | Christian | 15.10.2026 | `deferred-work.md` Nr. 27 |
| C-7 | **Die Konsole im Betriebsblick.** `admin` liegt noch nicht im Netz `monitoring`, und Prometheus holt `/metrics` nicht ab; Artans Grafana-Brett ist nicht übernommen. Mit der Einrichtung (S-8) nachziehen, wie bei `start` mit Alias `urbancrime-admin`. | Christian | 30.10.2026 | `AENDERUNGEN.md`, „Die Konsole hat einen Platz auf srv01" |
| C-8 | **Der Auslagerungstest wackelt auf CI.** `test_ausgelagert_laeuft_was_sonst_am_speicher_scheitert` fiel am 30.10.2026 auf dem Pull-Request-Lauf von #188 mit „failed to pin block (142,8 von 143 MiB)“ und lief beim Neustart desselben Jobs grün; lokal 15 von 15 grün. Er misst bei 150 MB knapp an der Grenze, mit zwei Threads. Robuster machen (ein Thread oder mehr Abstand), ohne die Zusage aufzugeben: mit Auslagerung läuft, was ohne sie scheitert. | Christian | 30.10.2026 | `tests/storage/test_duckdb.py`; Lauf 41130973257, erster Versuch |
| C-9 | **Das eigene Dashboard auf `srv01` einsetzen und Kibana ablösen.** Alle fünf Bretter stehen (`serving.dashboard`, 1.11.2026). Entschieden am 1.11.2026: Kibana und Elasticsearch gehen auf `srv01` auf einen Schlag. Kibanas Grenze sinkt vorher nicht, neben Kibana bleiben vom Speicherbudget 37 MiB frei. Dazu gehören: ein Compose-Dienst mit gemessener Grenze, die Tunnel-Route, `DASHBOARD_KONSOLE_URL`, die Einstiegsseite und die Dokumente, die Kibana nennen. **Beschrieben seit dem 1.11.2026** (Branch `feature/dashboard-auf-srv01`): Dienst `dashboard` mit 640 MiB, Datenlauf und Konsolen-Worker ohne die beiden Lader, `pruefe_stand --betrieb server`, Einstiegsseite. **Eingesetzt am 1.11.2026**, Spitze 429 MiB, Route steht. Container, Datenträger und Abbilder von Elasticsearch und Kibana sind am 6.11.2026 auf `srv01` gelöscht. Am selben Tag sind beide auch aus `/srv/docker/config/srv01.yaml` genommen (Pflicht-Datenträger `urbancrime_kibana-daten`, zwei erwartete Container); `srv01 doctor` meldet nichts mehr zu Urban Crime. Offen: die Route `urbancrime-kibana` entfernen (Christian). Daneben aufgefallen: Die Einstiegsseite nennt die Admin-Konsole noch „künftig“, obwohl sie seit dem 31.10.2026 auf `srv01` läuft. | Christian | 1.11.2026 | `docs/bilder/dashboard_*.png`; `docker-compose.srv01.yml`, Summe der Grenzen |
| C-11 | **Das Dashboard rechnet die Rate auf der Tatebene.** Die Dokumente nennen seit E-2 (12.11.2026) die Fallebene vorn (Detroit 124,7 je 1'000), das Brett »Raten« zeigt weiter 134,0. `serving.dashboard` zählt `count(*)` statt `count(*) FILTER (counts_case)`; umstellen oder beide zeigen. | Christian | 12.11.2026 | `README.md`, Abschnitt Dashboard |

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
| Nr. 18 | FR-27-Angaben für die vierzehn älteren Kacheln | **in `fr-stand.md`** | ist eine Anforderung (FR-27, teilweise) und wird dort geführt, nicht hier |
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
