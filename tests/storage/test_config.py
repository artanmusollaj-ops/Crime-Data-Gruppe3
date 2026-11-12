"""Die Konfiguration: drei Modi, aus der Umgebung, ohne Ueberraschungen."""

from __future__ import annotations

from pathlib import Path

import pytest

from storage import config as cfg


S3 = {"STORAGE_BACKEND": "s3", "S3_ACCESS_KEY": "k", "S3_SECRET_KEY": "s"}


def test_die_vorgabe_ist_local_und_data():
    c = cfg.load({}, dotenv=False)
    assert c.backend == "local" and c.local_root == Path("data")
    assert not c.remote and not c.publiziert and c.liest_lokal


@pytest.mark.parametrize("backend", ["s3", "hybrid"])
def test_s3_und_hybrid_brauchen_schluessel(backend):
    with pytest.raises(cfg.StorageConfigError, match="S3_ACCESS_KEY"):
        cfg.load({"STORAGE_BACKEND": backend}, dotenv=False)


def test_ein_unbekanntes_backend_ist_ein_fehler():
    with pytest.raises(cfg.StorageConfigError, match="erlaubt sind"):
        cfg.load({"STORAGE_BACKEND": "ftp"}, dotenv=False)


def test_hybrid_liest_lokal_und_publiziert_nach_dem_schreiben():
    c = cfg.load({**S3, "STORAGE_BACKEND": "hybrid"}, dotenv=False)
    assert c.remote and c.liest_lokal and c.publiziert


def test_hybrid_publish_laesst_sich_abschalten():
    c = cfg.load({**S3, "STORAGE_BACKEND": "hybrid",
                  "HYBRID_PUBLISH_AFTER_WRITE": "false"}, dotenv=False)
    assert c.remote and not c.publiziert


def test_s3_liest_nicht_lokal_und_publiziert_immer():
    c = cfg.load(S3, dotenv=False)
    assert c.remote and not c.liest_lokal and c.publiziert


def test_nur_local_als_leseprioritaet():
    with pytest.raises(cfg.StorageConfigError, match="HYBRID_READ_PRIORITY"):
        cfg.load({**S3, "STORAGE_BACKEND": "hybrid", "HYBRID_READ_PRIORITY": "s3"},
                 dotenv=False)


def test_endpoint_und_ssl():
    c = cfg.load({**S3, "S3_ENDPOINT": "s3.example.org", "S3_USE_SSL": "false"}, dotenv=False)
    assert c.endpoint_url == "http://s3.example.org"
    assert cfg.load(S3, dotenv=False).endpoint_url == "https://s3.datenwerft.ch"


def test_die_umgebung_schlaegt_die_env_datei(tmp_path, monkeypatch):
    """CI setzt Secrets in die Umgebung; eine mitgebrachte .env darf sie nicht
    ueberschreiben."""
    (tmp_path / ".env").write_text("STORAGE_BACKEND=s3\nS3_ACCESS_KEY=a\nS3_SECRET_KEY=b\n",
                                   encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.delenv("S3_ACCESS_KEY", raising=False)
    assert cfg.load().backend == "local"



def test_python_m_storage_prueft_ohne_schluessel_zu_zeigen(monkeypatch, capsys):
    """Die Pruefung sagt, was fehlt - und druckt nie einen Schluessel."""
    import storage
    from storage import __main__ as pruefung

    monkeypatch.setenv("STORAGE_BACKEND", "hybrid")
    monkeypatch.setenv("S3_ACCESS_KEY", "GEHEIM-ID")
    monkeypatch.setenv("S3_SECRET_KEY", "GEHEIM-SECRET")
    monkeypatch.setenv("S3_ENDPOINT", "s3.beispiel.invalid")
    storage.set_storage(None)
    assert pruefung.main([]) == 1
    out = capsys.readouterr().out
    assert "loest nicht auf" in out and "hybrid" in out
    assert "GEHEIM" not in out


def test_python_m_storage_im_local_modus(capsys):
    from storage import __main__ as pruefung

    assert pruefung.main([]) == 0
    assert "STORAGE_BACKEND=local" in capsys.readouterr().out


def test_nachpublizieren_zeigt_erst_und_laedt_dann_raw_vor_bronze(tmp_path, capsys):
    """Die Pipelines publizieren nur, was sie gerade schreiben; was vorher da
    war, kommt nur so hoch - Lauf fuer Lauf, Manifest zuletzt, idempotent."""
    import json

    import storage
    from storage import Config, FakeS3Client, Storage
    from storage import __main__ as befehl

    fake = FakeS3Client()
    data_root = tmp_path / "data"
    storage.set_storage(Storage(Config(backend="hybrid", local_root=data_root,
                                       s3_access_key="k", s3_secret_key="s"), fake))
    for rel in ("bronze/city=chicago/ingest_date=2026-09-05/run_a",
                "raw/city=chicago/ingest_date=2026-09-05/run_a",
                "bronze/dataset=noaa_ghcnd/station=X/run_b"):
        ordner = data_root / rel
        ordner.mkdir(parents=True)
        (ordner / "part-0001.parquet").write_bytes(b"PAR1")
        (ordner / "manifest.json").write_text(json.dumps({"status": "complete", "run_id": rel[-5:]}))
    # run_b liegt schon oben - der darf nicht noch einmal
    fake.put("bronze/dataset=noaa_ghcnd/station=X/run_b/part-0001.parquet", b"PAR1")
    fake.put("bronze/dataset=noaa_ghcnd/station=X/run_b/manifest.json",
             (data_root / "bronze/dataset=noaa_ghcnd/station=X/run_b/manifest.json").read_bytes())
    fake.uploads.clear()   # das Vorbereiten zaehlt nicht

    assert befehl.main(["publizieren"]) == 0
    out = capsys.readouterr().out
    assert "2 Lauf/Laeufe" in out and "Nichts publiziert" in out and fake.uploads == []

    assert befehl.main(["publizieren", "--wirklich"]) == 0
    assert fake.uploads == [
        "raw/city=chicago/ingest_date=2026-09-05/run_a/part-0001.parquet",
        "raw/city=chicago/ingest_date=2026-09-05/run_a/manifest.json",
        "bronze/city=chicago/ingest_date=2026-09-05/run_a/part-0001.parquet",
        "bronze/city=chicago/ingest_date=2026-09-05/run_a/manifest.json",
    ]
    assert befehl.main(["publizieren", "--wirklich"]) == 0
    assert "Nichts zu tun" in capsys.readouterr().out


def test_nachpublizieren_im_local_modus_sagt_nein(capsys, tmp_path, monkeypatch):
    # Ohne den Wechsel schriebe der Aufruf unter das echte data/ (conftest).
    monkeypatch.chdir(tmp_path)
    from storage import __main__ as befehl
    assert befehl.main(["publizieren", "--wirklich"]) == 1
    assert "nichts publiziert" in capsys.readouterr().out
