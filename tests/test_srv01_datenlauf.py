"""Haelt den auf ``srv01`` installierten Datenlauf und seinen Zeitplan fest.

Das Skript lag zuerst nur auf dem Server. Dadurch konnte weder die
Voll-/Delta-Verteilung noch der Aufruf aus dem Crontab gegen das Repository
geprueft werden. Besonders wichtig ist der zweite Montag: Ein Volllauf am
ersten Montag kollidiert in Monaten, die an einem Montag beginnen, mit dem
Restic-Vollrestore um 05:00.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "docker" / "srv01-datenlauf.sh"
CRONTAB = PROJECT_ROOT / "deploy" / "cron" / "urbancrime.crontab"


@pytest.mark.parametrize(
    ("day_of_month", "expected"),
    (
        (1, "delta"),
        (7, "delta"),
        (8, "full"),
        (14, "full"),
        (15, "delta"),
        (28, "delta"),
        (29, "skip"),
        (31, "skip"),
    ),
)
def test_der_zweite_montag_ist_der_einzige_volllauf(day_of_month, expected):
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; mode_for_day "$2"',
            "--",
            str(SCRIPT),
            str(day_of_month),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == expected


def test_der_crontab_ruft_genau_das_versionierte_skript_auf():
    text = CRONTAB.read_text(encoding="utf-8")
    aktive_zeilen = [
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "SHELL=", "PATH="))
    ]
    assert aktive_zeilen == [
        "30 4 * * 1 /usr/bin/flock --wait 21600 "
        "/srv/docker/apps/urbancrime/logs/pipeline.lock "
        "/srv/docker/apps/urbancrime/docker/srv01-datenlauf.sh auto "
        ">> /srv/docker/apps/urbancrime/logs/scheduled-pipeline.log 2>&1"
    ]


def test_das_skript_prueft_den_veroeffentlichten_stand_am_ende():
    text = SCRIPT.read_text(encoding="utf-8")
    schritte = (
        "orchestration.release holen aktuell --einsetzen",
        "serving.load_elasticsearch",
        "serving.build_kibana",
        "serving.pruefe_stand",
    )
    positionen = [text.index(schritt) for schritt in schritte]
    assert positionen == sorted(positionen)


# --------------------------------------------------------------------------
# Das Skript ruft sieben Module mit Flaggen auf - beide muessen es geben
# --------------------------------------------------------------------------

#: Jeder ``python -m <modul> ... --flagge``-Aufruf im Skript, aus dem Text
#: gelesen statt hier gepflegt: Eine Liste von Hand waere die zweite
#: Wahrheit, die genau dann veraltet, wenn das Skript sich aendert.
AUFRUF = re.compile(
    r"python -m (?P<modul>[\w.]+)(?P<rest>(?:\s+\\\s*\n)?(?:[^\n|;]|\\\s*\n)*)"
)


def aufrufe() -> dict[str, set[str]]:
    """Modul -> die langen Flaggen, mit denen das Skript es aufruft."""
    text = SCRIPT.read_text(encoding="utf-8")
    gefunden: dict[str, set[str]] = {}
    for treffer in AUFRUF.finditer(text):
        modul = treffer.group("modul")
        flaggen = set(re.findall(r"--[a-z][a-z-]+", treffer.group("rest")))
        gefunden.setdefault(modul, set()).update(flaggen)
    return gefunden


@pytest.fixture(scope="module")
def skript_aufrufe() -> dict[str, set[str]]:
    gefunden = aufrufe()
    assert gefunden, f"keine 'python -m'-Aufrufe in {SCRIPT.name} gefunden"
    return gefunden


def hilfe(modul: str) -> str:
    """``--help`` des Moduls. Braucht weder Netz noch Schluessel.

    argparse beendet sich vor jeder Arbeit, deshalb laeuft das auch ohne
    ``CENSUS_API_KEY`` und auf einem Rechner ohne Daten.
    """
    lauf = subprocess.run(
        [sys.executable, "-m", modul, "--help"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    assert lauf.returncode == 0, (
        f"'python -m {modul} --help' endet mit {lauf.returncode} - das Skript "
        f"auf srv01 ruft dieses Modul montags auf:\n{lauf.stderr[-600:]}"
    )
    return lauf.stdout


def test_jedes_aufgerufene_modul_gibt_es(skript_aufrufe):
    """Eine Umbenennung bricht den Montagslauf, nicht den Testlauf.

    Das ist dieselbe Falle, die ``AGENTS.md`` fuer die Notebooks nennt: Was
    nur woechentlich und unbeaufsichtigt laeuft, faellt erst auf, wenn es
    schon nicht mehr geht. Sieben Modulpfade stehen in diesem Skript, und
    ohne diesen Test haelt sie nichts.
    """
    for modul in sorted(skript_aufrufe):
        hilfe(modul)


def test_jede_flagge_im_skript_gibt_es_auch(skript_aufrufe):
    """Eine Flagge, die es nicht gibt, laesst den Lauf sofort scheitern.

    Gepruefte Form am 11.10.2026: ``--full``, ``--mode``, ``--years``,
    ``--auslieferung``, ``--vintage``, ``--ohne-ingestion``, ``--jahre`` und
    ``--einsetzen`` - alle vorhanden. Der Test haelt das, damit eine
    Umbenennung in einem ``arguments()`` nicht erst am Montag auffaellt.
    """
    fehler: list[str] = []
    for modul, flaggen in sorted(skript_aufrufe.items()):
        if not flaggen:
            continue
        text = hilfe(modul)
        vorhanden = set(re.findall(r"--[a-z][a-z-]+", text))
        for flagge in sorted(flaggen - vorhanden):
            fehler.append(f"{modul} kennt {flagge} nicht")
    assert not fehler, "\n".join(fehler)
