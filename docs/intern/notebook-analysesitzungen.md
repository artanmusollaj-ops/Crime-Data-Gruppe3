# Notebooks 34 und 37 auf einem stabilen Pipeline-Bestand (E-5)

Notebook 34 belegt Silver/Gold-Entscheidungen, Notebook 37 die Bewegung der
Bronze-Quellen anhand von Silver/source_change. Ein Ergebnis-Release allein
enthaelt nicht alle benoetigten Dateien. Die Datenwurzel wird deshalb explizit
gewaehlt; Bronze/Silver werden nicht still mit Gold eines anderen Standes vermischt.

## Lokal

Nach einem erfolgreichen Gesamtlauf mit der neuen Codefassung schreibt
`orchestration.run_all` unter der Datenwurzel `.analyse/stand.json`. Darin stehen
Aufbau-ID, Code-Commit (mit Hinweis auf lokale Aenderungen), Zeitpunkt, gebaute
Schichten, gegebenenfalls Release-ID und SHA-256 der lokalen Parquet-Dateien
und Manifeste aus Bronze, Silver und Gold. Ein Lauf nur bis Silver bestaetigt
kein eventuell noch vorhandenes Gold. Ein direkter Neubau oder eine Aenderung
entwertet den alten Nachweis vor dem Schreiben, auch wenn der Vorgang scheitert.
Eine Ausnahme gibt es: `release holen --einsetzen` legt den alten Nachweis nur
beiseite und setzt ihn zurueck, wenn er dasselbe Release nennt und jede erfasste
Datei danach noch dieselbe Pruefsumme hat (`bewahre_nachweis`). So bleibt auf
`srv01` der Nachweis von `run_all` stehen, wenn der Datenlauf das eben
publizierte Release einsetzt. Bei abweichender Release-ID, abweichenden
Pruefsummen, einem Nachweis ohne Release-ID oder einem Fehler bleibt der Bestand
gesperrt.

Auf `srv01` (Modus `s3`) braucht es dazu `STORAGE_ANALYSEBESTAND_LOKAL=true` in
den Diensten `pipeline` und `worker`. Sonst entfernt `run_all` Silver und Gold
nach dem Release, und der Nachweis erfasst nur Bronze.

Die Startzelle liest standardmaessig `data/`. Eine andere Wurzel wird vor dem
Start des Kernels gewaehlt, zum Beispiel in PowerShell:

```powershell
$env:CRIME_ANALYSIS_ROOT = 'C:\Pfad\zum\vollstaendigen\Datenbestand'
```

Die Startzelle erwirbt eine exklusive Prozesssperre, prueft den Herkunftsnachweis,
alle benoetigten Dateien und deren Hashes. Sie zeigt die Herkunft an. Aeltere
Bestaende ohne Nachweis werden nicht automatisch als konsistent angenommen:
zuerst erneut aufbauen. Ein erfolgreicher reiner Gold-Aufruf kann kein schon
vorher vermischtes Silver nachtraeglich bestaetigen; erforderlich ist der
zusammengehoerige Aufbau ueber den Gesamtlauf oder den Konsolen-Kandidatenbau.

Die Abschlusszelle ruft `analyse.beenden()` auf und schliesst die registrierte
DuckDB-Verbindung. Waehrend der Sitzung ist die Ablage des Kernels ausdruecklich
lokal, auch fuer die Gegenprobe mit dem Aufraeumbericht; beim Ende wird die
vorherige Konfiguration wiederhergestellt. Nur eine Sitzung je Kernel starten.
Danach Startzellen neu ausfuehren, bevor weitere Abfragen
gestartet werden. Bei einem Zellfehler bleibt die Sitzung absichtlich gesperrt:
Abschlusszelle manuell ausfuehren oder Kernel herunterfahren. Ein geschlossener
Browser-Tab beendet den Kernel nicht; im Analyse-Abbild beendet der
Notebook-Server untätige Kernel aber nach zwei Stunden
(`docker/jupyter_server_config.py`), damit ein vergessener Tab den
Datenlauf nicht blockiert. Bei automatischer Notebook-Ausfuehrung
wird der Kernel bei Ende/Abbruch beendet; die OS-Sperre endet mit dem Prozess.
Es gibt keinen Zeitablauf, der einem noch lesenden Notebook die Sperre entzieht.

## Verwalteter Betrieb

Die Konsole baut isoliert unter `data/admin/jobs/<Job-ID>/data/`. Genau dort
wird nach technisch erfolgreichem Kandidatenbau der Nachweis geschrieben;
`run_id` ist die Job-ID, die Release-ID benennt den Kandidaten. Das ist **keine
Review-Freigabe** und wird entsprechend angezeigt. Eine spaetere Freigabe wird
nicht aus dem gerade aktiven Release geraten. Fuer einen freigegebenen Stand
muss der Betreiber den zugehoerigen Job anhand der Konsolenentscheidung waehlen.
Der ueberschriebene letzte Worker-Takt in `pipeline_run.json` ist kein Ersatz
fuer den Aufbau-Nachweis. Die Bronze-Laufkennungen sind in den mitgeprueften
Manifesten enthalten, nicht eine erfundene gemeinsame Ingestionskennung.

Notebook 34 benoetigt die Gold-Tabellen aus dem Register sowie Silver/crime_offense,
tract und place (die geografischen Gegenproben dieses Notebooks verwenden
Vintage 2024). Notebook 37 benoetigt Silver/source_change und Bronze-Manifeste.
Fehlt etwas im lokalen Bestand, bricht die Startzelle ab; es gibt keinen
automatischen S3-Download oder Rueckfall auf einen anderen Datenstand.

## Sperren und Container

`storage.analysesitzung` verwendet eine exklusive Betriebssystem-Sperre,
unter Windows einen Byte-Range-Lock, unter Linux flock. Dieselbe Datei darf
niemals geloescht/ersetzt werden. Eine uebrig gebliebene Datei ohne aktive
OS-Sperre blockiert nicht. Worker-Kindprozesse koennen die gehaltene
Schreibsperre mitnutzen; Notebooks erhalten keine Schreibberechtigung.
Die bestehende `admin/worker.lock` samt Token und expliziter Recovery bleibt
erhalten. CLI-Einstiege fuer Pipelines, Serving, Gesamtlauf, Release und
Aufraeumen halten die Datensperre fuer ihre ganze Aktion. Ein blockierter
Worker-Takt laesst die Queue unangetastet und versucht es beim naechsten Takt
erneut. Direkte Dateiaenderungen und externe S3-Schreiber werden damit nicht
verhindert; auf dem Host sind die vorgesehenen Einstiege zu verwenden.

Ohne Konfiguration liegt die Sperre unter `<Datenwurzel>/.analyse/zugriff.lock`.
Fuer Container mit nur lesend eingehaengten Daten brauchen **alle** beteiligten
Prozesse `DATA_LOCK_ROOT` und ein gemeinsam beschreibbares Sperr-Volume.
Die Datenwurzel muss in allen Containern unter demselben absoluten Pfad liegen,
weil der Sperrname daraus abgeleitet wird. Jupyter braucht fuer Konsolenanalysen
zusaetzlich nur lesenden Zugang zum entsprechenden vollstaendigen Job-Datenordner;
die SQLite-Kontrolldatenbank und Tokens sollen dabei nicht freigegeben werden.

Die srv01-Compose-Datei bindet fuer Pipeline, Worker und Jupyter das Volume
`datensperren` unter `/app/datensperren` ein und setzt `DATA_LOCK_ROOT` darauf.
Jupyter erhaelt aus `konsole` ausschliesslich den Unterordner `jobs` als
schreibgeschuetzten Volume-Subpath unter `/app/data/admin/jobs`. Die SQLite-
Kontrolldatenbank und Worker-Tokens im Elternordner werden nicht eingehaengt.
Der Datenpfad ist damit identisch zum Worker; der Notebook-Arbeitsbereich
bleibt separat unter `/app/arbeit` beschreibbar.

Vor dem Start von Jupyter muss `jobs/` im konsole-Volume existieren. Ein
erfolgreicher Konsolen-Aufbau legt ihn samt Job-Daten an; Docker erzeugt fehlende
Volume-Subpaths nicht automatisch. Zusaetzlich muss im `arbeitsdaten`-Volume der
leere Mountpunkt `admin/jobs` existieren. Docker kann ihn unter dem nur lesend
eingehaengten `/app/data` nicht selbst erzeugen. Einmalig vor dem Start von Jupyter
im Verzeichnis des Stapels vorbereiten (nur Verzeichnisse, kein Datenlauf):

```bash
docker compose -f docker-compose.srv01.yml run --rm --no-deps --entrypoint python pipeline -c "from pathlib import Path; Path('/app/data/admin/jobs').mkdir(parents=True, exist_ok=True)"
```

Diese Vorbereitung verwendet den Pipeline-Dienst, der `arbeitsdaten` beschreibbar
und das `konsole`-Volume nicht eingehaengt hat. Der Worker waere dafuer ungeeignet:
Sein ueberlagerndes konsole-Volume wuerde die Verzeichnisse am falschen Ort anlegen.
Es werden keine Job-Daten nach `arbeitsdaten` kopiert.

In der `.env` des Stapels wird danach
`CRIME_ANALYSIS_ROOT=/app/data/admin/jobs/<Job-ID>/data` auf genau diesen Aufbau
gesetzt. Beim Aendern dieses Werts muss Jupyter neu erstellt werden, damit die
Kernel die neue Umgebung erben. Leer bleibt die Vorgabe `/app/data`, die nur
bei passendem lokalen Nachweis als Analysebestand akzeptiert wird.

Die Compose-Konfiguration allein aktualisiert weder die laufenden Container
noch die Notebook-Arbeitskopien. Unter Linux/Docker wurden am 31.10.2026
gegenseitige Leser-/Worker-Sperren, Freigabe und die Job-Volume-Zugriffsrechte
mit isolierten Test-Volumes bestaetigt. Beide Notebooks liefen auf einer
geprueften Kopie des lokalen Aufbaus vollstaendig durch. Der dauerhafte
[Pruefnachweis](e5-pruefnachweis.md) dokumentiert Ergebnisse und Grenzen.
Noch erforderlich ist die Abnahme im echten Verbund auf srv01 mit einem
erfolgreichen Konsolen-Job; der lokale Test schaltet keinen Server um.

Das Hashen liest die lokalen Eingaben einmal vollstaendig beim Bestaetigen und
beim Sitzungsstart. Fuer grosse Bronze-Bestaende kann das merklich dauern und
haelt waehrenddessen die Sperre. Es erzeugt keine zweite Datenkopie.
