# E-5: lokaler Prüfnachweis vom 31.10.2026

## Ergebnis und Geltungsbereich

Notebook 34 und 37 wurden lokal unter Windows und unter Linux/amd64 in Docker
vollständig ausgeführt. Gegenseitige Leser-/Worker-Sperren, Freigabe nach
Prozessende und nur lesender Zugriff auf Job-Daten wurden mit getrennten
Testcontainern und Test-Volumes bestätigt. Der Test verwendete eine geprüfte
Kopie des lokalen Pipeline-Aufbaus, keinen echten Konsolen-Job auf srv01.
E-5 bleibt bis zu dieser Server-Abnahme offen.

| Prüfung | Durchführung und Ergebnis |
| --- | --- |
| Datenaufbau | Bronze, Silver, Gold, Serving und lokales Release für 2024 erfolgreich gebaut |
| Windows | Beide Notebooks vollständig ausgeführt; Startprüfung und Herkunftsanzeige erfolgreich |
| Linux-Images | Pipeline- und Jupyter-Testimage gebaut; Import der Analyse-/Sperrmodule erfolgreich |
| Leser blockiert Worker | Jupyter-Testcontainer hält die Datensperre; echter `platform_admin.jobs.writer_lock` im zweiten Container wird abgewiesen |
| Worker blockiert Leser | Worker-Testcontainer hält die Sperre; Leser im zweiten Container wird abgewiesen |
| Freigabe | Nach Stoppen des jeweiligen Inhabers kann die Gegenstelle die Sperre erwerben |
| Volumes | Job-Datei lesbar, Schreibversuch vom Dateisystem abgewiesen; Kontrollmarker `control.sqlite` und `worker.lock` im Elternordner nicht sichtbar |
| Testdatenkopie | 52 Dateien aus Bronze, Silver und Gold vor/nach der Kopie anhand des Herkunftsnachweises geprüft; Quelle nur lesend eingebunden |
| Notebook 34 in Docker | 19 von 19 Codezellen ausgeführt, keine Fehlerausgaben |
| Notebook 37 in Docker | 15 von 15 Codezellen ausgeführt, keine Fehlerausgaben |
| Herkunft in Docker | Beide gespeicherten Notebook-Ausgaben enthalten die richtige Run-ID und Release-ID |

Die gegenseitigen Docker-Sperrtests wurden gemeinsam im Terminal durchgeführt;
die gespeicherten Notebook-Ausgaben wurden danach nochmals maschinell geprüft.
Die Sperrtests starten keine Datenpipeline während der Analyse, sondern prüfen
den echten Worker-Lock. Die Sichtbarkeitsprobe verwendet ungefährliche
Kontrollmarker statt echter Tokens oder einer echten Kontrolldatenbank.

## Datenstand und Images

- Aufbaulauf: `9bb071d6d83445caa8c703b85577fbd8`.
- Zugeordnetes Release: `2026-10-31T08-59-38Z`.
- Notebook 37: `silver/source_change` enthält in diesem Stand null Änderungen.
- Plattform: Linux/amd64; Jupyter-Container 768 MiB, DuckDB 512 MB und zwei Threads.
- Job-Datenpfad: `/app/data/admin/jobs/e5-notebooks/data`.
- Gemeinsame Sperren: `DATA_LOCK_ROOT=/app/datensperren`.

Lokale Image-IDs zum Zeitpunkt der Prüfung (keine veröffentlichten GHCR-Referenzen):

```text
urban-crime:e5-test
sha256:6bb9dc414fdcece49114a4f92901181b5538719dce31cfa8037ff9618859bf23

urban-crime-jupyter:e5-test
sha256:2b67dc284f65ac675326f3bc2ae0082461d5457e6f648c52b0f7454cbbe75454
```

Die Codefassung enthielt lokale, noch nicht committed Änderungen. Der im
Herkunftsnachweis genannte Basis-Commit allein beschreibt diese Fassung nicht.
Die lokalen Images sind weder ein publizierter Release noch ein Server-Roll-out.

Die ausführlichen Zellenausgaben und der lokale Bericht wurden unter
`logs/nachweise/e5/docker/` abgelegt. Dieser Ordner ist nicht versioniert und
muss für eine Weitergabe separat archiviert werden. Diese Zusammenfassung
bleibt dagegen unter `docs/` zur Übernahme ins Repository vorgesehen.

## Im Test gefundene und behobene Voraussetzungen

- TIGER-Ingestion unter Windows: gespeichertes ZIP als Byte-Puffer lesen und
  Parquet über einen ausdrücklich geschlossenen Dateihandle schreiben.
- Linux-Einstieg: LF-Zeilenenden; der Jupyter-Build normalisiert zusätzlich CRLF.
- Verschachtelter Mount: `jobs/` im konsole-Volume und der leere Mountpunkt
  `admin/jobs` im arbeitsdaten-Volume müssen vor Jupyter vorhanden sein.
- Notebook-Vorlagen: Das Einstiegsskript überschreibt vorhandene Arbeitskopien
  nicht. Für eine Abnahme muss die neue Image-Vorlage verwendet werden.

Die reproduzierbaren Betriebsschritte stehen in
[`notebook-analysesitzungen.md`](notebook-analysesitzungen.md), die Einordnung in
[`ENGINEERING_KONSOLE.md`](ENGINEERING_KONSOLE.md), Abschnitt 6.

## Noch offen für die Abnahme auf srv01

1. Änderungen über CI übernehmen und Pipeline-/Jupyter-Images veröffentlichen.
2. Neue Images und Compose-Konfiguration einschliesslich Sperr-Volume und
   Mountpunkt-Vorbereitung kontrolliert auf srv01 übernehmen.
3. Einen echten Konsolen-Job erfolgreich aufbauen und dessen Datenherkunft und
   Freigabezuordnung belegen; Jupyter auf genau diesen Bestand setzen.
4. Beide Notebooks mit den neuen Vorlagen vollständig ausführen und Sperre,
   Freigabe sowie Zugriffsrechte im tatsächlichen Verbund erneut prüfen.
5. Notebook 37 mit tatsächlich vorhandenen Änderungen zwischen geeigneten
   Vollschnappschüssen auswerten. Ein fehlerfreier Lauf auf der leeren Tabelle
   belegt deren Behandlung, aber keine fachliche Auswertung von Quelländerungen.
