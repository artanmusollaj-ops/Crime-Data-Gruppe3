"""Fuehrt die gesamte Testsuite aus und schreibt Text- sowie JSON-Testprotokolle.

Start aus dem Projekt-Root:

    python -m tests.run_tests

Die Textdatei enthaelt die komplette Konsolenausgabe inklusive Kategorie-
statistik und Fehler-Tracebacks. Der JSON-Report stellt die Laufkennzahlen fuer
Monitoring, CI oder eine spaetere Ops-Tabelle maschinenlesbar bereit.

Ausgefuehrt wird ueber pytest und nicht ueber ``unittest discover``. Die Census-
und Chicago-Tests sind im pytest-Stil geschrieben, also als Modulfunktionen mit
``assert`` statt als ``unittest.TestCase``, und ausserdem laedt ``unittest`` die
``conftest.py`` nicht. Ein Runner auf unittest-Basis fand deshalb nur die
Detroit-Tests und meldete Erfolg, obwohl der weitaus groessere Teil der Suite
nie ausgefuehrt wurde.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter

import pytest

from tests.test_bronze_ingestion import (
    BRONZE_TEST_CATEGORY_COUNTS,
    BRONZE_TEST_TOTAL,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = PROJECT_ROOT / "tests"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs" / "tests"


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
        """Meldet keinen Terminalmodus, damit pytest nicht farbig schreibt."""

        return False


class ResultCollector:
    """Sammelt die pytest-Ergebnisse fuer den JSON-Report."""

    def __init__(self) -> None:
        self.successes: list[str] = []
        self.failures: list[dict[str, str]] = []
        self.errors: list[dict[str, str]] = []
        self.skipped: list[dict[str, str]] = []

    @property
    def tests_run(self) -> int:
        """Zahl der Tests, die ein Ergebnis geliefert haben."""

        return (
            len(self.successes)
            + len(self.failures)
            + len(self.errors)
            + len(self.skipped)
        )

    def pytest_runtest_logreport(self, report) -> None:
        """Ordnet jeden Testbericht genau einer Ergebniskategorie zu."""

        if report.when == "call":
            if report.passed:
                self.successes.append(report.nodeid)
            elif report.failed:
                self.failures.append(self._record(report))
            elif report.skipped:
                self.skipped.append(self._skip_record(report))
        elif report.failed:
            # Ein Fehler in Fixture-Setup oder Teardown ist kein fachlich
            # fehlgeschlagener Test, sondern ein Error.
            self.errors.append(self._record(report))
        elif report.when == "setup" and report.skipped:
            self.skipped.append(self._skip_record(report))

    @staticmethod
    def _record(report) -> dict[str, str]:
        """Uebertraegt Fehlerbericht und Traceback in JSON-taugliche Felder."""

        return {"test": report.nodeid, "traceback": str(report.longrepr)}

    @staticmethod
    def _skip_record(report) -> dict[str, str]:
        """Liest den Grund aus dem Skip-Bericht heraus."""

        longrepr = report.longrepr
        if isinstance(longrepr, tuple) and len(longrepr) == 3:
            return {"test": report.nodeid, "reason": str(longrepr[2])}
        return {"test": report.nodeid, "reason": str(longrepr)}


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

    collector = ResultCollector()
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
            # Bronze-Tests bis ins Protokoll durch, statt sie wegzufangen.
            exit_code = int(
                pytest.main(
                    [
                        "-vv",
                        "-s",
                        "--color=no",
                        "-p",
                        "no:cacheprovider",
                        str(TEST_DIR),
                    ],
                    plugins=[collector],
                )
            )

            duration_seconds = round(perf_counter() - started_timer, 3)
            finished_at = datetime.now(timezone.utc)
            status = "SUCCESS" if exit_code == 0 else "FAILED"

            print()
            print("Test Run Summary:")
            print(f"  Status       : {status}")
            print(f"  Ausgefuehrt  : {collector.tests_run}")
            print(f"  Erfolgreich  : {len(collector.successes)}")
            print(f"  Fehlgeschl.  : {len(collector.failures)}")
            print(f"  Errors       : {len(collector.errors)}")
            print(f"  Uebersprungen: {len(collector.skipped)}")
            print(f"  Dauer (s)    : {duration_seconds}")
            print(f"  pytest-Code  : {exit_code}")

    report = {
        "project": "crime-data-gruppe3",
        "runner": "pytest",
        "run_id": run_id,
        "status": status,
        "pytest_exit_code": exit_code,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "counts": {
            "tests_run": collector.tests_run,
            "successful": len(collector.successes),
            "failures": len(collector.failures),
            "errors": len(collector.errors),
            "skipped": len(collector.skipped),
        },
        "bronze_fixture_statistics": {
            "offense_category_counts": BRONZE_TEST_CATEGORY_COUNTS,
            "downloaded_count": BRONZE_TEST_TOTAL,
        },
        "tests": {
            "successful": collector.successes,
            "failures": collector.failures,
            "errors": collector.errors,
            "skipped": collector.skipped,
        },
        "text_log": str(log_path),
    }
    write_json_atomic(json_path, report)

    print(f"Text-Log:    {log_path}")
    print(f"JSON-Report: {json_path}")
    return 0 if exit_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
