# Das Abbild der Strecke: ein Stapellauf, kein Dienst.
#
#   docker build -t urban-crime --build-arg GIT_COMMIT=$(git rev-parse HEAD) .
#   docker run --rm -v "$PWD/data:/app/data" --env-file .env urban-crime
#
# Die Begruendung jeder Entscheidung steht an ihrer Zeile und nicht in einem
# Block hier oben - wer eine Zeile aendern will, liest dort, warum sie so ist.

# Dieselbe Nebenversion wie auf dem Entwicklungsrechner, und dieselbe, fuer die
# requirements.lock eingefroren ist ("Nur 3.13: numpy 2.5 verlangt Python
# 3.12"). pyproject.toml sagt ">=3.11", und CI prueft damit beide Enden; ein
# Abbild hat dagegen genau einen Interpreter, und der soll der des Lockfiles
# sein. Nicht -slim: pyogrio und duckdb bringen zwar manylinux-Raeder mit, aber
# das schlanke Abbild spart rund 700 MB um den Preis, dass ein fehlendes
# Systempaket erst beim Laufen auffaellt - und dieses Abbild laeuft woechentlich
# ohne Zuschauer.
FROM python:3.13

# Ein Zuhause, das jeder Benutzer beschreiben kann. DuckDB legt seine
# Erweiterungen unter $HOME/.duckdb ab und pip seinen Zwischenspeicher
# darunter; ohne beschreibbares $HOME scheitert die erste Verbindung mit einem
# Fehler, der nicht nach der Ursache klingt. 0777 statt eines festen Benutzers,
# weil der Verbund den Benutzer vorgibt (docker run --user ...) und ein Abbild,
# das nur fuer eine uid funktioniert, genau dann klemmt.
ENV HOME=/home/pipeline \
    XDG_CACHE_HOME=/home/pipeline/.cache \
    PYTHONUNBUFFERED=1
RUN mkdir -p "$HOME" && chmod 0777 "$HOME"

# Das Lockfile vor dem Code: Diese Schicht ist die teure, und sie darf nicht
# bei jeder Codeaenderung neu gebaut werden.
COPY requirements.lock ./
COPY requirements-admin.lock Dockerfile Dockerfile.admin ./
# Aus dem Lockfile, nicht aus den Bereichen in pyproject.toml - sonst bekommt
# das Abbild je Bautag andere Versionen, und ein Lauf von heute ist mit einem
# von letzter Woche nicht mehr vergleichbar. Dass jede Zeile darin auf Linux
# installiert, beweist genau dieser Schritt: appnope==1.0.0 steht ohne
# Plattformmarker drin, ist reines Python und tut hier nichts.
RUN python -m pip install --no-cache-dir -r requirements.lock

# Die drei DuckDB-Erweiterungen zur Bauzeit, mit Netz. Zur Laufzeit hat der
# Container keines zu erwarten, und INSTALL scheitert dann hart: silver_pipeline
# laedt spatial, build_crime_offense icu, storage.duckdb httpfs - und ohne
# httpfs gibt es im s3-Modus ueberhaupt kein Bronze zu lesen. Sie landen unter
# $HOME/.duckdb/extensions/<version>/<plattform>; weil Bau und Lauf dieselbe
# duckdb-Version haben, findet das spaetere INSTALL sie dort und laedt nichts
# nach. tests/test_abbild.py haelt die Liste gegen die INSTALL-Aufrufe im Code.
RUN python -c "import duckdb; con = duckdb.connect(); \
    [con.execute(f'INSTALL {name}') for name in ('spatial', 'icu', 'httpfs')]" \
    && chmod -R a+rX "$HOME/.duckdb"

WORKDIR /app

# Die Pipelines rufen sich gegenseitig als Top-Level-Module auf (python -m
# silver_pipeline.build_tract), und die liegen unter src/crime. Editierbar
# installiert heisst: ein Pfadeintrag statt einer Kopie, und derselbe
# Importweg wie auf dem Entwicklungsrechner. --no-deps, weil die Versionen
# oben schon stehen - ohne das zieht pip aus den Bereichen in pyproject.toml
# etwas Neueres nach und haengt das Lockfile aus.
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir -e . --no-deps

# Laufzeit-Assets, keine Dokumentation. config/ traegt die Crosswalks, ohne
# die Silver keine NIBRS-Achse bekommt, und das Register der gepinnten Laeufe;
# AENDERUNGEN.md ist die Soll-Seite des Driftberichts (orchestration.drift
# liest ihren Kopfabschnitt). Beide werden **relativ** aufgeloest, also gegen
# das Arbeitsverzeichnis darunter.
COPY config ./config
COPY docs/intern/AENDERUNGEN.md ./docs/intern/AENDERUNGEN.md

# Der Rest von docs/, die Notebooks und tests/ bleiben draussen. Die Suite
# liest den ganzen docs-Baum und die Notebooks - sie hier mitzuschleppen
# machte das Abbild um ein Vielfaches groesser, und gelaufen wird sie in CI.
# Was dieses Abbild beweisen muss, ist FR-8: derselbe Eingabe-Fingerabdruck
# wie auf dem Host. Dafuer genuegt ein Lauf.

# Die Wurzel wird gesetzt, nicht geraten. manifeste.projektwurzel liest sie
# hier und prueft sie gegen ihre Kennzeichen (pyproject.toml und config/);
# run_all benutzt sie als Arbeitsverzeichnis jedes Unterprozesses. data/ wird
# bewusst **nicht** hineingebaut - es ist ein Volume, und ein Abbild mit
# Daten darin waere kein Abbild des Codes mehr. Auch kein VOLUME-Befehl: Der
# legte bei jedem docker run einen namenlosen Datentraeger an, in dem sich
# Bestand sammelt, nach dem niemand sucht. Das Einhaengen entscheidet der
# Verbund.
ENV PROJECT_ROOT=/app
RUN mkdir -p /app/data && chmod 0777 /app/data

# Zuletzt, damit ein neuer Commit nicht jede Schicht darueber neu baut: Der
# Commit kommt als Argument herein, weil .git/ nicht ins Abbild gehoert
# (FR-2) - und ohne ihn saehe jedes Manifest aus diesem Container so aus, als
# wisse niemand, welcher Code die Zahlen erzeugt hat. manifeste.code_stand
# nimmt ihn, wenn kein Repository da ist, und verlangt eine volle SHA-1.
# Leer gelassen bleibt die Herkunft leer; der Lauf laeuft trotzdem.
ARG GIT_COMMIT=""
ENV GIT_COMMIT=${GIT_COMMIT}

# CMD und nicht ENTRYPOINT: So laesst sich derselbe Container fuer einen
# zweiten Befehl benutzen, ohne --entrypoint zu tippen - etwa
# "docker run urban-crime python -m storage" oder ein Trockenlauf mit anderen
# Jahrgaengen. Ohne Argumente tut er das, was er soll: die ganze Strecke.
CMD ["python", "-m", "orchestration.run_all"]
