"""Fuehrt alle Tests aus und schreibt Text- sowie JSON-Testprotokolle.

Start aus dem Projekt-Root:

    python -m tests.run_tests

Die Textdatei enthaelt die komplette Konsolenausgabe inklusive Kategorie-
statistik und Fehler-Tracebacks. Der JSON-Report stellt die Laufkennzahlen fuer
Monitoring, CI oder eine spaetere Ops-Tabelle maschinenlesbar bereit.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
import unittest

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


class RecordingTestResult(unittest.TextTestResult):
    """Erweitert unittest um eine Liste erfolgreich ausgefuehrter Tests."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.successes: list[str] = []

    def addSuccess(self, test) -> None:  # noqa: N802 - unittest API
        """Speichert erfolgreiche Tests fuer den JSON-Report."""

        super().addSuccess(test)
        self.successes.append(str(test))


def failure_records(entries: list[tuple[object, str]]) -> list[dict[str, str]]:
    """Konvertiert unittest-Fehler in JSON-kompatible Datensaetze."""

    return [
        {"test": str(test), "traceback": traceback_text}
        for test, traceback_text in entries
    ]


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

    suite = unittest.defaultTestLoader.discover(
        start_dir=str(TEST_DIR),
        pattern="test_*.py",
        top_level_dir=str(PROJECT_ROOT),
    )

    started_timer = perf_counter()
    with log_path.open("w", encoding="utf-8") as log_handle:
        tee = TeeStream(sys.stdout, log_handle)
        with redirect_stdout(tee), redirect_stderr(tee):
            print("Detroit Pipeline Test Run")
            print(f"Run-ID:     {run_id}")
            print(f"Started at: {started_at.isoformat()}")
            print(f"Test path:  {TEST_DIR}")
            print()

            runner = unittest.TextTestRunner(
                stream=tee,
                verbosity=2,
                resultclass=RecordingTestResult,
            )
            result = runner.run(suite)

            duration_seconds = round(perf_counter() - started_timer, 3)
            finished_at = datetime.now(timezone.utc)
            status = "SUCCESS" if result.wasSuccessful() else "FAILED"

            print()
            print("Test Run Summary:")
            print(f"  Status     : {status}")
            print(f"  Ausgefuehrt: {result.testsRun}")
            print(f"  Erfolgreich: {len(result.successes)}")
            print(f"  Fehlgeschl.: {len(result.failures)}")
            print(f"  Errors     : {len(result.errors)}")
            print(f"  Uebersprungen: {len(result.skipped)}")
            print(f"  Dauer (s)  : {duration_seconds}")

    report = {
        "pipeline": "detroit_pipeline",
        "run_id": run_id,
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "counts": {
            "tests_run": result.testsRun,
            "successful": len(result.successes),
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
        },
        "bronze_fixture_statistics": {
            "offense_category_counts": BRONZE_TEST_CATEGORY_COUNTS,
            "downloaded_count": BRONZE_TEST_TOTAL,
        },
        "tests": {
            "successful": result.successes,
            "failures": failure_records(result.failures),
            "errors": failure_records(result.errors),
            "skipped": [
                {"test": str(test), "reason": reason}
                for test, reason in result.skipped
            ],
        },
        "text_log": str(log_path),
    }
    write_json_atomic(json_path, report)

    print(f"Text-Log:   {log_path}")
    print(f"JSON-Report: {json_path}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
