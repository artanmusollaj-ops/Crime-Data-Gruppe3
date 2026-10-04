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


# ---------------------------------------------------------------------------
# FR-61: memory_limit und threads
# ---------------------------------------------------------------------------


def test_ohne_umgebung_wird_nichts_gesetzt():
    """Der heutige Zustand bleibt, solange niemand etwas vorgibt."""
    assert sd.grenzen({}) == {}


def test_beide_grenzen_kommen_aus_der_umgebung():
    assert sd.grenzen({"DUCKDB_MEMORY_LIMIT": "2GB", "DUCKDB_THREADS": "3"}) == {
        "memory_limit": "2GB", "threads": "3",
    }


def test_ein_leerer_wert_ist_keine_angabe():
    """``DUCKDB_THREADS=`` in einer .env darf die Parallelitaet nicht abschalten."""
    assert sd.grenzen({"DUCKDB_MEMORY_LIMIT": "", "DUCKDB_THREADS": "  "}) == {}


@pytest.mark.parametrize("wert", ["0", "-2", "zwei", "2.5"])
def test_unbrauchbare_fadenzahl_scheitert_laut(wert):
    with pytest.raises(sd.DuckDBFehler, match="DUCKDB_THREADS"):
        sd.grenzen({"DUCKDB_THREADS": wert})


def test_die_grenzen_landen_wirklich_auf_der_verbindung():
    con = sd.verbinde(env={"DUCKDB_MEMORY_LIMIT": "2GB", "DUCKDB_THREADS": "2"})
    speicher, faeden = con.execute(
        "SELECT current_setting('memory_limit'), current_setting('threads')"
    ).fetchone()
    assert faeden == 2
    # DuckDB rechnet GB in GiB um, deshalb kein Vergleich auf den Wortlaut.
    assert "GiB" in speicher and speicher.startswith("1.8")


def test_eine_grenze_die_duckdb_ablehnt_scheitert_statt_still_zu_verfallen():
    """Eine still verworfene Grenze ist schlimmer als keine."""
    with pytest.raises(sd.DuckDBFehler, match="memory_limit"):
        sd.verbinde(env={"DUCKDB_MEMORY_LIMIT": "ganz viel"})


def test_connect_setzt_die_grenzen_auch_im_local_modus():
    con = sd.connect(Config(backend="local"))
    assert con.execute("SELECT current_setting('threads')").fetchone()[0] >= 1


def test_keine_verbindung_umgeht_die_grenzen():
    """Der Docstring sagt zu, dass jede Verbindung hier durchgeht.

    Ein eigenes ``duckdb.connect`` ist der zweite Weg in denselben Code - und
    der zweite Weg ist der, der irgendwann ohne Grenze laeuft. Am 3.10.2026
    waren es neun Stellen.
    """
    import re
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[2]
    erlaubt = wurzel / "src" / "crime" / "storage" / "duckdb.py"
    muster = re.compile(r"(?<!storage_)(?<!storage\.)\bduckdb\.connect\s*\(")

    gefunden: list[str] = []
    for ordner in ("src", "tools"):
        for datei in (wurzel / ordner).rglob("*.py"):
            if datei == erlaubt or "__pycache__" in datei.parts:
                continue
            for nummer, zeile in enumerate(
                datei.read_text(encoding="utf-8").splitlines(), 1
            ):
                if muster.search(zeile):
                    gefunden.append(f"{datei.relative_to(wurzel)}:{nummer}")

    assert not gefunden, (
        "diese Stellen verbinden an storage.duckdb vorbei und laufen damit "
        "ohne memory_limit: " + ", ".join(gefunden)
    )
