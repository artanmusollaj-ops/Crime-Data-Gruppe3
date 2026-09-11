# Detroit Pipeline
Aktuelle vollständige Anleitung: ../DETROIT_PIPELINE_ANLEITUNG.md.
Änderungen: ../DETROIT_PARQUET_DUCKDB_AENDERUNGEN.md.

- detroit_arcgis.py: Quellmetadaten, HTTP-Client, Filterfenster und bestehender Parser.
- extract_detroit.py: Full-/Daily-Orchestrierung, Snapshot-Gates, Parquet-Publikation und Manifest.
- bronze_parquet.py: explizites Arrow-Schema, Typprüfung, vollständiges Quellfeature.
- bronze_manifest.py: Validierung veröffentlichter Parquet-Runs.
- load_duckdb.py: transaktionaler und auf Run-Ebene idempotenter Bronze-Import.
- transform_detroit.py: bestehende Einzeldatei-Normalisierung; liest neues Parquet oder Legacy-NDJSON.
- __init__.py: Paketexporte.

Start immer aus dem übergeordneten Projekt-Root. Silver-Current/History und Gold sind noch aufzubauen.


## Einstieg unter Windows

Folge Abschnitt 1–2 in `../DETROIT_PIPELINE_ANLEITUNG.md`: Python prüfen, `.venv314` erstellen, Abhängigkeiten installieren, Kernel auswählen und Tests ausführen. Danach Full-/Daily-Load starten. Fehlerbehebung steht am Ende der Anleitung.
