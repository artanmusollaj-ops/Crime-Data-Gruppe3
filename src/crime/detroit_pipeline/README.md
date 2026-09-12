# Detroit Pipeline
Aktuelle vollständige Anleitung: ../../../docs/DETROIT_PIPELINE_ANLEITUNG.md.

- detroit_arcgis.py: Quellmetadaten, HTTP-Client mit Retry und ID-Pagination, Filterfenster.
- extract_detroit.py: Full-/Daily-Orchestrierung, Snapshot-Gates, Raw-Ablage, Parquet-Publikation und Manifest.
- bronze_parquet.py: explizites Arrow-Schema, Typprüfung, vollständiges Quellfeature.
- bronze_manifest.py: Validierung veröffentlichter Parquet-Runs.
- load_duckdb.py: transaktionaler und auf Run-Ebene idempotenter Bronze-Import.
- __init__.py: Paketexporte.

**Dieses Paket lädt, es deutet nicht.** Was Detroits Zeilen fachlich bedeuten —
Korn, NIBRS-Zuordnung, Raum und Zeitachse —, entscheidet
`silver_pipeline/build_crime_offense.py` gemeinsam für beide Städte. Eine
zweite, Detroit-eigene Normalisierung gab es bis September 2026
(`transform_detroit.py`); sie ist entfernt, weil zwei Kategorienzuordnungen für
dieselben Daten schlechter sind als eine belegte.

Start immer aus dem übergeordneten Projekt-Root.


## Einstieg unter Windows

Folge Abschnitt 1–2 in `../../../docs/DETROIT_PIPELINE_ANLEITUNG.md`: Python prüfen, `.venv314` erstellen, Abhängigkeiten installieren, Kernel auswählen und Tests ausführen. Danach Full-/Daily-Load starten. Fehlerbehebung steht am Ende der Anleitung.
