"""Auch eine Fixture, die vor dem Test entsteht, sieht keine ``.env``.

``conftest._frische_ablage`` raeumt die Ablage **je Test** auf. Eine Fixture
mit ``scope="module"`` entsteht aber davor, und am Ende des vorigen Tests
steht die Standardablage auf ``None``. ``storage.get_storage()`` liest sie
dann neu, mit ``.env``. Auf einem Rechner, dessen ``.env`` auf den Eimer
zeigt, las ``test_dashboard_taten.bestand`` am 26.11.2026 so das echte
Release statt der Testdaten: sechs von achtzehn Tests rot, nur lokal, in CI
und in einem frischen Checkout grün, denn dort gibt es keine ``.env``.

Hier liegt eine solche ``.env`` im Arbeitsverzeichnis, und eine Fixture mit
Modulgeltung fragt nach der Ablage.
"""

from __future__ import annotations

import os

import pytest

import storage

_EIMER = {
    "STORAGE_BACKEND": "s3",
    "S3_ENDPOINT": "s3.beispiel.invalid",
    "S3_ACCESS_KEY": "probe",
    "S3_SECRET_KEY": "probe",
    "S3_BUCKET": "probe",
}


@pytest.fixture(scope="module")
def ablage_vor_dem_test(tmp_path_factory):
    ort = tmp_path_factory.mktemp("mit_env")
    (ort / ".env").write_text("".join(f"{k}={v}\n" for k, v in _EIMER.items()))
    vorher_ort, vorher_env = os.getcwd(), dict(os.environ)
    storage.set_storage(None)
    os.chdir(ort)
    try:
        return storage.get_storage().config.backend
    except Exception as fehler:  # ein halber Eimer ist genauso falsch
        return f"Fehler: {fehler}"
    finally:
        os.chdir(vorher_ort)
        # load_dotenv schriebe in os.environ; nichts davon darf bleiben.
        os.environ.clear()
        os.environ.update(vorher_env)
        storage.set_storage(None)


def test_eine_modulfixture_bekommt_die_lokale_ablage(ablage_vor_dem_test):
    assert ablage_vor_dem_test == "local"
