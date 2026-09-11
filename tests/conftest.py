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
from gold_pipeline import build_gold
from serving import build_analysis_db
from silver_pipeline import (
    build_crime_offense,
    build_place,
    build_tract,
    build_weather_day,
)
from weather_pipeline import download_noaa

sys.modules["build_analysis_db"] = build_analysis_db
sys.modules["build_crime_offense"] = build_crime_offense
sys.modules["build_gold"] = build_gold
sys.modules["build_place"] = build_place
sys.modules["build_tract"] = build_tract
sys.modules["build_weather_day"] = build_weather_day
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
