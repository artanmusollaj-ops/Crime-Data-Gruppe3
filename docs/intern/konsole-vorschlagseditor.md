# Änderungsvorschläge in der Engineering-Konsole

Stand: 9. November 2026. Ergänzung zum [Konsolenhandbuch](ENGINEERING_KONSOLE.md).

## Einen Vorschlag erfassen

Unter **Änderungen → + Neuer Vorschlag** (oben rechts am Aufgabenboard) zuerst zwischen
**Mapping ändern** und **Konfiguration & Zeitpläne** wählen. Der Entwurf wird
im Browser bearbeitet. Erst **Vorschlag einreichen & Impact berechnen** speichert
eine Revision und reiht den Impact-Auftrag über die bestehende API ein.

Beim Mapping werden Stadt, vorhandener Quellcode und konkreter NIBRS-Zielcode
gewählt. Die Vorschau zeigt bisherige und vorgeschlagene Zuordnung. Führende
Nullen bleiben erhalten. Begründung und optionale fachliche Fundstelle werden
vor dem Einreichen gemeinsam angezeigt und als eine Begründungszeile gespeichert.
Die Korrektur gehört weiterhin in `mapping_overrides.csv`; die erzeugten
Crosswalks und die Kennzeichnung `admin_review` / `ambiguous` bleiben unverändert.

## Importjobs und Zeitpläne

1. **Konfiguration & Zeitpläne → Importe & Zeitpläne** öffnen. Alle vier
   Konfigurationstabs bleiben sichtbar; der Wechsel ersetzt nur den Inhalt darunter.
2. Die Stadt wählen. Die kurze Jobliste zeigt Full-Load und Delta-Load mit
   den **aktiven** Automatik- und UTC-Einstellungen.
3. Einen Job auswählen. Die Liste wird durch das Jobformular links und die
   Änderungskarte rechts ersetzt. Vorherige Werte sind grau, neue Werte türkis.
4. Parameter, Zeitplan und gemeinsame Begründung bearbeiten. Über **Zurück zur
   Auswahl** können weitere Jobs desselben Entwurfs bearbeitet werden.
5. **Änderung prüfen** zeigt sämtliche Änderungen des gemeinsamen Entwurfs.
   Erst die anschliessende Einreichung startet den bestehenden Vorschlagsprozess.

Die Karte zeigt Zeitplan und Automatik des gewählten Jobs sowie weitere geänderte
Felder. Änderungen anderer Jobs oder Bereiche bleiben unter **Weitere Änderungen**
erreichbar. Stadt-, Job-, Bereichs- und Sprachwechsel erhalten den Entwurf.
Ein Neuladen oder Schliessen der Browserseite speichert einen noch nicht
eingereichten Entwurf nicht dauerhaft.

**Weitere Aufträge** enthält Rebuild, Replay, Qualitätsprüfung und gegebenenfalls
den konfigurierten Detroit-Daily-Legacy-Auftrag. Diese gehören nicht zur
Full-/Delta-Auswahl. Mehrere vorhandene Jobs derselben Ladeart bleiben einzeln
auswählbar; fehlende Jobs werden nicht automatisch erzeugt.

## Fachliche Definitionen

| Auswahl | Bestehender Auftrag | Bedeutung |
| --- | --- | --- |
| Chicago Full-Load | `full_chicago` | Vollsnapshot eines Tatjahrs |
| Chicago Delta-Load | `daily_chicago` | `updated_on`, Wasserzeichen und fester Lookback von 14 Tagen; ohne Wasserzeichen Vollsnapshot |
| Detroit Full-Load | `full_detroit` | Vollimport der angegebenen Kalenderjahre |
| Detroit Delta-Load | `delta_detroit` | Änderungen je Kalenderjahr über `updated_at` und Wasserzeichen |

Quellimporte schreiben Raw/Bronze. Ein anschliessender Rebuild erstellt den
Kandidaten. Die Konsole ergänzt eigene UTC-Zeitpläne; der montägliche Gesamtimport
wird weiterhin separat durch den Server-Datenlauf gesteuert. Eine eingetragene
Uhrzeit löst bei ausgeschalteter Automatik keinen geplanten Start aus.

**Datenumfang** verwendet einen inklusiven Beginn und ein exklusives Ende.
Diese Grenzen bestimmen Importjahre und Census-Vintages. Bereits geladene
Bronze-Daten ausserhalb des Zeitraums werden nicht still entfernt, sondern im
Quality Gate beanstandet. Die maximale ungemappte Quote wird je Stadt und lokalem
Tatdatum auf Silver geprüft. Die Oberfläche zeigt Prozent, die API erhält
weiterhin das Verhältnis, beispielsweise `0.04` für 4 %.

**Ladelogik & technische Details** enthält die Definition des ausgewählten Imports
und den gemeinsamen JSON-Entwurf. Ungültiges JSON verhindert die Übernahme und
Einreichung. Bei einer zwischenzeitlich geänderten aktiven Basis wird die
Einreichung gesperrt; **Aktuelle Basis übernehmen** überträgt die bewusst geänderten
Felder auf den neuen Stand. Die anschliessende Prüfung bleibt erforderlich.

## Sprache und Bedienung

Die Sprachwahl **DE | EN** verwendet Deutsch als Standard und merkt sich die
Auswahl lokal im Browser. Mouse-over und Tastaturfokus zeigen Deutsch bzw. English;
Screenreader erhalten ausgeschriebene Namen und den ausgewählten Zustand.
Benutzereingaben, amtliche Katalogbezeichnungen, IDs, Code und gespeicherte
Berichts-/Fehlertexte werden nicht inhaltlich übersetzt. Auf schmalen Bildschirmen
stehen Formular und Änderungskarte untereinander.

## Integration und Abgrenzung

Die Umsetzung liegt in `src/crime/platform_admin/static/index.html`, die Flask
bereits ausliefert und die bestehende Paketkonfiguration einschliesst. Es gibt
keine zusätzliche Frontend-Laufzeit und keinen neuen Dienst. Die Oberfläche
verwendet weiterhin die vorhandenen Mapping-, Settings-, Status- und Review-APIs.

Neu sind Darstellung, Navigation, Übersetzung, Formularvalidierung,
Entwurfsverwaltung und Eventbehandlung im Browser. Schreibende Flask-Routen,
Worker-Konfiguration, Queue, Datenbankschema, Scheduler, Ausführungssperren,
Vier-Augen-Freigabe, Git/CI-Prüfung und Release-Aktivierung wurden für diese
Oberflächenänderung nicht angepasst. Der bestehende lesende Endpunkt `/api/diff` liefert zusätzlich `resource`,
`before` und `after` für den Vergleich mit der ursprünglichen Revision. Sein
bisheriges Feld `diff` bleibt erhalten. Die serverseitigen Prüfungen bleiben
massgebend. Frontend-Sperren ersetzen sie nicht.

Die lokale Vorschau und UI-Abnahme verwenden einen isolierten Testbestand ohne
laufenden Worker. Die Prüfung belegt keinen Roll-out auf `srv01`.

## Prüfungen

- `node tests/platform_admin/test_console_editor.mjs`: 37 Prüfungen für
  CSV-Codes, Validierung, Änderungen, Basiswechsel, Importauswahl und Begründungen.
- `python -m pytest tests/platform_admin/test_mapping_export.py tests/platform_admin/test_console_v3_standalone.py -q`:
  acht gezielte Backend-Regressionstests.
- Browserprüfung: Mapping und Settings einreichen, Full-/Delta- und Stadtwechsel,
  DE/EN mit Entwurferhalt, ungültiges JSON, fester Chicago-Lookback, mobile Ansicht.
- Screenshots, lokale Laufzeitmessungen und Grenzen der erweiterten Tests stehen
  im Projekt-Root unter `design-qa.md`.


## Änderungen eines eingereichten Antrags ansehen

Sowohl der Aufgabentitel als auch **Details öffnen** öffnen denselben Antrag.
Unter **Änderung** erscheinen alte Werte rot mit „Bisher“ und neue Werte grün
mit „Neu“. Die Beschriftung unterscheidet die Zustände auch ohne Farberkennung.
Verglichen wird mit der Ausgangsrevision des Antrags, nicht mit einem inzwischen
geänderten aktiven Stand. Bei Mapping-Overrides wird die bisher wirksame
Zuordnung aus Override oder Crosswalk ermittelt. **Technisches Diff** blendet
zusätzlich den unveränderten Textvergleich ein und aus. Die Ansicht unterstützt
DE/EN und stapelt die Werte auf schmalen Bildschirmen.

Nach dieser API-Erweiterung muss ein bereits laufender lokaler Flask-Prozess
neu gestartet werden; ein Browser-Neuladen allein aktualisiert nur die Oberfläche.

## Veröffentlichung und Betrieb (10. November 2026)

Git-Aktionen gehören zum geöffneten Antrag unter **Veröffentlichung**. Die
frühere zentrale Auswahl einer fachlich freigegebenen Revision unter Betrieb
entfällt. Die Ansicht zeigt Fachfreigabe, Pull Request, bestätigten Merge und
Datenrelease getrennt. Die Git-Ampel und Branch-/Commit-Nachweise bleiben erhalten.
Das **Git-Protokoll** enthält nur Betriebsaufträge dieses Antrags; Ergebnisse
lassen sich einzeln aufklappen. Es zeigt den vorhandenen Auftragsnachweis, kein
vollständiges GitHub-Ereignisprotokoll und keine zusätzlich abgefragte CI-Zusage.

- Nach fachlicher Freigabe kann ein Engineer **Commit / Branch / PR erstellen**.
- Bei offenem PR kann ein Release-Manager als zweite Person **Geprüften PR
  mergen**. Die bestehende serverseitige Prüfung von CI, Basis und Commit bleibt
  massgebend; ein offener PR allein bedeutet nicht, dass CI erfolgreich ist.
- Bei `MERGED_UNVERIFIED` heisst die Aktion **Merge erneut prüfen**.
- Laufende Git-Aufträge, fehlende Rolle oder fehlende Git-Konfiguration schalten
  keine neue Aktion frei. Bestätigte Merges werden nicht erneut angeboten.
- Eine Begründung und die Bestätigung des protokollierten Auftrags sind nötig.
  Freigabe zurückziehen und genehmigte Publikation fortsetzen bleiben erhalten.

**Betrieb** enthält drei Ansichten, die ohne Seitenwechsel umschalten:

1. **Aufträge:** bestehende ETL-Pipeline, Quellimporte und Rebuilds sowie
   Betriebsaufträge und aufklappbarer technischer Dienstestatus.
2. **Analyse-Bereitstellung:** aktiver Release, zuletzt erfolgreich bereitgestellter
   Release und letzte Statusmeldung. Nur `SUCCEEDED` für genau den aktiven Release
   wird als bereit dargestellt. Ein alter erfolgreicher Stand, `PARTIAL`, `RUNNING`
   und fehlende Nachweise erhalten keine grüne Bereitschaftsanzeige.
   **Wartung · Erneut bereitstellen** ist standardmässig geschlossen. Der Operator
   kann den aktiven freigegebenen Release erneut bereitstellen. Der Server bestimmt
   die Release-ID; diese Aktion erstellt keinen neuen Kandidaten. Ohne aktiven
   Release oder bei bereits eingereihtem/laufendem Auftrag ist sie gesperrt.
3. **Sicherung:** letzte erfolgreiche Sicherung mit UTC-Zeit, Speicherart,
   Archivschlüssel und SHA-256 aus dem vorhandenen Nachweis. Die UI behauptet
   keinen automatischen Auslöser, da dieser im Sicherungsnachweis nicht steht.
   Unter **Manuelle Sicherung** kann ein Operator den Konsolenzustand sichern.
   Laufende oder fehlgeschlagene Sicherungsaufträge bleiben neben dem früheren
   Erfolgsnachweis erkennbar. Die Wiederherstellung bleibt das bestehende
   kontrollierte Offline-Verfahren; es gibt keinen neuen Restore-Endpunkt.

Die Sicherung umfasst die Kontrolldatenbank, Konfigurationsrevisionen,
Auftragsverzeichnisse, Impact-Archive, Serving-Nachweise, vorhandene
Verwaltungsmarker und lokale Release-Verzeichnisse. Auftragsverzeichnisse können
Kandidateneingaben enthalten. Sie ist **keine vollständige Sicherung aller
Quelldaten oder des Servers**.

Alle Ansichten unterstützen DE/EN. Begründungen bleiben bei Tabwechsel,
Sprachwechsel und Statusaktualisierung erhalten, aber nicht nach einem kompletten
Neuladen. Beim Wechsel des Antrags wird dessen Git-Begründungsfeld geleert.
Unveränderte Betriebsdaten werden beim Polling nicht neu aufgebaut; geöffnete
Protokolle bleiben bei unverändertem Inhalt offen. Die vorhandene API liefert
höchstens die letzten 100 Betriebsaufträge; die UI ist kein Langzeitarchiv.

### Technische Abgrenzung und Prüfung

Für diese Trennung wurden **nur Frontend, Dokumentation und Frontendtests**
angepasst. Verwendet werden unverändert `/api/operations`, `/api/git-open`,
`/api/git-merge`, `/api/git-withdraw`, `/api/serving` und `/api/backup` sowie die
bisherige Publikationsroute. Worker, Flask-Routen, Queue, Scheduler, Sperren,
Rollenmodell, Git-Schutzregeln und Deployment-Konfiguration wurden dabei nicht
geändert. Die oben dokumentierte frühere Ergänzung von `/api/diff` gehört nicht
zu dieser Trennung. Für diese reine UI-Aktualisierung genügt Browser-Neuladen.

Geprüft: `node tests/platform_admin/test_console_operations.mjs` (25 Prüfungen),
die 37 bisherigen Editor-Prüfungen und zehn Python-Regressionstests für lesbares
Diff, Mappingexport und die eigenständige Konsole. Die neuen Tests prüfen auch
die genaue Antrags-ID beim PR-Auftrag, normalisierte Begründungen, Abbruch ohne
API-Aufruf und die serverseitige Releaseauswahl bei erneuter Bereitstellung.
Die lokale Browserprüfung löst keine Git-, Backup- oder Serving-Aufträge aus.
Ein erfolgreicher produktiver Merge oder Restore wird damit nicht behauptet.
