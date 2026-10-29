# Integrationsentscheidungen und Lieferumfang

Paket: Crime_Data_2026-10-26_v1.0

## Eingangsstände

- Infrastruktur: angehängtes `Crime-Data-Gruppe3-main (5).zip`, Git-Kommentar `e193d97555211965f2d8df00648dc8da89c135c0`.
- Konsole: angehängtes `Crime_Data_2026-10-09_v3.0(1).zip`.

Die Infrastruktur ist die Ausgangsbasis. Aus dem alten Paket wurden das Konsolenmodul und seine Tests übernommen und angepasst. Die alten Pipeline-, Compose- und Serving-Versionen wurden nicht über die neuen Dateien kopiert. Die vollständige Dateidifferenz zur Infrastruktur steht in LIEFERUMFANG_KONSOLE.json.

## Gefundene Konflikte und Umsetzung

| Schnittstelle | Konflikt | Umsetzung |
| --- | --- | --- |
| Release-Erstellung | Alte Konsole verlangt inaktive Kandidaten; neue Release-Funktion aktiviert standardmässig | Rückwärtskompatibles activate=False; Kandidat verändert keinen aktiven Zeiger |
| Bronze/S3 | Konsole erwartete lokale Quellen; Infrastruktur entfernt publizierte Arbeitskopien | S3-Inventar, isolierter Bronze-Download, Manifest-/Dateifingerprints; Import nutzt bestehendes publish_run |
| Mehrjahresverarbeitung | Alte Konsole verwendete unentfaltete Stufen | Vorhandene auswahl-Funktion entfaltet Jahre und Census-Vintages |
| Historisierung | Alter Rebuild kannte source_change nicht | Stufe enthalten, freigegebene Historie in Kandidat übernommen und im Release archiviert |
| Detroit | Daily-Kalenderfenster und echtes Delta wurden gleich bezeichnet | Eigener delta_detroit-Job mit Jahren; Legacy-Daily getrennt benannt |
| Chicago | Alter CLI-Parameter --lookback-days nicht mehr vorhanden | Aktuelle CLI verwendet, abweichende Alt-Konfiguration mit Erklärung abgewiesen |
| Mapping | admin_review im neuen Silver-Vertrag unbekannt | Als fachlich entschieden/ambiguous eingeordnet |
| Gold | offense_group_id wurde stadtübergreifend als eindeutig geprüft | Eindeutigkeitsprüfung auf reporting_city plus offense_group_id korrigiert |
| Serving | Alte Konsole baute vereinfachten Index und verlangte ClickHouse | Vorhandene Elasticsearch-/Kibana-/Startseiten-Lader und Standprüfung wiederverwendet |
| Übergabe an Analyse | Kein dauerhafter Auftrag nach Freigabe | Idempotent nachgeführte Serving-Outbox; PARTIAL sichtbar, expliziter Retry |
| Parallelität | Betriebscron und Konsole konnten gleichzeitig schreiben | Cron reiht Batch ein; eine gemeinsame Worker-Sperre; verwaltete CLI-Schreiber prüfen Besitznachweis |
| Unbeabsichtigtes Veröffentlichen | Altes run_all kann Review umgehen | Verwalteter Datenbestand sperrt direkten Gesamtlauf und Release-CLI-Schreibaktionen |
| Speicher | Konsolen-DuckDB-Verbindungen ignorierten Limits | Gemeinsame DuckDB-Grenzen, Parquet-Views bei Prüfungen und speicherbegrenzter Bronze-Download |
| Notebooks | Feste Pfade können während einer Umschaltung wechseln | Notebook 34/37 halten einen Releasepfad pro Initialisierung fest |
| Backup | Bisheriger Sicherungssatz kennt admin/control.sqlite nicht | Konsolenbackup mit SQLite-Snapshot, Kandidaten, Archiven, Serving-Nachweisen und Management-Marker |
| Monitoring | Alte Betriebsmetriken belegen keine Konsolenjobs | Eigenes Metrics-Target und ergänzendes Grafana-Dashboard; keine erfundene run_all-Erfolgsmeldung |

## Beibehaltene Funktionen

Mapping- und Konfigurationsvorschläge, Vier-Augen-Review, persönliche Arbeitslisten/Zuweisungen, Konflikthinweise, Impact je Versuch, Archivdownload, gekoppelter Git-Nachweis, Wiederaufnahme, Codevorschau, Quelllaufbelege und schwarze Eingabeschrift bleiben enthalten. Die Fortschrittsanzeige nennt zusätzlich den Zustand der Analysebereitstellung.

## Bewusste Grenzen

Ein schreibender Host, kein verteilter Scheduler. Die Sperre koordiniert die vorgesehenen Prozesse; sie ist keine Sicherheitsgrenze gegen Administratoren mit Dateizugriff. Hybrid-Speicher wird für verwaltete Freigaben abgelehnt, weil lokale und entfernte Quellen sonst uneindeutig sein können. Lokaler Modus und S3-Modus sind unterstützt.

Destruktive Retention im verwalteten Bestand ist gesperrt. Eine spätere Erweiterung muss offene Kandidaten, Freigaben, Datenherkunft und Archivfristen in die bestehenden Löschregeln integrieren. Bis dahin nur Trockenlauf und kontrollierte Planung; keine stillschweigende Löschung von Prüfmaterial.

Die Aufnahme in Restic/externes Backup, externe Access-Route, Rollen-Identitäten, Secrets, Registry-Digests und tatsächliche Server-Ressourcen sind installationsabhängig. Sie wurden nicht geraten und nicht auf einem fremden Server verändert.

Die Integration ersetzt weder Elasticsearch noch die vorhandene Zielarchitektur. Ein Imagewechsel bleibt ein kontrollierter Betriebsprozess. Ein Datenrelease ist kein Containerrelease.
