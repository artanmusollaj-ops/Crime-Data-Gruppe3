"""Macht das Chicago-Modul unter einem kurzen Namen verfuegbar.

Die Tests sprechen es als ``download_chicago`` an. Der Importpfad kommt
entweder aus der editierbaren Installation oder aus ``pythonpath`` in
pyproject.toml, sodass die Tests auch ohne Installation laufen.
"""

from __future__ import annotations

import sys

from chicago_pipeline import download_chicago

sys.modules["download_chicago"] = download_chicago
