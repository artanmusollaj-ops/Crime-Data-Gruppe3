"""Der Takt der Engineering-Konsole auf srv01.

Der Worker der Konsole fuehrt die Pipelines aus und braucht deren 1'280 MiB.
Er laeuft deshalb nicht dauernd, sondern als Stapellauf im Fuenf-Minuten-Takt
(Entscheidung vom 30.10.2026). Was das traegt, ist eine Sperre: Takt und
Datenlauf duerfen nie gleichzeitig laufen, sonst stehen zwei 1'280-MiB-
Container nebeneinander, und das Budget von FR-13 reicht dafuer nicht.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKRIPT = PROJECT_ROOT / "docker" / "srv01-konsole-takt.sh"
CRONTAB = PROJECT_ROOT / "deploy" / "cron" / "urbancrime.crontab"


def takt_zeile() -> str:
    zeilen = [z for z in CRONTAB.read_text(encoding="utf-8").splitlines()
              if "srv01-konsole-takt.sh" in z]
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


def test_das_skript_ist_gueltiges_bash(benutzbares_bash):
    subprocess.run([benutzbares_bash, "-n", str(SKRIPT)], check=True)


def test_ein_takt_startet_genau_einen_worker_und_sonst_nichts():
    """Kein ``up``: Ein Takt, der Dienste startet, waere ein zweiter
    Datenlauf. Und nur ``worker`` - die Pipeline gehoert dem Cron-Datenlauf."""
    befehle = [z.strip() for z in SKRIPT.read_text(encoding="utf-8").splitlines()
               if z.strip() and not z.lstrip().startswith("#")]
    text = " ".join(befehle)
    assert re.search(r"\brun --rm worker\s*$", text), text
    assert not re.search(r"\b(up|start|restart)\b", text.split("compose", 1)[1])
    assert text.count("docker compose") == 1


def test_takt_und_datenlauf_teilen_eine_sperre():
    datenlauf = [z for z in CRONTAB.read_text(encoding="utf-8").splitlines()
                 if "srv01-datenlauf.sh" in z and not z.lstrip().startswith("#")]
    sperre = re.search(r"/usr/bin/flock .*?(/\S+\.lock)", datenlauf[0]).group(1)
    assert sperre in takt_zeile(), "ohne gemeinsame Sperre laufen beide nebeneinander"


def test_der_takt_wartet_nicht():
    """Ein wartender Takt staute sich hinter einem stundenlangen Datenlauf zu
    einer Reihe, die danach nacheinander abliefe. Belegt heisst: ausfallen,
    und das ohne Fehlercode - sonst meldete cron alle fuenf Minuten einen."""
    zeile = takt_zeile()
    assert "--nonblock" in zeile and "--conflict-exit-code 0" in zeile


def test_der_takt_ist_bis_zur_einrichtung_auskommentiert():
    """Vor ``platform_admin init`` bricht jeder Takt ab. Eingeschaltet wird
    er auf srv01 von Hand, nicht durch das naechste ``crontab``."""
    assert takt_zeile().lstrip().startswith("#")


# --------------------------------------------------------------------------
# Montags: der geplante Quellenlauf, ab enable-managed (Entscheidung 30.10.2026)
# --------------------------------------------------------------------------

EINREIHEN = PROJECT_ROOT / "docker" / "srv01-konsole-datenlauf.sh"
DATENLAUF = PROJECT_ROOT / "docker" / "srv01-datenlauf.sh"


def test_das_einreihen_ist_gueltiges_bash(benutzbares_bash):
    subprocess.run([benutzbares_bash, "-n", str(EINREIHEN)], check=True)


def test_der_rhythmus_kommt_aus_derselben_funktion():
    """Erster Montag Delta, zweiter Voll, dritter und vierter Delta, fuenfter
    frei - und der Volllauf nie am Monatsersten wegen des Restic-Restores.
    Eine zweite Fassung dieser Regel liefe frueher oder spaeter auseinander;
    das Skript liest die eine aus dem Datenlauf."""
    text = EINREIHEN.read_text(encoding="utf-8")
    assert re.search(r'^\s*source "\$\(dirname "\$\{BASH_SOURCE\[0\]\}"\)/srv01-datenlauf\.sh"',
                     text, re.M), "liest den Rhythmus nicht aus dem Datenlauf"
    assert re.search(r"mode_for_day \"\$\(date", text), "der Rhythmus wird nicht benutzt"
    assert not re.search(r"^\s*(function\s+)?mode_for_day\s*\(\)", text, re.M), (
        "eigene Fassung des Rhythmus")


def test_eingereiht_wird_ein_batch_und_sonst_nichts():
    text = EINREIHEN.read_text(encoding="utf-8")
    aufrufe = re.findall(r"compose run --rm (\w+) python -m ([\w.]+)", text)
    assert aufrufe == [("worker", "platform_admin.batch")], aufrufe
    for flagge in ('--mode "${mode}"', "--slot", "--operator scheduler"):
        assert flagge in text, flagge


def test_der_montag_wartet_auf_den_takt():
    """Anders als der Takt wartet das Einreihen: Es darf nicht ausfallen,
    nur weil gerade ein Auftrag laeuft - sonst fehlte der Wochenlauf."""
    zeilen = [z for z in CRONTAB.read_text(encoding="utf-8").splitlines()
              if "srv01-konsole-datenlauf.sh" in z]
    assert len(zeilen) == 1 and zeilen[0].lstrip().startswith("#")
    assert "--wait" in zeilen[0] and "logs/pipeline.lock" in zeilen[0]
    assert zeilen[0].lstrip("# ").startswith("30 4 * * 1 "), "derselbe Termin wie der Datenlauf"
