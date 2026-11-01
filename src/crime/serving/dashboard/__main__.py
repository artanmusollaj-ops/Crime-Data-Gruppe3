"""Lokal starten: ``python -m serving.dashboard --data-root data``."""

from __future__ import annotations

import argparse

from serving.dashboard.app import create_app
from storage import for_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m serving.dashboard")
    parser.add_argument("--data-root", default=None,
                        help="Datenwurzel; ohne Angabe die der Ablage-Einstellung")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    create_app(for_root(args.data_root).local_root).run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
