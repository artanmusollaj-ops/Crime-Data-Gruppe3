"""Baut die Silver-Tabelle ``community_area``: ein Stadtteil je Zeile.

    python -m silver_pipeline.build_community_area [--data-root PFAD]

Chicago: die 77 Community Areas, Detroit: die 54 Master Plan Neighborhoods
(``gebiete_pipeline``, Ebene ``stadtteil``). Gebaut wie ``police_area`` - das
Modul ``build_police_area`` kennt beide Ebenen (``Ebene``). Unterschiede:

1. **Der Schluessel darf ein Name sein.** Chicago numeriert seine Areas
   (``1`` bis ``77``), Detroit nicht; dort ist ``area_id`` der Name des
   Stadtteils, etwa ``Brightmoor``.
2. **Der Name ist der der Quelle**, in Chicago aus Grossbuchstaben in
   gewohnte Schreibung gebracht: »ROGERS PARK« wird »Rogers Park«.
"""

from __future__ import annotations

import logging
import sys

from silver_pipeline.build_police_area import Ebene, build as _build, main as _main

TABLE = "community_area"

# Der Deutungsvertrag; jede Erhoehung gehoert in AENDERUNGEN.md,
# "Vertragsversionen". Ein Test prueft das.
CONTRACT_VERSION = 1

STADTTEIL = Ebene(TABLE, "stadtteil", "Stadtteile", {}, False,
                  "ein Stadtteil (Chicago Community Area, Detroit Master Plan Neighborhood)")


def build(data_root):
    return _build(data_root, STADTTEIL, CONTRACT_VERSION)


def main() -> int:
    return _main(STADTTEIL, CONTRACT_VERSION)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)
    raise SystemExit(main())
