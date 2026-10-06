#!/bin/sh
# Der Einstieg des Analyse-Abbilds: die Vorlagen einmal hinlegen, dann
# ausfuehren, was uebergeben wurde.
#
# **Warum ueberhaupt ein Skript.** Der Arbeitsbereich ist ein benannter
# Datentraeger. Haenge ihn ueber ein Verzeichnis, in dem das Abbild schon
# Dateien liegen hat, und sie sind beim ersten Start weg - Docker kopiert sie
# nur in einen **leeren** neuen Datentraeger, und wer einen bestehenden
# einhaengt, sieht dessen Inhalt. Ein COPY in den Arbeitsbereich waere
# deshalb ein Versprechen, das vom Zustand des Datentraegers abhaengt.
#
# **Warum Vorlagen und keine Arbeitskopien.** Die Notebooks im Repository
# sind versionierte Artefakte, und tests/test_notebooks.py sowie
# tests/test_verweise.py halten sie. Wer sie im Browser aendert, haette einen
# Stand, den kein Waechter mehr haelt - und beim naechsten Abbildwechsel
# waere die Aenderung weg. Eine Kopie im Arbeitsbereich ist ehrlicher: Sie
# gehoert dem, der sie aendert.
#
# Gelegt wird genau einmal, naemlich in einen leeren Arbeitsbereich. Liegt
# dort irgendetwas, wird **nichts** angefasst: Nach dem ersten Start ist das
# der Normalfall, und eine bearbeitete Vorlage darf nicht beim naechsten
# Neustart wieder die ausgelieferte Fassung sein.
set -eu

# Die beiden Pfade kommen aus der Umgebung, damit sich dieses Skript ohne
# Docker pruefen laesst (tests/test_jupyter_abbild.py fuehrt es in einem
# Testverzeichnis aus). Die Vorgaben sind die Pfade des Abbilds, und derselbe
# Test haelt sie gegen Dockerfile.jupyter.
VORLAGEN="${JUPYTER_VORLAGEN:-/vorlagen}"
ARBEIT="${JUPYTER_ARBEIT:-/app/arbeit}"

# Jede Meldung nach stderr. stdout gehoert dem Befehl darunter - sonst
# traegt "jupyter lab --version" eine Zeile vor der Fassung.
if [ "$#" -eq 0 ]; then
    echo "jupyter-einstieg: kein Befehl uebergeben" >&2
    exit 2
fi

if [ ! -d "$ARBEIT" ]; then
    # Kein Fehler: Ohne eingehaengten Arbeitsbereich laeuft der Befehl
    # trotzdem - "docker run <abbild> jupyter lab --version" soll antworten
    # und nicht an einem fehlenden Datentraeger scheitern.
    echo "jupyter-einstieg: $ARBEIT gibt es nicht, keine Vorlagen gelegt" >&2
elif [ -n "$(ls -A "$ARBEIT" 2>/dev/null || true)" ]; then
    echo "jupyter-einstieg: $ARBEIT ist nicht leer, nichts angefasst" >&2
elif cp "$VORLAGEN"/*.ipynb "$ARBEIT"/ 2>/dev/null \
        && chmod u+w "$ARBEIT"/*.ipynb 2>/dev/null; then
    # Das chmod gehoert dazu: cp uebernimmt die Rechte der Vorlage, und die
    # ist im Abbild absichtlich nur lesbar. Ohne diese Zeile liegt die Kopie
    # da, liesse sich aber nicht speichern - ein Fehler, der erst beim ersten
    # Speichern auffaellt, und zwar mitten in einer Analyse.
    echo "jupyter-einstieg: Vorlagen aus $VORLAGEN nach $ARBEIT gelegt" >&2
else
    # Auch das bricht nicht ab: Ein Arbeitsbereich, in den dieser Benutzer
    # nicht schreiben darf, ist eine Sache des Verbunds. Der Server soll
    # starten und den Grund zeigen, statt im Neustartkreis zu haengen.
    echo "jupyter-einstieg: konnte keine Vorlage nach $ARBEIT legen" >&2
fi

# exec "$@" und nicht ein fest verdrahteter Serverstart: So verschluckt
# dieser ENTRYPOINT keinen zweiten Befehl - "docker run <abbild> jupyter lab
# --version" und "docker run <abbild> sh -c 'ls /vorlagen'" tun, was sie
# sagen. Dieselbe Entscheidung wie das CMD im Grundabbild.
exec "$@"
