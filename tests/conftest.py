"""Macht die Ingestion-Module unter kurzen Namen verfuegbar.

Die Tests sprechen sie als ``download_chicago``, ``download_noaa``
beziehungsweise ``download_tiger`` an. Der Importpfad kommt entweder aus der editierbaren
Installation oder aus ``pythonpath`` in pyproject.toml, sodass die Tests auch
ohne Installation laufen.
"""

from __future__ import annotations

import subprocess
import sys

from census_pipeline import download_acs
from chicago_pipeline import download_chicago
from gold_pipeline import build_gold
import manifeste
from orchestration import aufraeumen, drift, run_all
from serving import build_analysis_db, build_comparison, export_geojson
from silver_pipeline import (
    build_crime_offense,
    build_place,
    build_tract,
    build_weather_day,
)
from weather_pipeline import download_noaa

sys.modules["build_analysis_db"] = build_analysis_db
sys.modules["build_comparison"] = build_comparison
sys.modules["export_geojson"] = export_geojson
sys.modules["build_crime_offense"] = build_crime_offense
sys.modules["build_gold"] = build_gold
sys.modules["manifeste"] = manifeste
sys.modules["run_all"] = run_all
sys.modules["aufraeumen"] = aufraeumen
sys.modules["drift"] = drift


# Die Ablage kommt aus der Umgebung und wird einmal gelesen. Zwischen zwei
# Tests darf davon nichts uebrigbleiben - und kein Test darf versehentlich
# gegen eine .env des Entwicklers laufen, die auf SeaweedFS zeigt.
#
# Seit dem 6.10.2026 stehen fuenf weitere in derselben Liste: PROJECT_ROOT,
# GIT_COMMIT und die drei Dienst-URLs. Sie gehoeren dem Betrieb im Container
# (siehe Dockerfile), und jede aendert eine Vorgabe - die Projektwurzel, die
# Herkunftsangabe, die Adresse eines Laders. Ein Lauf der Suite in einer
# Umgebung, die sie gesetzt hat, pruefte andere Zusagen als einer auf dem
# Entwicklungsrechner. Wer sie braucht, setzt sie im Test selbst.
import pytest  # noqa: E402
import storage  # noqa: E402


@pytest.fixture(autouse=True)
def _frische_ablage(monkeypatch):
    for name in ("STORAGE_BACKEND", "LOCAL_DATA_ROOT", "S3_ENDPOINT", "S3_ACCESS_KEY",
                 "S3_SECRET_KEY", "S3_BUCKET", "S3_USE_SSL", "HYBRID_READ_PRIORITY",
                 "HYBRID_PUBLISH_AFTER_WRITE", "PROJECT_ROOT", "GIT_COMMIT",
                 "ELASTICSEARCH_URL", "CLICKHOUSE_URL", "KIBANA_URL"):
        monkeypatch.delenv(name, raising=False)
    storage.set_storage(storage.Storage(storage.Config()))
    yield
    storage.set_storage(None)
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


@pytest.fixture(scope="session")
def benutzbares_bash() -> str:
    """Ein wirklich benutzbares POSIX-``bash``, sonst uebersprungen.

    **Warum nicht ``shutil.which("bash")``.** Auf den Windows-Laeufern von
    GitHub Actions liegt ein ``bash.exe`` im Pfad - der Starter von WSL. Ohne
    installierte Distribution gibt er Rueckgabewert 1 und eine
    UTF-16-Meldung *„…<distro>' to install."* aus. Vorhanden ist er also, nur
    kann er nichts. Am 17.10.2026 fielen deshalb fuenf Tests auf dem
    Windows-Job um, und zwar mit einer leeren Fehlermeldung, weil der Text
    auf stdout stand und nicht auf stderr.

    Gefragt wird deshalb nicht, ob es ihn gibt, sondern ob er **antwortet**.

    Uebersprungen statt rot: Die drei Dateien, die hier haengen, pruefen
    Shell-Skripte fuer `srv01` - ein Linux-Server. Auf einer Maschine ohne
    bash ist ihr Ergebnis keine Aussage ueber den Code. **Die Sammlung bleibt
    unberuehrt**, die Testzahl also auf jeder Plattform dieselbe; ein
    Modulskip beim Sammeln haette sie verschoben
    (`tests/test_sammelzeit_abhaengigkeiten.py` sagt, was das anrichtet).
    """
    try:
        fertig = subprocess.run(["bash", "-c", "printf ok"],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as fehler:
        pytest.skip(f"kein bash aufrufbar: {fehler}")
    if fertig.returncode != 0 or fertig.stdout.strip() != "ok":
        pytest.skip("'bash' im Pfad antwortet nicht wie ein POSIX-bash "
                    f"(Rueckgabe {fertig.returncode}, Ausgabe "
                    f"{fertig.stdout[:60]!r}) - auf Windows ist das der "
                    "WSL-Starter ohne Distribution")
    return "bash"
