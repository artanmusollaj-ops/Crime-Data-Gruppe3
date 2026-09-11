# Zeitzonenvertrag bleibt erhalten
Stand 09.09.2026. Der Parquet-Umbau ändert die fachlichen Fenster nicht.
Full: incident_occurred_at im Detroit-Kalenderjahr. Daily: updated_at in abgeschlossenen Detroit-Kalendertagen, ohne Tatjahresfilter.
Alle Grenzen sind halb-offen: start <= Zeit < end.
ZoneInfo("America/Detroit") konvertiert beide Grenzen separat nach UTC. Ein DST-Tag kann 23 oder 25 Stunden haben.
Das Manifest führt window_contract_version=2, lokale und UTC-Grenzen sowie Dauer.
UTC ist eine globale Zeitreferenz, keine Zürcher Ortszeit.
Parquet bewahrt ArcGIS-Datumswerte als Roh-Epoch-Millisekunden; Silver muss daraus explizit UTC-Instant, Detroit-Ortszeit und lokales Tatdatum ableiten.
ingested_at_utc bezeichnet Beobachtung/Lineage, niemals fachliche Aggregationszuordnung.
Details zu CLI, Referenzdatum, Scheduler und Grenzen stehen in DETROIT_PIPELINE_ANLEITUNG.md.

