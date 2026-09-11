"""Tests fuer den Test-Runner selbst.

Der Runner ist zweimal auf ``unittest.defaultTestLoader.discover``
zurueckgefallen. Der Loader erkennt nur ``TestCase``-Klassen, waehrend die Tests
fuer Chicago, Census, Wetter, Silver und die Referenztabellen Modulfunktionen
mit ``assert`` sind. Beide Male meldete der Runner daraufhin **SUCCESS nach 39
von 448 Tests** - ein gruener Lauf, der den groessten Teil der Suite nie
angefasst hatte.

Das Tueckische daran ist nicht der Fehler, sondern seine Form: Ein Runner, der
zu wenig sammelt, sieht aus wie ein Runner, der durchlaeuft. Weder der
Exit-Code noch das Protokoll verraten es; man muss die Zahl lesen und wissen,
wie hoch sie sein sollte.

Deshalb diese Tests. Sie geben dem Runner ein winziges, eigens gebautes
Verzeichnis mit **je einem Test beider Stile** und pruefen, dass er beide
findet. Kein Verlass auf eine Gesamtzahl, die mit jedem neuen Test veraltet -
gemessen wird die Faehigkeit, nicht der Bestand.

Der Runner laeuft dabei als Unterprozess. Das ist kein Umweg, sondern noetig:
pytest innerhalb eines pytest-Laufs erneut zu starten teilt sich Zustand mit
dem aeusseren Lauf.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ein Test je Stil. Der erste ist das, was unittest findet; der zweite das, was
# es uebersieht - und genau daran ist der Runner zweimal gescheitert.
UNITTEST_STIL = '''
import unittest


class ImUnittestStil(unittest.TestCase):
    def test_eins(self):
        self.assertTrue(True)
'''

PYTEST_STIL = '''
def test_zwei():
    assert True
'''

FEHLSCHLAG = '''
def test_faellt_um():
    assert False, "absichtlich"
'''


def runner(ziel: Path, log_dir: Path) -> tuple[int, dict]:
    """Startet den Runner auf ``ziel`` und liefert Exit-Code und JSON-Report."""
    ergebnis = subprocess.run(
        [sys.executable, "-m", "tests.run_tests",
         "--test-dir", str(ziel), "--log-dir", str(log_dir)],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    berichte = sorted(log_dir.glob("test_run_*.json"))
    assert berichte, (
        f"Der Runner hat keinen JSON-Report geschrieben.\n"
        f"stdout:\n{ergebnis.stdout}\nstderr:\n{ergebnis.stderr}"
    )
    return ergebnis.returncode, json.loads(berichte[-1].read_text(encoding="utf-8"))


@pytest.fixture
def beide_stile(tmp_path: Path) -> Path:
    ziel = tmp_path / "probe"
    ziel.mkdir()
    (ziel / "test_unittest_stil.py").write_text(UNITTEST_STIL, encoding="utf-8")
    (ziel / "test_pytest_stil.py").write_text(PYTEST_STIL, encoding="utf-8")
    return ziel


# --------------------------------------------------------------------------
# Der Kern: beide Teststile werden gefunden
# --------------------------------------------------------------------------


def test_findet_beide_teststile(beide_stile, tmp_path):
    """Die Pruefung, die den Rueckfall auf unittest unmoeglich macht.

    Mit ``unittest.discover`` faende der Runner hier genau einen Test statt
    zwei, meldete aber SUCCESS. Dieser Test unterscheidet die beiden Faelle.
    """
    code, report = runner(beide_stile, tmp_path / "logs")

    assert code == 0, "beide Tests bestehen, der Lauf muss erfolgreich sein"
    assert report["counts"]["tests_run"] == 2, (
        "Der Runner hat nicht beide Teststile gefunden. Sammelt er wieder mit "
        "unittest statt pytest? Dann sieht er nur die TestCase-Klasse."
    )
    gefunden = {Path(n.split("::")[0]).name for n in report["tests"]["successful"]}
    assert gefunden == {"test_unittest_stil.py", "test_pytest_stil.py"}


def test_sammler_ist_pytest(beide_stile, tmp_path):
    """Der Report nennt seinen Sammler, damit es im Protokoll nachlesbar ist."""
    _, report = runner(beide_stile, tmp_path / "logs")
    assert report["collector"] == "pytest"


# --------------------------------------------------------------------------
# Ein Fehlschlag muss durchschlagen
# --------------------------------------------------------------------------


def test_fehlschlag_ergibt_exit_code_eins(tmp_path):
    """Ein Runner, der Fehler verschluckt, ist schlimmer als keiner."""
    ziel = tmp_path / "probe"
    ziel.mkdir()
    (ziel / "test_faellt_um.py").write_text(FEHLSCHLAG, encoding="utf-8")

    code, report = runner(ziel, tmp_path / "logs")
    assert code == 1
    assert report["status"] == "FAILED"
    assert report["counts"]["failures"] == 1


def test_fehlschlag_im_pytest_stil_wird_bemerkt(tmp_path):
    """Der Fall, der zweimal durchrutschte: ein Modulfunktions-Test faellt um.

    Mit unittest als Sammler waere diese Datei nie ausgefuehrt worden und der
    Lauf haette SUCCESS gemeldet - mit null ausgefuehrten Tests.
    """
    ziel = tmp_path / "probe"
    ziel.mkdir()
    (ziel / "test_nur_pytest_stil.py").write_text(FEHLSCHLAG, encoding="utf-8")

    code, report = runner(ziel, tmp_path / "logs")
    assert code == 1, (
        "Ein umfallender Test im pytest-Stil muss den Lauf scheitern lassen"
    )
    assert report["counts"]["tests_run"] == 1


def test_nicht_einlesbare_datei_ist_kein_erfolg(tmp_path):
    """Ein Modul mit Syntaxfehler darf nicht stillschweigend uebersprungen werden."""
    ziel = tmp_path / "probe"
    ziel.mkdir()
    (ziel / "test_kaputt.py").write_text("def test_x(:\n    pass\n", encoding="utf-8")

    code, report = runner(ziel, tmp_path / "logs")
    assert code == 1
    assert report["counts"]["collection_errors"] == 1


# --------------------------------------------------------------------------
# Protokolle
# --------------------------------------------------------------------------


def test_schreibt_text_und_json_protokoll(beide_stile, tmp_path):
    log_dir = tmp_path / "logs"
    _, report = runner(beide_stile, log_dir)

    assert len(list(log_dir.glob("test_run_*.log"))) == 1
    assert len(list(log_dir.glob("test_run_*.json"))) == 1
    assert Path(report["text_log"]).exists()
    # Keine halbfertige Datei: der JSON-Report wird atomar veroeffentlicht.
    assert not list(log_dir.glob("*.tmp"))


def test_report_nennt_das_geprueften_verzeichnis(beide_stile, tmp_path):
    """Sonst laesst sich ein Protokoll nicht einordnen."""
    _, report = runner(beide_stile, tmp_path / "logs")
    assert report["test_dir"] == str(beide_stile)


def test_zwei_laeufe_ueberschreiben_einander_nicht(beide_stile, tmp_path):
    log_dir = tmp_path / "logs"
    runner(beide_stile, log_dir)
    runner(beide_stile, log_dir)
    assert len(list(log_dir.glob("test_run_*.json"))) == 2
