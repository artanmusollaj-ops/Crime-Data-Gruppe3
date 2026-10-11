"""Haelt den auf ``srv01`` installierten Datenlauf und seinen Zeitplan fest.

Das Skript lag zuerst nur auf dem Server. Dadurch konnte weder die
Voll-/Delta-Verteilung noch der Aufruf aus dem Crontab gegen das Repository
geprueft werden. Besonders wichtig ist der zweite Montag: Ein Volllauf am
ersten Montag kollidiert in Monaten, die an einem Montag beginnen, mit dem
Restic-Vollrestore um 05:00.
"""

from __future__ import annotations

import subprocess
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
