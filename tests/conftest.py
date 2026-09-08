"""Macht die Ingestion-Module unter kurzen Namen verfuegbar.

Die Tests sprechen sie als ``download_chicago``, ``download_noaa``
beziehungsweise ``download_tiger`` an. Der Importpfad kommt entweder aus der editierbaren
Installation oder aus ``pythonpath`` in pyproject.toml, sodass die Tests auch
ohne Installation laufen.
"""

from __future__ import annotations

import sys

from census_pipeline import download_acs
from chicago_pipeline import download_chicago
from silver_pipeline import build_tract
from weather_pipeline import download_noaa

sys.modules["build_tract"] = build_tract
sys.modules["download_acs"] = download_acs
sys.modules["download_chicago"] = download_chicago
sys.modules["download_noaa"] = download_noaa

# Nur die TIGER-Ingestion braucht pyogrio. Fehlt es, sollen alle uebrigen Tests
# trotzdem laufen - ihre Tests ueberspringen sich selbst per importorskip.
try:
    from census_pipeline import download_tiger
except ImportError:  # pragma: no cover - haengt an der Umgebung, nicht am Code
    pass
else:
    sys.modules["download_tiger"] = download_tiger
