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
