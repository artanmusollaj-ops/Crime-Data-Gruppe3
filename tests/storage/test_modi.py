"""Die drei Modi, in einer Tabelle - was jeder tut und was nicht.

Die Einzelheiten stehen in ``test_release.py``, ``test_holen.py`` und
``test_run_all.py``. Hier steht die **Matrix**, die man nachschlaegt: je
Modus, ob ein Gesamtlauf Raw und Bronze holt, ob er ein Release bildet, ob er
es publiziert und ob die lokale Kopie bleibt. Faellt eine Zelle, hat sich eine
Zusage aus ``storage-architektur.md`` 3 und 6a geaendert - und das Dokument
muss mit.

Warum eine eigene Datei: Am 17.9.2026 fiel beim Durchsehen der Modi auf,
dass ``s3`` als *ohne lokalen Bestand* definiert ist und ein automatisches
Holen ihn genau damit gefuellt haette. Das stand in keinem der drei
Einzeltests, weil jeder nur seinen Modus sah.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import run_all as ra
from storage import Config, FakeS3Client, Storage, set_storage
from tests.orchestration.test_run_all import bronze, falsche_stufe
from tests.storage.test_release import gebaut


# Modus -> (holt Raw/Bronze, bildet Release, publiziert es, lokale Kopie bleibt)
MATRIX = {
    "local": (False, False, False, None),
    "hybrid": (True, True, True, True),
    "s3": (False, True, True, False),
}


def lauf(tmp_path: Path, monkeypatch, backend: str) -> tuple[dict, Path, FakeS3Client]:
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    gebaut(data_root)
    fake = FakeS3Client()
    fake.put("bronze/city=chicago/ingest_date=2026-09-06/run_B/part-0001.parquet", b"PAR1")
    fake.put("bronze/city=chicago/ingest_date=2026-09-06/run_B/manifest.json",
             json.dumps({"status": "complete", "run_id": "run_B",
                         "completed_at_utc": "2026-09-17T00:00:00+00:00"}).encode())
    set_storage(Storage(Config(backend=backend, local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    return ra.lauf(data_root, tmp_path), data_root, fake


@pytest.mark.parametrize("backend", sorted(MATRIX))
def test_die_matrix_der_modi(tmp_path, monkeypatch, backend):
    holt, bildet, publiziert, kopie_bleibt = MATRIX[backend]
    manifest, data_root, fake = lauf(tmp_path, monkeypatch, backend)
    assert manifest["status"] == "complete", manifest

    geholt = bool(manifest["fetched_runs"])
    assert geholt is holt, f"{backend}: holt={geholt}, erwartet {holt}"

    freigabe = manifest["release"]
    assert (freigabe is not None) is bildet, f"{backend}: Release gebildet={freigabe is not None}"
    if freigabe:
        assert freigabe["published"] is publiziert
        kopie = (data_root / "releases" / f"release={freigabe['release_id']}").exists()
        assert kopie is kopie_bleibt, f"{backend}: lokale Kopie bleibt={kopie}"
        oben = fake.head("releases/AKTUELL.json") is not None
        assert oben is publiziert


def test_local_bildet_auf_wunsch_ein_release_und_publiziert_es_nicht(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    gebaut(data_root)
    fake = FakeS3Client()
    set_storage(Storage(Config(backend="local", local_root=data_root), fake))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    manifest = ra.lauf(data_root, tmp_path, release=True)
    assert manifest["release"]["published"] is False
    assert fake.uploads == []


def test_die_dokumentation_nennt_die_matrix():
    """Die Tabelle in storage-architektur.md 6a muss dasselbe sagen wie diese Datei."""
    text = (Path(__file__).resolve().parents[2] / "docs" / "storage-architektur.md").read_text(encoding="utf-8")
    assert "| `local` | nein — es gibt kein S3 | nur mit `run_all --release`" in text
    assert "| `hybrid` | **ja**, was oben liegt und lokal fehlt | nach jedem grünen Gesamtlauf" in text
    assert "| `s3` | nein — von Hand mit `python -m storage holen --wirklich` | wie `hybrid`, lokale Kopie danach entfernt" in text
    assert "Automatisch holt nur `hybrid`" in text
