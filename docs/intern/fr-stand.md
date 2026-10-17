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
| FR-33 | Die Seite nennt die Grenzen der Aussage | ○ | **offen**, am 17.10.2026 geprüft: „Erfassung", „Grenze" und „Anzeige" kommen im Text nicht vor |

## Welle 5 · Anstoss, Alarm, Rückholbarkeit, Betriebsblick (Christian)

| | Anforderung | Stand | Beleg |
| --- | --- | :-: | --- |
| FR-15 | Wöchentlicher Anstoss auf `srv01` | ● | Crontab montags 04:30 mit `flock`, am 11.10.2026 abgelesen |
| FR-16 | Zeitfenster kollidiert nicht | ○ | **offen** — fällt der Monatserste auf einen Montag, beginnt der Volllauf um 04:30 gegen den Vollrestore um 05:00. Zwei Messungen fehlen, die auf `srv01` jetzt zu nehmen sind |
| FR-17 | Gescheiterter Lauf erzeugt eine Meldung | ○ | **offen**, am 17.10.2026 geprüft: `srv01-datenlauf.sh` meldet nichts, der Crontab hängt an ein Log an. Die Läufe vom 12. und 15.10. sind unbemerkt gescheitert |
| FR-18 | Secrets aus der ignorierten `.env` | ● | `.env` des Stapels, ungetrackt; `.dockerignore` schliesst sie aus |
| FR-19 | — | ▣ | **existiert im PRD nicht.** Die Nummer ist übersprungen; kein Inhalt verloren, aber die Lücke gehört genannt |
| FR-20 | Ein grüner Lauf muss rückholbar sein | ◐ | der Mechanismus steht (`release holen aktuell --einsetzen`), **als Rückholweg nie erprobt** |
| FR-30 | Grafana zeigt den Betriebsblick | ○ | **offen**, am 17.10.2026 geprüft: Grafana und Prometheus laufen auf `srv01`, Prometheus scrapet nur sich selbst, kein Dashboard von uns |

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
| ● erfüllt | 35 |
| ◐ teilweise | 14 |
| ○ offen | 14 |
| ▣ zurückgestellt | 2 |
| **zusammen** | **65** |

Von den sechzehn offenen trägt **Artan** fünf (FR-48, FR-49, FR-51, FR-58 und
anteilig FR-56), **Welle 8** vier, und **vier** sind Christians nächste
Arbeit: FR-16, FR-17, FR-30 und FR-33.

**FR-17 und FR-30 gehören zusammen** und sind der nächste Schritt. Heute hat
genau das gefehlt: Der Lauf auf `srv01` ist am 12. und 15.10.2026 gescheitert,
und gewusst hat es niemand; danach meldete `pruefe_stand` wochenlang eine
fehlende Tabelle, und niemand hat es gelesen. Der Betrieb hat keine Stimme.
