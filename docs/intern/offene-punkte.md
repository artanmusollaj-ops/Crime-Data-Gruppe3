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
| E-1 | **Detroits Rate auf `srv01` ist gedriftet.** Dokumentiert sind 133,1 je 1'000 (Tatebene, 2024), der Server misst 133,4 — dreimal die Toleranz von 0,1. Detroit ändert Einträge noch Jahre nach der Tat. Bleibt die Dokumentzahl beim Referenzstand, oder geht sie auf den Serverstand? Die Entscheidung vom 4.10. war, Drift festzuhalten statt nachzuziehen. | beide | 18.10.2026 | `AENDERUNGEN.md`, Eintrag „FR-30 ist im Brett"; Brett *Urban Crime · Betriebsblick*, Reihe „Die Drift" |
| E-2 | **Tatebene oder Fallebene vorn.** E5 hat am 5.10.2026 die Fallebene vorn beschlossen; die Dokumente und der Kopf von `AENDERUNGEN.md` führen weiter die Tatebene (94,5 / 133,1) und die Fallebene in einer dritten Zeile. | Artan | 5.10.2026 | `deferred-work.md` Nr. 19; Kopfabschnitt „Der Stand in Zahlen" |
| E-3 | **Versionierung des Eimers `urban-crime` abschalten?** Sie kostete 3,91 GiB, die jedes Aufräumen für frei hielt. Unser Entwurf braucht sie nicht — nichts überschreibt, `publish_files` lehnt stilles Überschreiben ab. Bleibt sie an, sammeln sich die alten Fassungen wieder an. | Christian | 18.10.2026 | `storage-architektur.md`, „Der Eimer ist versioniert" |
| E-4 | **Was übernimmt der Konsolen-Worker vom Datenlauf?** Nach `platform_admin enable-managed` sperrt `storage.verwaltet` `run_all` und `release` für alles ausser dem Worker — der Cron-Datenlauf scheitert dann. Der Worker lädt, baut, veröffentlicht und lädt Elasticsearch/Kibana, misst aber weder **Drift** noch schreibt er den **Betriebsstand** oder holt den **Sicherungssatz**. Übernimmt er sie (Code in `platform_admin`), oder bleibt der Bestand unverwaltet? **Bis dahin kein `enable-managed`.** | beide | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“; `AENDERUNGEN.md`, „Die Konsole hat einen Platz auf srv01" |
| E-5 | **Wie lesen Notebooks im verwalteten Betrieb?** Artans `serving.release_reader` lenkte sie auf das aktive Release, das aber kein Silver und kein Bronze enthält: Notebook 34 liess 13 von 17 Zellen still leer, 37 brach ab. Nicht übernommen. | Artan | 30.10.2026 | `AENDERUNGEN.md`, „Die Konsole ist im Repository" |

## Auf dem Server

Handgriffe auf `srv01`, die ausserhalb dieses Repositories liegen.

| Nr | Punkt | Wer | seit | wo belegt |
| --- | --- | --- | --- | --- |
| S-1 | **3,91 GiB alte Fassungen entfernen**, danach SeaweedFS kompaktieren. Für die Serversicherung zählt es nicht mehr (`seaweedfs_data` ist aus der Policy), für Platte und SeaweedFS-Kontingent schon. `aufraeumen --loeschen --auch-fern --fassungen`, dann `/vol/vacuum`. | Christian | 18.10.2026 | `AENDERUNGEN.md`, „Ein Löschen, das nie etwas freigegeben hat" |
| S-2 | **Die `srv01`-CLI committen.** Zwei Änderungen liegen ungesichert in `/srv/docker/tools/srv01-cli/`: `health.py` klappt die gruppierte restic-Ausgabe auf (vorher meldete `doctor` bei jedem Lauf „No valid Restic snapshot found"), `util.py` schreibt den Fehlertext ins Protokoll. Sicherungskopien liegen in `/tmp/*.bak`. | Christian | 18.10.2026 | `AENDERUNGEN.md`, „FR-17 ist belegt, nicht beschrieben" |
| S-3 | **Den Monitoring-Stapel committen.** Geändert: `prometheus/prometheus.yaml` (Scrape, zweite `rule_files`-Zeile), `compose.yaml` (zwei Einhängungen), neu `grafana/provisioning/dashboards/urbancrime.yaml`. | Christian | 18.10.2026 | `storage-architektur.md`, „Der Meldeweg" und „Das Brett in Grafana" |
| S-4 | **`christian` in die Gruppe `adm`.** Ohne sie ist das systemd-Journal nur mit `sudo` lesbar — dort stand die Meldung von restic, die 24 Nachtläufe lang niemand sah. `sudo usermod -aG adm christian`, neu anmelden. | Christian | 18.10.2026 | `AENDERUNGEN.md`, „Gesichert wird, was sich nicht nachrechnen lässt" |
| S-5 | **Tunnel-Route für `urbancrime-admin.datenwerft.ch`** auf `http://traefik:80`, wie für Kibana, Jupyter und `start`. Die Access-Anwendung über `urbancrime-*` deckt sie mit; danach mit einem zufälligen Hostnamen prüfen, dass nichts offen ist. | Christian | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“, Punkt 1 |
| S-6 | **Die `.env` des Stapels ergänzen:** `CF_ACCESS_ISSUER` und `CF_ACCESS_AUD` (aus der Access-Anwendung — ohne sie startet `admin` nicht), `ADMIN_ROLE_BINDINGS` (JSON, Access-`sub` → Rollen; zwei Personen, sonst gibt es kein Vier-Augen-Prinzip), `ADMIN_METRICS_TOKEN`, `ADMIN_GITHUB_TOKEN` (Schreibrecht auf das Repository, nur der Worker liest es). | Christian | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“, Punkt 2; `docker-compose.srv01.yml`, Dienste `admin` und `worker` |
| S-7 | **`urbancrime_konsole` in `backup.volumes`.** Darin liegt die SQLite-Datenbank mit den Review-Entscheidungen — das Einzige der Konsole, das sich nicht nachrechnen lässt. | Christian | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“, Punkt 3 |
| S-8 | **Konsole in Betrieb nehmen:** `up -d admin`, einmal `run --rm worker python -m platform_admin init --project-root /app --data-root /app/data --operator christian`, dann die Takt-Zeile in `deploy/cron/urbancrime.crontab` einkommentieren und `crontab` neu laden. Vorher bricht jeder Takt ab. Setzt S-5 bis S-7 voraus. | Christian | 30.10.2026 | `storage-architektur.md` §16, „Was die Engineering-Konsole zusätzlich braucht“, Punkt 4; `tests/test_srv01_konsole_takt.py` |
| S-9 | **Den Webdienst auf `srv01` nachmessen.** Die 160 MiB ruhen auf einer lokalen Messung (92 MiB nach 210 Anfragen, macOS). Nach S-8 `docker stats` lesen, einmal mit einem Impact-Download; liegt es höher, Grenze und `GRENZEN_MIB` nachziehen. | Christian | 30.10.2026 | `docker-compose.srv01.yml`, `mem_limit` von `admin`; `tests/test_srv01_compose.py` |

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
