"""Wer in einen verwalteten Datenbestand schreiben darf.

Sobald die Engineering-Konsole einen Bestand uebernommen hat
(``admin/managed.json``), gilt ein Stand erst nach Review. Ein direkter
``run_all``, ein ``release erstellen`` oder ein vergessener Cron-Eintrag
wuerde das umgehen - darum fragt jeder schreibende Einstieg hier, bevor er
anfaengt. Der Konsolen-Worker darf, wenn er sich mit dem Token aus seiner
Sperrdatei ausweist; alle anderen nicht.

Das ist eine Absprache zwischen Prozessen auf einem Host, **keine**
Zugriffsgrenze: Wer Dateizugriff hat, kann den Marker loeschen. Das Modul
liegt in ``storage`` und nicht in ``platform_admin``, damit die Pipelines
es importieren koennen, ohne Flask mitzuladen.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: Unter der Datenwurzel; von ``platform_admin`` geschrieben.
MARKER = "admin/managed.json"
SPERRDATEI = "admin/worker.lock"
#: Die Umgebungsvariable, ueber die der Worker seinen Kindprozessen das
#: Token mitgibt (``platform_admin.jobs``).
TOKEN_VARIABLE = "ADMIN_WRITER_TOKEN"


class VerwaltetFehler(RuntimeError):
    """Ein direkter Schreiber in einem verwalteten Bestand."""


def verwaltet(data_root: Path | str) -> bool:
    """Hat die Konsole diesen Bestand uebernommen?"""
    # lokal mit Absicht: Der Marker ist Zustand des schreibenden Hosts, nicht
    # der Ablage - im s3-Modus liegt er genauso lokal wie die Sperrdatei.
    return (Path(data_root) / MARKER).is_file()


def sperre(data_root: Path | str, *, worker_erlaubt: bool = False) -> None:
    """Bricht ab, wenn ein verwalteter Bestand direkt beschrieben werden soll.

    ``worker_erlaubt=True`` setzen die Einstiege, die der Konsolen-Worker
    selbst aufruft (Pipelines, Serving). ``run_all``, ``release`` und das
    destruktive ``aufraeumen`` setzen es nicht: Sie umgehen den Review auch
    dann, wenn der Worker sie startete.
    """
    wurzel = Path(data_root)
    if not verwaltet(wurzel):
        return
    if worker_erlaubt:
        try:
            # lokal mit Absicht: dieselbe Host-Datei, die der Worker beim
            # Start schreibt.
            token = json.loads((wurzel / SPERRDATEI).read_text(encoding="utf-8"))["token"]
        except (OSError, ValueError, KeyError):
            token = None
        if token and token == os.getenv(TOKEN_VARIABLE):
            return
    raise VerwaltetFehler(
        "Verwalteter Datenbestand: Aktion ueber die Engineering-Konsole oder "
        "'python -m platform_admin.batch' einreihen. Direkte Schreiber und "
        "destruktives Aufraeumen sind gesperrt.")
