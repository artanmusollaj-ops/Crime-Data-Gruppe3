# Design- und Funktionsprüfung der Engineering-Konsole

Die lokale Flask-Anwendung wurde mit einem getrennten SQLite-Testbestand und Testmanifesten im Browser geprüft. Die Anwendung verwendet ihre vorhandenen Routen. Der Prüfserver bleibt auf Loopback und hatte keinen Worker. Damit prüfen die Browserläufe Anzeige, Navigation und Freigabebedingungen der Oberfläche.

## Visuelle Prüfung

| Zustand | Vorlage | Umsetzung | Vergleich | Viewport |
| --- | --- | --- | --- | --- |
| Aufgabenboard, laufender Antrag | Bild 1 | Browseraufnahme 1 | Vollansicht 1 | 2601 × 1212 |
| Qualitätsprüfung gesperrt, Messdialog offen | Bild 2 | Browseraufnahme 2 | Vollansicht 2 | 2306 × 1227 |
| Betrieb, Gate gesperrt | Bild 3 | Browseraufnahme 3 | Vollansicht 3 | 2336 × 1209 |
| Betrieb, Serving bei 33 % | Bild 4 | Browseraufnahme 4 | Vollansicht 4 | 2581 × 1247 |

Die Vorlagen messen 2601 × 1212, 2306 × 1227, 2336 × 1209 und 2581 × 1247 Pixel. Die Aufnahmen des Browserinhalts messen 2586 × 1205, 2291 × 1219, 2321 × 1201 und 2566 × 1240 Pixel. Die Browser-Viewport-Einstellungen entsprechen der letzten Spalte. Für die Vergleiche wurden Vorlage und Umsetzung jeweils proportional auf 900 Pixel Breite skaliert.

- Ausschnitt Qualitätsdialog
- Ausschnitt Pipeline
- Mobile Ansicht

Im ersten Vergleich rückten lange Spalten den Antragsbereich aus dem sichtbaren Ausschnitt. Die überarbeitete Ansicht begrenzt die Karten je Seite und hält die Spalten scrollbar. Beim Öffnen richtet sie den Fokus auf den Antrag und scrollt nur, wenn dessen Überschrift ausserhalb des sichtbaren Bereichs liegt. Die erneute Desktop-Aufnahme zeigt Board, Details und Zeitverlauf gemeinsam. Die Betriebsauswahl liegt nun platzsparend in der Kartenüberschrift. Der Qualitätsdialog wurde über dem Arbeitsbereich ausgerichtet. Das Board, die horizontale Navigation auf schmalen Bildschirmen und der Detaildialog wurden im Browser überprüft.

Die Produktausführung zeigt die angemeldete Identität, echte Auftrags- und Inbox-Filter sowie die vorhandenen Aktionen und Zeitmarken. Die Simulationssteuerung und Variantenwahl gehören zur Vorlage. Die Auftragsliste und Messwerte variieren mit dem Testbestand.

## Browserprüfung

- Alle vier Spalten, persönliche Filter und Antragsdetails öffnen und schliessen.
- Git-Zustände Gelb, Rot und Grün prüfen. Der bestätigte Merge zeigt den Zielbranch `main`.
- Gold- und Impact-Deltas mit Beispielen für `+1'122 / +56.1 %` und `-1'122 / -28.05 %` prüfen.
- TIGER, ACS5 und NOAA aus verschachtelten Testmanifesten anzeigen. Zeitstempel aus Lauf-ID und Tabellenbau getrennt ausweisen.
- Qualitätsdialog mit 62 von 1'000 ungemappten Zeilen, 6.2 % und Grenze von 5 % prüfen. Dialog per Escape schliessen.
- Geöffnete Impact-Berichte unterscheiden. Freigabe bei blockierter Qualität, bei historischen Berichten und vor dem Öffnen des aktuellen READY-Berichts gesperrt.
- Serving mit einem von drei bestätigten Modulen bei 33 % prüfen. Ein Update auf der offenen Antragsseite liess Scrollposition, Fokus und aktiven Reiter gleich.
- Sieben Quellläufe auf zwei Seiten prüfen und den gespeicherten Laufnachweis öffnen.
- Auftragsdetails im Dialog öffnen. Mobile Ansichten bei eingestellten 390 × 844 prüfen. Alle drei Ansichten ohne horizontalen Seitenüberlauf bei 375 Pixel nutzbarer Breite.
- Keine Browser-Konsolenfehler bei den beschriebenen Abläufen.

## Lokale Laufzeitmessung

Sieben Browser-Neuladungen pro Testbestand. Gemessen wurde die Zeit vom Neuladen bis zum sichtbaren Antragszähler, inklusive Browserautomatisierung und lokaler API-Aufrufe.

| Testbestand | Median | Spanne | Gerenderte Karten beim Start |
| --- | --- | --- | --- |
| 6 Anträge | 238 ms | 191–298 ms | 6 |
| 600 Anträge, davon 594 abgeschlossene Testfälle | 242 ms | 205–336 ms | 20 |

Maximal acht Karten werden je Spalte und Seite erzeugt. Die Messung umfasst lokale Frontend- und API-Reaktionszeiten mit Testdaten. Die ETL-Laufzeit, Cloudflare-Sitzung und Ausführung auf srv01 waren ausserhalb des Prüfaufbaus.

## Python-Prüfungen und Datenumfang

44 gezielte Tests bestanden. Sechs weitere Fälle sind separat eingeordnet.

- Zwei Tests benötigen Windows-Rechte zum Anlegen von Symlinks und scheiterten an WinError 1314.
- Der vorhandene lokale Release-Persistenztest scheiterte im Testaufbau unter Windows an einem Pfadfehler.
- Drei vorhandene Konflikttests gehen für `jobs[2]` von Chicago aus. Die versionierte Betriebskonfiguration hat an dieser Position `detroit_full`.

Die Goldübersicht verwendet die vorhandenen Berichtssummen und die Vorschau der geänderten Partitionen. Eine vollständige Liste unveränderter Deliktkategorien erfordert zusätzliche Berichtsdaten. Die Quellenansicht wertet nachgewiesene Manifestdaten aus.

final result: passed

## Ergänzung: Vorschlagseditor und Importe, 9. November 2026

Diese Abnahme ergänzt die oben dokumentierte Aufgabenboard-Umsetzung. Sie
betrifft die zuletzt bestätigte Kombination: Stadt-/Jobliste aus Variante 1,
ausgewählter Job und separate Änderungskarte aus Variante 2, Sprachwahl DE | EN.

### Visuelle Umsetzung

- Auswahlseite: Stadt-Dropdown und kompakte Tabelle mit Ladeart, Automatik und UTC.
- Detailseite: Jobformular links, „Deine Änderungen“ rechts; die Jobliste ist
  ausgeblendet. Zurück zur Auswahl erhält den gemeinsamen Entwurf.
- Vorherige Werte grau, neue Werte türkis. Automatik als bedienbarer Switch.
- Technische Ladelogik und JSON eingeklappt; die Begründung bleibt sichtbar.
- Mobile Darstellung stapelt Formular und Änderungskarte. Im letzten mobilen
  Screenshot fiel ein links abgeschnittener Sprach-Hilfetext auf: die CSS-
  Ausrichtung wurde anschliessend auf `left:0` korrigiert. Dieser letzte Tooltip-
  Feinschliff wurde nach Wiederaufnahme nicht nochmals mobil aufgenommen.
- Beim letzten Browserdurchlauf wechselte die Ansicht parallel zur Automation.
  Die offene Vorschau wurde deshalb dem Benutzer überlassen; keine weiteren
  Formularaktionen wurden ausgeführt.

Referenzen:
Jobliste,
Detail und Änderungskarte.

Browseraufnahmen der Detailansicht:
Deutsch,
Englisch,
mobil, vor Tooltip-Korrektur.

### Funktionsprüfung

37 Frontend-Vertragstests bestanden. Sie laden die tatsächlichen reinen Funktionen
aus der ausgelieferten HTML-Datei. Geprüft wurden CSV mit Anführungszeichen und
führenden Nullen, Settings-Validierung, benannte Jobs statt Arraypositionen,
unveränderte Fremdfelder bei Basiswechsel, Stadt-/Ladeartauswahl und einzeilige
Begründungen. Acht gezielte Python-Regressionstests sowie elf Tests des
Dokumentwegweisers bestanden ebenfalls: insgesamt 56 gezielte Prüfungen.

Im Browser geprüft: Mappingvorschlag, gemeinsamer Settings-Entwurf, Stadt-/Job-
und Sprachwechsel ohne Verlust der Eingaben, ungültiges JSON und Wiederherstellung,
fester Chicago-Lookback, Review und Einreichung. Die finale Settings-Testrevision
`9d2e1a38343340b0925e6fc7fc3508a6` enthält Detroit Full-Load um 06:30 UTC,
`enabled: false`, alle zuvor konfigurierten Kalenderjahre und genau einen
eingereihten Impact-Auftrag. Alle Zeitpläne sind weiterhin deaktiviert. Die
Prüfung verwendet ausschliesslich `logs/console-variant3-qa-1cxphale` ohne Worker.

Die breitere, ergänzend ausgeführte Integrationsauswahl war **nicht vollständig
grün**: 18 bestanden, neun scheiterten. Acht Fälle hängen an der vorhandenen
synthetischen Runner-Erwartung von neun Befehlen; der aktuelle Rebuild erzeugt
15 Befehle (vier Tract-, vier Place-, Weather-, Offense-, Source-Change-, Gold-
und drei Serving-Stufen). Ein Fall scheiterte an Windows-Socketrechten
(WinError 10013). Diese Befunde wurden nicht durch eine Abschwächung der Tests
verdeckt; Backend und Test-Runner wurden für die Oberfläche nicht geändert.

### Lokale Reaktionszeiten und Architekturgrenze

Fünf Seitenladungen bis zur sichtbaren authentifizierten Oberfläche:
200, 172, 171, 173 und 188 ms; Median 173 ms. Vier Sprachwechsel:
276, 268, 282 und 280 ms. Enthalten sind Browserautomatisierung und lokale
API-Antworten. Das ist keine Lastmessung der Pipeline und keine srv01-Abnahme.

Die einzige geänderte Laufzeitdatei ist
`src/crime/platform_admin/static/index.html`. Zusätzlich wurden Tests und
Dokumentation ergänzt. Flask, Schnittstellen, Datenbankschema, Worker,
Docker-Konfiguration, Scheduler, Queue und serverseitige Sperr-/Freigaberegeln
sind unverändert. Der Browser hat neue Navigation, Validierung und
Entwurfsverwaltung; es handelt sich daher um Frontend-Funktionalität und nicht
nur um CSS. Kein Commit, Push oder Deployment wurde ausgeführt.


## Nachprüfung: Einstieg und einheitliche Konfigurationstabs

Der Akkordeon-Einstieg wurde durch „+ Neuer Vorschlag“ rechts am Board-Titel
ersetzt. 50 px Mindesthöhe, 16 px Schrift, separates dekoratives Plus,
Petrol #087f73 mit weisser Schrift (berechneter Kontrast 4.89:1), Hover und
sichtbarer Tastaturfokus. Der zugängliche Name enthält nur den Aktionstext.

Importe & Zeitpläne nutzt nun dieselbe Überschrift, Schrittanzeige und
Tabnavigation wie Datenumfang und Qualitätsregeln. Der zuvor abweichende
Seitenwechsel entfällt. Browserprüfung: Detroit Full-Load von 06:15 auf
06:30 ändern, zu Qualitätsregeln und zurück wechseln, danach EN/DE wechseln.
Zeitplan, Stadt, Job und Begründung blieben erhalten. Alle vier Tabs blieben
sichtbar; ihre Position im Dokument blieb gleich. Rückkehr zum Board und
Fokus auf „Neuer Vorschlag“ geprüft; keine Browserfehler. Nichts eingereicht.
Die 37 Frontend-Vertragstests blieben grün. Backend unverändert.


## Nachprüfung: lesbares Antrags-Diff, 10. November 2026

Antrag 157e944389d1 aus dem isolierten Worker-Test: Zeitplan 06:15 → 06:30.
Browserprüfung über den anklickbaren Kartentitel und separat „Details öffnen“:
beide öffnen denselben Antrag. Unter Änderung erscheinen Bisher/Neu rot/grün.
Technisches Diff zeigt unverändert den Unified-Diff und lässt sich wieder
schliessen. DE/EN geprüft; keine Browser-Konsolenfehler. Keine Freigabe oder
Publikation vorgenommen.

Neu: `/api/diff` liefert zusätzlich resource/before/after. Dies ist eine lesende
API-Erweiterung; Schreibschnittstellen, Worker, Schema und Freigaberegeln bleiben
unverändert. Zwei neue Tests prüfen exakte Settings-Ausgangs-/Zielwerte, Zugriff
nur mit lokalem Sitzungstoken, führende Nullen im Mapping und unveränderte Heads.
37 Frontend-Vertragstests bestanden. Die zehn gezielten Python-Tests bestanden
mit einem temporären Verzeichnis innerhalb des Projekts; der erste Lauf mit
Windows-Sandbox-Temp scheiterte an Ordnerrechten.

Screenshot:
Lesbarer Änderungsvergleich.
# Abnahme: Veröffentlichung und Betrieb – 10.11.2026

- Git-Aktionen wurden an den geöffneten Antrag gebunden; kein zentraler
  Revisionsselektor mehr. Betriebsansichten: Aufträge, Analyse-Bereitstellung,
  Sicherung. Wartung und Protokolle sind standardmässig eingeklappt.
- 25 neue Frontendprüfungen bestanden: Berechtigungen, zweite Person, fehlende
  Freigabe/Git-Konfiguration, laufende Aufträge, bestätigte/unbestätigte Merges,
  veralteter Analysebestand, genaue API-Antrags-ID und Abbruch ohne Einreichung.
- 37 bestehende Editorprüfungen, zehn gezielte Python-Regressionstests und drei
  Handbuchprüfungen bestanden. `git diff --check` ohne Whitespacefehler.
- Browser auf isolierter lokaler Instanz 8767: Navigation, Git-Ansicht bei nicht
  konfiguriertem Git, fehlende Sicherungs-/Serving-Nachweise, DE/EN, Begründung
  über Tabwechsel und Statusaktualisierung erhalten. Keine Konsolenfehler/-warnungen.
- Mobile Sicherungsansicht bei 390 × 844 getestet: Inhaltsbreite entsprach der
  sichtbaren Breite (375 CSS-Pixel nach Scrollbar), kein horizontaler Überlauf.
- Gegen die Entwürfe geprüft: bestehendes Navy/Teal-Design, getrennte Ansichten,
  antragsbezogenes Git-Protokoll, zurückgenommene Wartungsaktionen. Erfolgswerte
  aus den Entwürfen werden nicht übernommen; der Testbestand hat keine entsprechenden
  Nachweise. CI-Erfolg und automatische Sicherung werden ohne Nachweis nicht behauptet.
- Unveränderte Pollingantworten bauen Betriebs- und Publikationsansichten nicht
  erneut auf. Kein zusätzlicher API-Poll oder neuer Dienst. Kein Lasttest des Servers.
- Screenshots (lokale, ignorierte Nachweise): `logs/analyse-bereitstellung-ui.png`,
  `logs/sicherung-ui.png`, `logs/git-am-antrag-ui.png`.
- Zentrales Handbuch und daraus erzeugtes PDF aktualisiert; geänderte PDF-Seiten
  3 und 7 gerendert und visuell auf Lesbarkeit/Umbruch geprüft.
- Keine Git-, Serving- oder Backup-Aufträge beim Browsercheck ausgelöst; kein
  produktiver End-to-End-Merge, Restore oder srv01-Roll-out durchgeführt.

