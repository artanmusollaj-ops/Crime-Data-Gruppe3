# Der Stand je Anforderung

Das PRD (`_bmad-output/initiative-ln2/prd-ln2-serving-betrieb/`) sagt, **was**
gebaut werden soll, und sein Abschnitt 8 in welcher Reihenfolge. Was davon
**steht**, sagte bis zum 17.10.2026 nichts — es war über
`docs/intern/AENDERUNGEN.md` und die Planungsdateien verteilt und musste für
jede Anforderung einzeln rekonstruiert werden. Diese Tabelle ist die Antwort
darauf.

**Jede Zeile nennt ihren Beleg.** Das ist die Bedingung, unter der die Tabelle
etwas wert ist: Eine Statusspalte ohne Beleg ist eine Meinung. Wo nichts
geprüft wurde, steht das — `nicht geprüft` ist eine ehrliche Angabe, `erfüllt`
ohne Beleg wäre keine.

● erfüllt · ◐ teilweise · ○ offen · ▣ zurückgestellt, mit Grund

`tests/test_fr_stand.py` hält die Tabelle gegen das PRD: Jede Anforderung des
PRD steht hier, und hier steht keine, die es nicht gibt.

## Welle 1 · Mehrjährigkeit und DuckDB-Grenzen (Christian)

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-34 | `run_all` nimmt einen Jahresbereich | ● | `--jahre 2021-2026`, Wächter in `tests/orchestration/test_run_all.py` |
| FR-35 | Census je Vintage | ● | `silver/tract` und `silver/place` liegen je Vintage, vier ACS-Vintages |
| FR-36 | 2024er Nenner ab 2025 | ● | `gold_pipeline.RATENJAHR`, E12 |
| FR-37 | Unvollständiges Jahr gekennzeichnet | ● | 2026 als Teiljahr, Datenbereich bis 2026-10-04 auf der Startseite |
| FR-38 | NIBRS über sechs Jahrgänge | ● | beide Städte 100 % zugeordnet, `tests/config/test_micr_nibrs_mapping.py` |
| FR-39 | Abdeckung je Jahr ausgewiesen | ● | `docs/feldkatalog.md`, erzeugt |
| FR-40 | Speicherbedarf geschätzt | ● | `docs/intern/platzbedarf.md`, erzeugt, mit Zweitlauf-Wächter |
| FR-61 | `memory_limit` und `threads` gesetzt | ● | `docker-compose.srv01.yml`; am 17.10.2026 auf die gemessene Zahl zurückgenommen, nachdem das Heben die falsche Ursache war |

## Welle 2 · Forschungsfragen und Hypothesen (Artan)

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-53 | Artans Fassung im Repository | ● | `docs/forschungsfragen.md`, erzeugt aus dem abgegebenen LN1-PDF |
| FR-54 | Kein Dokument mit zwei Hypothesenmengen | ◐ | nicht geprüft — E1 ist entschieden, die Durchsicht aller Dokumente fehlt |
| FR-55 | Forschungsfragen im PRD-Sinn definiert | ● | sechs Teilfragen F1–F6, Wortlaut in `docs/forschungsfragen.md` |

## Welle 3 · Abbild, Einbau, Zugang (Christian)

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-1 | `Dockerfile` baut das Abbild | ● | `Dockerfile`, `CMD ["python", "-m", "orchestration.run_all"]` |
| FR-2 | `.dockerignore` schliesst `.env`, `.venv/`, `data/` | ● | drei Einträge geprüft |
| FR-3 | Abbild nicht auf `srv01`, per Digest gepinnt | ● | `.github/workflows/abbilder.yml`, Digest in der `.env` des Stapels; E7 weicht im Buchstaben ab (nicht in CI, sondern Entwicklungsrechner → Registry) |
| FR-4 | Projektwurzel nicht aus `__file__` | ● | `LOCAL_DATA_ROOT` in `storage.config`, Vorgabe `data` |
| FR-5 | `config/` im Abbild | ● | `Dockerfile` |
| FR-6 | `spatial`, `icu`, `httpfs` zur Bauzeit | ● | `Dockerfile`, Erweiterungen unter `$HOME/.duckdb` |
| FR-7 | Beschreibbares `$HOME` | ● | `ENV HOME=/home/pipeline`, `chmod 0777` |
| FR-8 | Gleicher Eingabe-Fingerabdruck im Container | ◐ | **nicht geprüft** — ein Containerlauf gegen einen Hostlauf auf denselben Eingaben fehlt |
| FR-9 | Stapellauf, kein Webdienst | ● | `profiles: [stapel]`, `restart: on-failure:2`, kein `ports:` |
| FR-10 | Webdienste hinter dem Tunnel | ● | Traefik-Label je Webdienst |
| FR-11 | Elasticsearch nicht im `proxy`-Netz | ● | nur das Stapelnetz, `tests/test_srv01_compose.py` |
| FR-12 | Tunnel-Route je Hostname | ● | am 11.10.2026 auf `srv01` abgelesen |
| FR-13 | Speicherlimit je Dienst | ● | `mem_limit` je Dienst, Wächter hält sie gegen die Messung vom 6.10.2026 |
| FR-14 | Dienst-URLs über Umgebungsvariablen | ● | `ELASTICSEARCH_URL`, `KIBANA_URL` |
| FR-21 | Startseite unter dem Muster | ● | `urbancrime-start.datenwerft.ch`, E11 |
| FR-22 | Hostnamen folgen einem Muster | ● | `urbancrime-<dienst>`, Wächter in `tests/test_srv01_compose.py` |
| FR-23 | Eigene Access-Policy für die Prüfenden | ○ | **offen**, bewusst zurückgestellt — die Policy entsteht erst zur Abgabe |
| FR-24 | Keine Identifikatoren in offener Ansicht | ● | am 17.10.2026 geprüft: `docs/einstieg.html` nennt weder `offense_id` noch `case_number` |
| FR-25 | Zufälliger Hostname wird abgewiesen | ● | am 9. und 11.10.2026 gemessen |

## Welle 4 · Analyseszenarien und Startseite (geteilt)

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-26 | Mindestens drei Analyseszenarien | ● | am 17.10.2026 auf `srv01` gezählt: **sieben** Dashboards |
| FR-27 | Jedes Szenario nennt Frage, Nenner, Grenze | ◐ | die ES\|QL- und Kartenkacheln tragen sie und ein Wächter verlangt es; die **vierzehn Kacheln der drei älteren Bretter** nicht — ausdrücklich zurückgestellt (`test_build_kibana.py:307`) |
| FR-28 | Index trägt die Release-Kennung | ● | am 17.10.2026 gemessen: acht Aliase auf `…-20261017t…` |
| FR-29 | Dashboards als Code | ● | `serving.build_kibana`, versioniert |
| FR-31 | Startseite zeigt den einen Befund | ● | `docs/einstieg.html`, auf `srv01` vom Dienst `start` ausgeliefert |
| FR-32 | Jede Zahl auf ihr Release zurückführbar | ● | die Seite nennt Release, Vertrag, Codestand und Eingabe-Fingerabdruck |
| FR-33 | Die Seite nennt die Grenzen der Aussage | ● | der Abschnitt „Was diese Zahlen nicht sagen" steht seit dem 18.10.2026 **unmittelbar hinter dem Städtevergleich** und nennt alle drei: Erfassung ist nicht Kriminalität, Tatort nicht Wohnort, ökologischer Fehlschluss. Vier Wächter in `tests/test_einstieg.py` — über die drei Grenzen, über ihr Beisammenstehen, über ihre Stellung und über die Gleichheit mit `ln2_konzept.md` 11 |

## Welle 5 · Anstoss, Alarm, Rückholbarkeit, Betriebsblick (Christian)

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-15 | Wöchentlicher Anstoss auf `srv01` | ● | Crontab montags 04:30 mit `flock`, am 11.10.2026 abgelesen |
| FR-16 | Zeitfenster kollidiert nicht | ◐ | der **gemeldete** Fall ist gelöst und gewacht: `mode_for_day` fährt den Volllauf nur an den Tagen 8–14, also am **zweiten** Montag — ein Monatserster kann nie der Volllauftag sein (`tests/test_srv01_datenlauf.py`). Offen bleibt die Frage daneben: Ein **Delta**-Lauf beginnt jeden Montag 04:30 und kann über 05:00 hinauslaufen; wie lange er auf `srv01` dauert, ist nicht gemessen |
| FR-17 | Gescheiterter Lauf erzeugt eine Meldung | ◐ | **der Kanal stand schon, und zwar als Telegram** — meine Messung vom 17.10.2026 („kein Alertmanager-Empfänger") war falsch. Am 18.10. lesend nachgesehen: fertiger Empfänger mit Secrets und eigenem Ausgangsnetz, Route **ohne Matcher**, zehn Scrapes, sieben aktive Regeln. `docker/prometheus-regeln/urbancrime.yaml` trägt acht Regeln über die Messwerte von FR-30 — gescheiterter Lauf, gescheiterte Stufe, **ausgefallener** Lauf, fehlendes Protokoll, unerreichbarer Scrape, leere Metrikdatei, veraltete Quelle, halbes Release; `tests/test_alarmregeln.py` hält jeden Namen und jede Marke gegen einen echten Lauf von `serving.betriebsstand` (elf Mutationsproben, alle rot). Offen ist **dreimal eine Zeile** im Monitoring-Stapel und die Gegenprobe über `amtool`, beide in `docs/storage-architektur.md`, „Der Meldeweg" |
| FR-18 | Secrets aus der ignorierten `.env` | ● | `.env` des Stapels, ungetrackt; `.dockerignore` schliesst sie aus |
| FR-19 | — | ▣ | **existiert im PRD nicht.** Die Nummer ist übersprungen; kein Inhalt verloren, aber die Lücke gehört genannt |
| FR-20 | Ein grüner Lauf muss rückholbar sein | ◐ | der Mechanismus steht (`release holen aktuell --einsetzen`), **als Rückholweg nie erprobt** |
| FR-30 | Grafana zeigt den Betriebsblick | ◐ | `serving.betriebsstand` schreibt den Zustand im Textformat von Prometheus neben die Startseite — Status, Alter des Standes, Exitcode je Stufe, Quellenfrische, Release; ein fehlender Lauf meldet `lauf_bekannt 0` statt zu schweigen. **Was fehlt, liegt ausserhalb dieses Repositories:** Prometheus wird aus `/srv/docker/infrastructure/monitoring/` konfiguriert, scrapet nur sich selbst, und liegt im Netz `monitoring` — unser `start` in `proxy`. Eine Scrape-Zeile und eine Netzzeile, dann ist der Blick da |

## Welle 6 · Präsentation, Abgabe, Skalierbarkeit

| | Anforderung | Stand | Beleg | Wer |
| --- | --- | :-: | --- | --- |
| FR-48 | Präsentation deckt die Pflichtaspekte | ○ | nicht begonnen | Artan |
| FR-49 | Limitationen als eigener Abschnitt | ○ | nicht begonnen | Artan |
| FR-50 | Eigenständigkeit, Quellen benannt | ◐ | die Regel gilt im Code (`AGENTS.md`); die Abgabedokumente sind nicht durchgesehen | Artan |
| FR-51 | Abgabemechanik geregelt | ○ | E3 steht auf „vorläufig ja" (Repository bleibt geschlossen) | Artan |
| FR-52 | Datenabgabe passt in die Grenze | ◐ | `platzbedarf.md` gibt die Zahlen; die Grenze selbst ist nicht entschieden | Artan |
| FR-56 | Fundstelle je Pflichtbestandteil P1–P6 | ◐ | **nicht geprüft** — kein Wächter gefunden, der die sechs Fundstellen hält | Artan |
| FR-57 | Finaler Lebenszyklus, sechs Phasen | ◐ | `ln2_konzept.md` Kapitel 5 ordnet sie zu; „final" ist er nicht | Artan |
| FR-58 | LN1-Feedback eingearbeitet | ○ | die Rückmeldung liegt nicht vor | Artan |
| FR-59 | Skalierbarkeit argumentiert | ◐ | `docs/ausblick.md` Abschnitt 3 „Skalieren" | Christian |
| FR-60 | Die drei gemessenen Bremsen benannt | ◐ | in `ausblick.md` enthalten; nicht als eigener, belegter Abschnitt geprüft | Christian |

## Welle 7 · Die Nähte für eine dritte Stadt (Christian)

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-41 | Nähte benannt und dokumentiert | ◐ | `silver_pipeline.STUDIENSTAEDTE` ist der eine Ort; `architektur-ist-und-ziel.md:607` nennt die Blocker. Kein eigener Abschnitt |
| FR-42 | Die vier Asymmetrien als Muster beschrieben | ◐ | im Code an den Stellen begründet (`mode`/`extraction_mode`, `started_at`, `event_year`/`year`, Tat/Anklage); nicht als Muster zusammengeschrieben |
| FR-43 | Jede „genau zwei Städte"-Stelle benannt | ○ | nicht geprüft |

## Welle 8 · Die Vorführung am 12.12.2026 (beide)

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-62 | Vorführung unter fünf Minuten, ohne Eingabe | ○ | nicht begonnen |
| FR-63 | Rückfallweg ohne Internet | ○ | nicht begonnen |
| FR-64 | Rückfallweg einmal geprobt | ○ | nicht begonnen |
| FR-65 | Beide können den eigenen Teil allein vorführen | ○ | nicht begonnen |

## Welle 9 · Google Cloud (Christian) — fällt zuerst

Abschnitt 8 des PRD: *„Fällt zuerst. Beantwortet keine Frage, die das LN2
stellt."*

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-44 | Umgebungswechsel ist Konfiguration | ◐ | `STORAGE_BACKEND` und die S3-Variablen sind Konfiguration; ein Wechsel ist nie probiert |
| FR-45 | S3-Client nimmt Endpunkt, Region, Stil aus der Konfiguration | ● | `storage.config.Config`, `storage.duckdb.secret_sql`, `storage.parquet._ablage` |
| FR-46 | Nichts im Abbild setzt `srv01` voraus | ◐ | nicht geprüft |
| FR-47 | Portierung einmal trocken belegt | ▣ | zurückgestellt mit der Welle |

## Was die Zahlen sagen

| Stand | Anzahl |
| --- | ---: |
| ● erfüllt | 36 |
| ◐ teilweise | 17 |
| ○ offen | 10 |
| ▣ zurückgestellt | 2 |
| **zusammen** | **65** |

Wer die **zehn** offenen trägt — jede genau einmal, und keine, die nicht
offen ist:

| wem | wie viele | welche |
| --- | ---: | --- |
| **Artan** | 4 | FR-48, FR-49, FR-51, FR-58 |
| **Welle 8**, die Vorführung | 4 | FR-62, FR-63, FR-64, FR-65 |
| bewusst zurückgestellt | 1 | FR-23 |
| noch niemandem zugeordnet | 1 | FR-43 |

An FR-56 trägt Artan einen Anteil; es steht teilweise und zählt deshalb hier
nicht mit. `tests/test_fr_stand.py` hält diese Aufteilung gegen die
Statusspalte — die vorige Fassung nannte fünf für Artan und drei für
Christian, zählte dabei ein teilweise erfülltes mit, führte FR-30 noch als
Vorhaben und liess FR-23 und FR-43 ganz aus. Vier Fehler in zwei Sätzen,
weil sie niemand nachgezählt hat.

**Zwei Zeichen widersprechen der Legende**, und beide bewusst stehen
gelassen, weil die Zuordnung eine Entscheidung ist und keine Schreibarbeit:
FR-23 ist nach eigenem Beleg „bewusst zurückgestellt" und trägt dennoch ○,
FR-19 trägt ▣ für etwas, das im PRD gar nicht existiert — zurückgestellt ist
es nicht, es gibt es nicht. Wer eines davon dreht, zieht die Summentabelle
mit.

**FR-17 und FR-30 gehörten zusammen, und jetzt trennt sie eine Entscheidung.**
Der Anlass bleibt wahr: Der Lauf auf `srv01` ist am 12. und 15.10.2026
gescheitert, und gewusst hat es niemand; danach meldete `pruefe_stand`
wochenlang eine fehlende Tabelle, und niemand hat es gelesen. Der Betrieb
hatte keine Stimme.

Seit dem 17.10.2026 hat er eine: `serving.betriebsstand` schreibt den Zustand
hin, wo ein Werkzeug ihn abholen kann, und zwar **auch nach einem Abbruch**.
Seit dem 18.10.2026 steht auch, was aus dem Zustand eine Meldung macht —
acht bewachte Alarmregeln liegen im Repository — und der Kanal, den ich am
17.10. als fehlend gemeldet hatte, **stand bereits**: ein fertiger
Telegram-Empfänger im Alertmanager, Route ohne Matcher. Die Entscheidung,
die ich Christian abverlangt habe, war keine.

**Von unserer Seite ist damit keine Anforderung mehr offen.** Was bei FR-17
und FR-30 fehlt, ist dieselbe Sorte Arbeit und zusammen **dreimal eine
Zeile**: `monitoring` zu den Netzen von `start`, ein Scrape auf `urbancrime-start:80`,
unser Regelverzeichnis beim Dienst `prometheus`. Beschrieben in
`docs/storage-architektur.md`, „Der Meldeweg", samt Gegenprobe über
`amtool`. Erst wenn die einmal gelaufen ist, geht FR-17 auf ●: Ein
Meldeweg, den niemand ausgelöst hat, ist eine Vermutung.

Übrig bleiben damit zehn offene — vier bei Artan, vier in Welle 8, das
bewusst zurückgestellte FR-23 und das unverteilte FR-43.
