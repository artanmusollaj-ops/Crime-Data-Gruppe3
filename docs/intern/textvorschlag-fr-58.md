# Textvorschlag FR-58: Was aus der LN1-Rückmeldung wurde

Für Artan. Stand 23.11.2026. Ein **Vorschlag**, kein Beleg: Er kommt nicht in
die Zeile P1 von [`pflichtbestandteile.md`](pflichtbestandteile.md). Dort
steht erst die Stelle, die du daraus in den Abgabetext machst. Dann geht
FR-56 auf ●, und `tests/test_pflichtbestandteile.py` verlangt das auch.

**Vorher prüfen.** Die Kritikpunkte unten sind **sinngemäss** wiedergegeben,
aus unseren Notizen zur Rückmeldung vom 3.11.2026 (Note 5.75). Den Wortlaut
bitte gegen die Rückmeldung selbst halten, bevor er in die Abgabe geht.

## Die Punkte einzeln

| # | Kritik (sinngemäss) | Was daraus wurde | Beleg | Grenze |
| --- | --- | --- | --- | --- |
| 1 | Die Notebooks lagen ohne gespeicherte Ausgaben vor. Der Replay in Notebook 36 und die Benchmarks galten deshalb als nicht belegt | Die Notebooks bleiben im Repository ohne Ausgaben, das erzwingt `tests/test_notebooks.py`. Daneben liegen sie **ausgeführt** als HTML, lesbar ohne Python und ohne Daten. `nachweis.json` nennt je Lauf Commit, Umgebung, Laufzeit und Datenstand. Ändert sich der Code eines Notebooks, meldet `tests/test_nachweise.py` den Nachweis als veraltet | [`nachweise/README.md`](../nachweise/README.md), jüngster Lauf `2026-11-14_1a77e8b` mit den Notebooks 31, 33, 34, 35, 36 und 37 | Der jüngste Nachweis ist älter als Gold-Vertrag 10. Er wird zum Abgabestand erneuert ([`abgabestand.md`](abgabestand.md)) |
| 2 | README, LN1-Konzept und PDF waren nicht synchron. In Notebook 36 fielen zwei Nummernkreise für die Hypothesen auf | Die Zahlen der Abgabedokumente hält ein eigener Testlauf gegen die Parquet-Dateien (`pytest -m referenzstand`, 111 Wächter). Ein Wegweiser-Test verlangt, dass jedes Dokument im Wegweiser steht und keines erfunden ist. `forschungsfragen.md` wird aus dem abgegebenen PDF erzeugt. Es gilt ein einziger Nummernkreis, F1 bis F6 mit H1 bis H6, auch in den Notebooks | [`ln2_konzept.md`, 3.5](../ln2_konzept.md#35-woher-diese-nummern-kommen), [`forschungsfragen.md`](../forschungsfragen.md), [`README.md`](../README.md) | Die Wächter halten Zahlen und Verweise, nicht jeden Satz. Der Referenzstand-Lauf ist vom Standardlauf getrennt und muss nach jedem Neubau eigens laufen |
| 3 | Ein dokumentierter Lauf ist nicht dasselbe wie ein eigener vollständiger Neuaufbau. Eine Testzahl belegt Umfang, keinen Erfolg | **Zwei** Neuaufbauten ausserhalb des Entwicklungsrechners. Erstens baut der wöchentliche Datenlauf seit dem 7.11.2026 auf einem Linux-Runner von GitHub alles aus den Quellen neu, montags. Zweitens hat am 15.11.2026 dasselbe Abbild in Google Cloud aus denselben Bronze-Läufen ein zweites Release gebaut: 13 von 13 Tabellen mit gleichem Eingabe-Abdruck, 12 davon byteweise gleich | [`storage-architektur.md`, 17](../storage-architektur.md#17--dieselbe-strecke-in-google-cloud), `.github/workflows/datenlauf.yml`, [`ln2_konzept.md`, 3.3](../ln2_konzept.md#33-hypothesen) (Absatz unter der Tabelle, H5) | Google Cloud baute aus Bronze, nicht aus den Quellen. Die dreizehnte Tabelle, `serving/source_movement`, blieb leer, weil je Quelle nur ein Lauf kopiert war |
| 4 | Eine weitere Stadt braucht quellenspezifischen Code, nicht nur Konfiguration, und so muss man es auch sagen | Die Ingestion ist für eine Stadt auf Socrata oder ArcGIS ein Eintrag in `config/quellen.toml`, ohne neuen Code. Silver, Census, Wetter und Serving brauchen dagegen eigenen Code je Stadt. Die Anleitung nennt jede Stelle einzeln | [`dritte-stadt.md`](dritte-stadt.md), Abschnitt 3 | Eine dritte Stadt ist nicht geplant. Ausprobiert ist der Weg nicht |
| 5 | Ein fertiges Kibana-Serving gehört zu LN2 | **Bewusste Kursänderung.** Kibana hat sich in Entwicklung und Analyse als ungeeignet erwiesen. Auf `srv01` ersetzt seit dem 1.11.2026 ein eigenes Dashboard Elasticsearch und Kibana: Flask und DuckDB, es liest das aktive Release, Spitze 429 MiB statt zusammen 2'816 MiB Grenze. Kibana gibt es weiter, in der Probe in Google Cloud, über `srv01` erreichbar | [`architektur-ist-und-ziel.md`, Teil B](../architektur-ist-und-ziel.md#teil-b--die-ziel-architektur), [`storage-architektur.md`, 16](../storage-architektur.md#16--die-strecke-auf-srv01) und 17 | Die Begründung „ungeeignet in Entwicklung und Analyse“ ist ein Entscheid, keine Messung. Gemessen ist der Speicher |
| 6 | Licht- und Tageslängendaten sind nicht nachgewiesen | Gold trägt seit Vertrag 9 je Stadt und Tag Sonnenaufgang, Sonnenuntergang und Tageslänge, gerechnet nach NOAA. Gegen den NOAA Solar Calculator liegen die Zeiten höchstens 56 Sekunden daneben. Das Dashboard teilt die Fälle im Brett „Zeitverlauf“ nach Tageslicht und Dunkelheit | [`feldkatalog.md`](../feldkatalog.md), Tabelle `dim_city_day` | Keine Hypothese stützt sich darauf, und keine dieser Zahlen steht in einem Abgabedokument |
| 7 | Eine Deliktschwere-Metrik ist nicht nachgewiesen | **Nicht gebaut.** | — | Gehört in die Limitationen (FR-49), mit dem Satz, dass sie in LN1 keine Pflicht war |

## Vorschlag für den Abgabetext

Als eigener Abschnitt, zum Beispiel „Was aus der Rückmeldung zu LN1 wurde“.
Die Fundstellen in Klammern ersetzt du durch die Kapitelnummern der Abgabe.

> Die Rückmeldung zu LN1 nannte sieben Punkte. Fünf sind behoben, einer ist
> eine bewusste Kursänderung, einer bleibt offen.
>
> **Belege statt Behauptungen.** Die Notebooks liegen jetzt zusätzlich
> ausgeführt vor, mit Commit, Umgebung und Datenstand je Lauf (Nachweise).
> Die Zahlen der Abgabedokumente prüfen 111 Tests gegen die Daten. Es gilt
> ein einziger Nummernkreis für Fragen und Hypothesen (3.5).
>
> **Neuaufbau.** Die Strecke wurde zweimal ausserhalb des
> Entwicklungsrechners neu gebaut. Wöchentlich baut ein Linux-Runner alles
> aus den Quellen. In Google Cloud entstanden aus denselben Bronze-Daten
> dieselben Tabellen, zwölf von dreizehn byteweise gleich (H5).
>
> **Skalierbarkeit.** Eine weitere Stadt ist in der Ingestion Konfiguration,
> in Silver, Census, Wetter und Serving aber eigener Code. Die Stellen sind
> einzeln benannt.
>
> **Serving.** Kibana ist nicht die Oberfläche der Abgabe. Es hat sich in
> Entwicklung und Analyse als ungeeignet erwiesen, und Elasticsearch passte
> mit Kibana nicht in den Speicher des Servers. Ein eigenes Dashboard liest
> das aktive Release und braucht 429 MiB. Kibana läuft weiter in Google
> Cloud.
>
> **Licht und Tageslänge** liegen je Stadt und Tag im Gold-Modell und
> trennen im Dashboard Fälle bei Tag und bei Nacht.
>
> **Offen** bleibt eine Deliktschwere-Metrik (Grenzen).

## Danach

- Die Stelle, die daraus im Abgabetext entsteht, kommt in Zeile P1 von
  `pflichtbestandteile.md`, Stand **belegt**. Den Eintrag mache ich, sobald
  die Stelle steht.
- FR-58 in `fr-stand.md` geht dann auf ●, FR-56 ebenso, sofern P2 bis dahin
  nicht mehr „Entwurf“ heisst (FR-57).
