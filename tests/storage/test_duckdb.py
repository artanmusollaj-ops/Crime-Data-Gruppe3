"""DuckDB und die Ablage: lokal wie bisher, S3 mit temporaerem Secret."""

from __future__ import annotations

import duckdb
import pytest

from storage import Config
from storage import duckdb as sd


def test_local_ist_eine_gewoehnliche_verbindung():
    con = sd.connect(Config(backend="local"))
    assert con.execute("SELECT 1").fetchone() == (1,)
    secrets = con.execute("SELECT count(*) FROM duckdb_secrets()").fetchone()[0]
    assert secrets == 0


def test_das_secret_ist_temporaer_pfadstil_und_maskiert_nichts_im_sql():
    config = Config(backend="s3", s3_access_key="AKIA'x", s3_secret_key="geheim",
                    s3_endpoint="s3.datenwerft.ch", s3_use_ssl=False)
    sql = sd.secret_sql(config)
    assert sql.startswith("CREATE OR REPLACE SECRET seaweedfs (TYPE S3")
    assert "PERSISTENT" not in sql
    assert "URL_STYLE 'path'" in sql and "USE_SSL false" in sql
    assert "KEY_ID 'AKIA''x'" in sql, "ein Apostroph im Schluessel bricht das SQL nicht"


def test_s3_verbindung_legt_das_secret_nur_in_der_sitzung_an():
    config = Config(backend="s3", s3_access_key="k", s3_secret_key="s")
    try:
        con = sd.connect(config)
    except sd.DuckDBFehler as fehler:
        pytest.skip(f"httpfs nicht verfuegbar: {fehler}")
    (name, persistent) = con.execute(
        "SELECT name, persistent FROM duckdb_secrets()").fetchone()
    assert name == "seaweedfs" and persistent is False
    # Eine zweite Verbindung kennt es nicht - es lebt nur in dieser.
    assert duckdb.connect().execute("SELECT count(*) FROM duckdb_secrets()").fetchone()[0] == 0
