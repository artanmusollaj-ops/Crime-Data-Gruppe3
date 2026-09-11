"""Fuehrt alle Tests aus und schreibt Text- sowie JSON-Testprotokolle.

Start aus dem Projekt-Root, beide Wege gehen:

    python -m tests.run_tests
    python tests/run_tests.py

Die Textdatei enthaelt die komplette Konsolenausgabe inklusive Fehler-
Tracebacks. Der JSON-Report stellt die Laufkennzahlen fuer Monitoring, CI oder
eine spaetere Ops-Tabelle maschinenlesbar bereit.

**Warum pytest und nicht unittest.** Dieses Skript sammelte die Tests frueher
mit ``unittest.defaultTestLoader.discover``. Der Loader erkennt nur
``TestCase``-Klassen; die Tests fuer Chicago, Census, Wetter, Silver und die
Referenztabellen sind aber Modulfunktionen mit ``assert``. Dazu kommt, dass
``unittest`` die ``conftest.py`` gar nicht laedt, in der die Pipelines unter
ihren kurzen Namen bekannt gemacht werden. Das Ergebnis war ein
Protokoll, das **SUCCESS nach 39 von 448 Tests** meldete - ein gruener Lauf, der
91 Prozent der Suite nie angefasst hatte. Dieselbe Falle war in
``run_tests_and_log.py`` schon einmal aufgefallen und dort behoben worden; die
Lehre stand also im Repository, nur nicht in dieser Datei.

Gesammelt wird deshalb mit demselben Sammler, den auch ``python -m pytest``
benutzt. Beide koennen dadurch nicht mehr auseinanderlaufen: Was pytest findet,
findet dieser Runner auch.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = PROJECT_ROOT / "tests"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs" / "tests"

# Erlaubt den Aufruf als Skript (python tests/run_tests.py) und nicht nur als
# Modul. Ohne diese Zeile scheitert der Import von ``tests.…`` mit
# ModuleNotFoundError, weil dann das Verzeichnis tests/ im Pfad liegt und nicht
# der Projekt-Root.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402 - erst nach dem Pfad-Bootstrap importierbar

from tests.test_bronze_ingestion import (  # noqa: E402 - dito
    BRONZE_TEST_CATEGORY_COUNTS,
    BRONZE_TEST_TOTAL,
)


class TeeStream:
    """Schreibt dieselbe Testausgabe ins Terminal und in die Logdatei."""

    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, text: str) -> int:
        """Schreibt Text in alle konfigurierten Ausgabestroeme."""

        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        """Leert alle Ausgabepuffer, damit Logs sofort sichtbar sind."""

        for stream in self.streams:
            stream.flush()

    def isatty(self) -> bool:
        """pytest fragt danach, bevor es Farben und Fortschritt waehlt."""

        return False


class Mitschrift:
    """Sammelt die Testergebnisse waehrend des pytest-Laufs.

    pytest meldet je Test bis zu drei Berichte - ``setup``, ``call``,
    ``teardown``. Gezaehlt wird der ``call``-Bericht; scheitert schon ``setup``
    oder ``teardown``, ist das ein *Error* und kein *Failure*, genau wie zuvor
    bei unittest.
    """

    def __init__(self) -> None:
        self.erfolgreich: list[str] = []
        self.fehlschlaege: list[dict[str, str]] = []
        self.fehler: list[dict[str, str]] = []
        self.uebersprungen: list[dict[str, str]] = []
        self.subtest_fehler: list[dict[str, str]] = []
        self.gelaufen: set[str] = set()
        self.gesammelt = 0
        self.sammelfehler: list[dict[str, str]] = []

    # -- pytest-Haken ------------------------------------------------------

    def pytest_collection_finish(self, session) -> None:
        """Haelt fest, wie viele Tests der Sammler gefunden hat."""

        self.gesammelt = len(session.items)

    def pytest_collectreport(self, report) -> None:
        """Ein Modul, das sich nicht einlesen laesst, darf nicht durchrutschen."""

        if report.failed:
            self.sammelfehler.append(
                {"test": str(report.nodeid), "traceback": report.longreprtext}
            )

    def pytest_runtest_logreport(self, report) -> None:
        """Uebernimmt jeden Einzelbericht in die passende Liste."""

        # pytest 9 meldet subTest-Bloecke als eigene Berichte mit gesetztem
        # ``context``. Sie sind keine eigenen Tests und duerfen die Zaehlung
        # nicht aufblaehen - ein gescheiterter Subtest wird aber festgehalten.
        if getattr(report, "context", None) is not None:
            if report.failed:
                self.subtest_fehler.append(
                    {"test": report.nodeid, "traceback": report.longreprtext}
                )
            return

        eintrag = {"test": report.nodeid, "traceback": report.longreprtext}
        if report.when == "call":
            self.gelaufen.add(report.nodeid)
            if report.passed:
                self.erfolgreich.append(report.nodeid)
            elif report.failed:
                self.fehlschlaege.append(eintrag)
            elif report.skipped:
                self.uebersprungen.append(
                    {"test": report.nodeid, "reason": grund(report)}
                )
        elif report.failed:
            self.gelaufen.add(report.nodeid)
            self.fehler.append(eintrag)
        elif report.when == "setup" and report.skipped:
            self.gelaufen.add(report.nodeid)
            self.uebersprungen.append(
                {"test": report.nodeid, "reason": grund(report)}
            )

    # -- Auswertung --------------------------------------------------------

    @property
    def erfolgreich_gelaufen(self) -> bool:
        return not (self.fehlschlaege or self.fehler
                    or self.subtest_fehler or self.sammelfehler)


def grund(report) -> str:
    """Der Grund einer Ueberspringung, so weit pytest ihn mitliefert."""

    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    return str(longrepr) if longrepr else ""


def write_json_atomic(path: Path, payload: dict) -> None:
    """Publiziert den JSON-Testreport atomisch."""

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def main(log_dir: Path = DEFAULT_LOG_DIR) -> int:
    """Fuehrt die Tests aus, protokolliert Ergebnisse und liefert Exit-Code."""

    log_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%S_%fZ")
    log_path = log_dir / f"test_run_{run_id}.log"
    json_path = log_dir / f"test_run_{run_id}.json"

    mitschrift = Mitschrift()
    started_timer = perf_counter()

    with log_path.open("w", encoding="utf-8") as log_handle:
        tee = TeeStream(sys.stdout, log_handle)
        with redirect_stdout(tee), redirect_stderr(tee):
            print("Crime-Data-Gruppe3 Test Run")
            print(f"Run-ID:     {run_id}")
            print(f"Started at: {started_at.isoformat()}")
            print(f"Test path:  {TEST_DIR}")
            print()

            # -vv nennt jeden Test einzeln, auch gegen das -q aus
            # pyproject.toml. -s laesst die Kategoriestatistik der
            # Bronze-Tests bis ins Protokoll durch, statt sie wegzufangen -
            # sie ist der Grund, warum dort ueberhaupt gedruckt wird.
            # -p no:cacheprovider haelt .pytest_cache aus dem Repository.
            pytest.main(
                ["-vv", "-s", "--color=no", "-p", "no:cacheprovider", str(TEST_DIR)],
                plugins=[mitschrift],
            )

            duration_seconds = round(perf_counter() - started_timer, 3)
            finished_at = datetime.now(timezone.utc)
            status = "SUCCESS" if mitschrift.erfolgreich_gelaufen else "FAILED"

            print()
            print("Test Run Summary:")
            print(f"  Status     : {status}")
            print(f"  Gesammelt  : {mitschrift.gesammelt}")
            print(f"  Ausgefuehrt: {len(mitschrift.gelaufen)}")
            print(f"  Erfolgreich: {len(mitschrift.erfolgreich)}")
            print(f"  Fehlgeschl.: {len(mitschrift.fehlschlaege)}")
            print(f"  Errors     : {len(mitschrift.fehler)}")
            print(f"  Uebersprungen: {len(mitschrift.uebersprungen)}")
            if mitschrift.subtest_fehler:
                print(f"  Subtests fehlgeschlagen: {len(mitschrift.subtest_fehler)}")
            if mitschrift.sammelfehler:
                print(f"  SAMMELFEHLER: {len(mitschrift.sammelfehler)}")
            print(f"  Dauer (s)  : {duration_seconds}")

    report = {
        "pipeline": "crime_data_gruppe3",
        "run_id": run_id,
        "status": status,
        "collector": "pytest",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "counts": {
            "collected": mitschrift.gesammelt,
            "tests_run": len(mitschrift.gelaufen),
            "successful": len(mitschrift.erfolgreich),
            "failures": len(mitschrift.fehlschlaege),
            "errors": len(mitschrift.fehler),
            "skipped": len(mitschrift.uebersprungen),
            "subtest_failures": len(mitschrift.subtest_fehler),
            "collection_errors": len(mitschrift.sammelfehler),
        },
        "bronze_fixture_statistics": {
            "offense_category_counts": BRONZE_TEST_CATEGORY_COUNTS,
            "downloaded_count": BRONZE_TEST_TOTAL,
        },
        "tests": {
            "successful": mitschrift.erfolgreich,
            "failures": mitschrift.fehlschlaege,
            "errors": mitschrift.fehler,
            "skipped": mitschrift.uebersprungen,
            "subtest_failures": mitschrift.subtest_fehler,
            "collection_errors": mitschrift.sammelfehler,
        },
        "text_log": str(log_path),
    }
    write_json_atomic(json_path, report)

    print(f"Text-Log:   {log_path}")
    print(f"JSON-Report: {json_path}")
    return 0 if mitschrift.erfolgreich_gelaufen else 1


if __name__ == "__main__":
    raise SystemExit(main())
