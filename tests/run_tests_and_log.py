"""Runs the project test suite and keeps the last five runs in tests/test_results.txt."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = PROJECT_ROOT / "tests"
LOG_PATH = TESTS_DIR / "test_results.txt"
HISTORY_LIMIT = 5
RUN_SEPARATOR = "\n\n===== TEST RUN =====\n"


def read_history() -> list[str]:
    if not LOG_PATH.exists():
        return []

    content = LOG_PATH.read_text(encoding="utf-8")
    if not content.strip():
        return []

    runs = [run.strip() for run in content.split(RUN_SEPARATOR) if run.strip()]
    return runs


def write_history(history: list[str]) -> None:
    combined = RUN_SEPARATOR.join(history[:HISTORY_LIMIT])
    LOG_PATH.write_text(combined + "\n", encoding="utf-8")


def main() -> int:
    timestamp = dt.datetime.now().astimezone().isoformat()
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(TESTS_DIR),
        "-v",
    ]

    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    current_run = (
        f"===== TEST RUN: {timestamp} =====\n"
        f"Command: {' '.join(command)}\n\n"
        f"{result.stdout}\n{result.stderr}\n"
        f"EXIT CODE: {result.returncode}\n"
    )

    history = read_history()
    history.insert(0, current_run.strip())
    write_history(history)

    sys.stdout.write(current_run)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
