# Testnachweis der Konsolenintegration

Stand: 26. Oktober 2026 · Crime_Data_2026-10-26_v1.0

## Automatisierte Prüfungen

Ausgeführt mit Python 3.12 und DuckDB 1.5.5 in einer separaten Testumgebung:

```bash
python -m pytest tests/platform_admin tests/storage tests/orchestration \
  tests/silver_pipeline tests/gold_pipeline tests/serving \
  tests/chicago_pipeline tests/detroit_pipeline \
  tests/census_pipeline tests/weather_pipeline --maxfail=5
```

Ergebnis: **1'526 passed, 56 skipped, 16 deselected, 26 subtests passed**. Laufzeit etwa 127 Sekunden. Die abgewählten Referenzstand-Prüfungen und übersprungenen Umgebungs-/Datenprüfungen sind kein Nachweis produktiver Daten oder externer Dienste. Das ungekürzte Abschlussprotokoll liegt in testnachweise-console/integration.txt.

Zusätzlich: 57 bestandene Prüfungen und eine übersprungene Prüfung für Release-Leser, Notebook/Jupyter-Vertrag und Konsolenübergänge. Nach den letzten Formular-/Validierungsanpassungen: 40 bestandene Konsolenprüfungen. Diese Zahlen überschneiden sich mit dem Hauptlauf und werden nicht zu einer künstlichen Gesamtsumme addiert.

Weitere 86 Strukturprüfungen für Dokumentwegweiser, reproduzierbare Architekturbilder, Dockerfile und Workflow-Shell bestanden; eine Referenzprüfung war abgewählt. Die Architekturabbildungen wurden nach der Ergänzung des elften Pakets aus dem Code neu erzeugt. Der Compose-Vertrag prüft insbesondere, dass Publikation an den Worker delegiert wird und nur dieser den GitHub-Token erhält.

Ruff für den vollständigen Python-Quellbaum und die ergänzten Tests: erfolgreich. JavaScript-Syntaxprüfung der tatsächlichen HTML-Datei mit Node: erfolgreich. Bash-Syntaxprüfung des neuen Cron-Einstiegs: erfolgreich. Die zusätzliche Admin-Lockdatei wurde mit pip --dry-run auflösbar geprüft; das ist kein Containerbuild.

## Inhaltlich geprüfte Grenzen

- Kandidaten verändern den bestehenden aktiven Releasezeiger nicht.
- Rebuild verwendet produktive Pipeline-CLIs und echte kleine Parquet-Daten, einschliesslich Spatial, Quellhistorisierung und GeoJSON.
- Vier-Augen-Regel, archivierte Impact-Bindung, Konflikte, Git-/Merge-Prüfungen, CSRF und Rollenprüfungen.
- S3-Snapshot und Quellansicht verwenden entfernte Manifeste trotz absichtlich veralteter lokaler Kopie; S3-Adapter kontrolliert simuliert.
- Mehrjahres-/Vintage-Entfaltung; Detroit Delta und Daily besitzen unterschiedliche CLI-Parameter.
- Gemeinsame Schreibsperre, direkter Schreibzugriff im verwalteten Bestand, idempotente Batch-Einreihung.
- Bestehende Serving-Lader in richtiger Reihenfolge; Teilfehler bleiben sichtbar, der Datenrelease bleibt unverändert.
- Wiederaufnahme und lokaler Backup-/Restore-Rundlauf mit Kontroll- und Serving-Nachweisen.
- Notebook-Release bleibt nach Zeigerwechsel für die laufende Sitzung festgehalten.

## Dokument- und Oberflächenprüfung

Die Anleitung wurde als PDF gerendert und alle acht Seiten visuell geprüft. Die HTML-Oberfläche wird über vorhandene Struktur-, Routen- und Sicherheitstests sowie JavaScript-Syntaxprüfung abgedeckt. Ein zusätzlicher echter Browserlauf war nicht möglich, weil kein Chromium-Binary vorhanden ist. Es wird daher keine bestandene Browser-End-to-End-Prüfung behauptet.

## Nicht ausgeführt

Kein Docker-/Compose-Start: Docker ist in dieser Umgebung nicht verfügbar. Kein Zugriff auf srv01, keine produktiven API-Importe, kein produktiver S3-CAS-Test, kein Cloudflare-Login, kein GitHub-Merge und kein echter Elasticsearch-/Kibana-Export. Für diese Übergänge sind Konfiguration, Secrets, Netz und Last auf der Zielinstallation separat abzunehmen. Insbesondere sind der Compose-Merge, Speicherbedarf, Wiederanlauf nach Containerabbruch und Wiederherstellung aus der externen Sicherung vor Ort zu prüfen.

Die Tests belegen die beschriebenen lokalen Programmverträge; sie sind keine pauschale Produktionsfreigabe.
