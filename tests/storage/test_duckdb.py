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


# --------------------------------------------------------------------------
# Das Auslagerungsverzeichnis (gefunden am 16.10.2026 auf srv01)
# --------------------------------------------------------------------------


def test_ein_auslagerungsverzeichnis_wird_uebernommen():
    """Ohne es ist ``memory_limit`` eine Wand statt einer Bremse.

    Am 16.10.2026 starb der Serverlauf bei ``silver crime_offense``:
    *„could not allocate block of size 256.0 KiB (854.6 MiB/854.4 MiB
    used)"* - und 854,4 MiB sind genau die 896 MB, die der Stapel setzt. Die
    innere Grenze ist Absicht (sonst toetet der Kernel den Container), ihr
    fehlte nur der Ausweg.
    """
    gesetzt = sd.grenzen({"DUCKDB_TEMP_DIRECTORY": "/app/data/duckdb-tmp"})
    assert gesetzt == {"temp_directory": "/app/data/duckdb-tmp"}


def test_ein_relatives_auslagerungsverzeichnis_wird_abgelehnt():
    """Relativ haengt es am Arbeitsverzeichnis des Aufrufs - und das ist je
    nach Stufe ein anderes. Ein Verzeichnis, das mal hier und mal dort
    entsteht, ist schlimmer als keines."""
    with pytest.raises(sd.DuckDBFehler, match="absoluter Pfad"):
        sd.grenzen({"DUCKDB_TEMP_DIRECTORY": "duckdb-tmp"})


def test_ohne_angabe_bleibt_das_auslagern_DuckDBs_entscheidung():
    """Leer heisst nicht setzen - wie bei den beiden anderen Grenzen."""
    assert "temp_directory" not in sd.grenzen({})
    assert "temp_directory" not in sd.grenzen({"DUCKDB_TEMP_DIRECTORY": "  "})


def test_ausgelagert_laeuft_was_sonst_am_speicher_scheitert(tmp_path):
    """Die Zusage selbst, gemessen statt behauptet.

    Dieselbe Abfrage, einmal ohne und einmal mit Auslagerungsverzeichnis -
    bei einer Grenze, die sie nicht im Speicher schafft. Ohne das
    Verzeichnis wirft DuckDB genau die Fehlerform von srv01.
    """
    duckdb = pytest.importorskip("duckdb")

    def versuch(ziel: str | None) -> str | None:
        con = duckdb.connect(":memory:")
        try:
            con.execute("SET memory_limit='150MB'")
            con.execute("SET threads=2")
            con.execute(f"SET temp_directory='{ziel or ''}'")
            con.execute("""
                SELECT count(*) FROM (
                  SELECT i, repeat(md5(i::VARCHAR), 12) AS breit
                  FROM range(2500000) AS t(i) ORDER BY breit)""")
            return None
        except duckdb.Error as fehler:
            return str(fehler)
        finally:
            con.close()

    ohne = versuch(None)
    assert ohne is not None and "Out of Memory" in ohne, (
        "ohne Auslagerung lief die Abfrage durch - dann misst dieser Test "
        f"nichts mehr: {ohne}")
    assert versuch(str(tmp_path)) is None, (
        "mit Auslagerung scheiterte sie trotzdem")


# --------------------------------------------------------------------------
# Die Grenzen stehen im Protokoll (gelernt am 16.10.2026)
# --------------------------------------------------------------------------


def test_die_gesetzten_grenzen_stehen_im_protokoll(caplog, monkeypatch):
    """Sonst bleibt offen, ob eine Einstellung ueberhaupt ankam.

    Derselbe Lauf scheiterte an jenem Tag zweimal an derselben
    Speichergrenze, und beide Male war unklar, ob das
    Auslagerungsverzeichnis ankommt: Die Variable stand in
    ``docker-compose.srv01.yml``, aber ob das **Abbild** sie kennt, sagte
    niemand - ein altes Abbild ignoriert sie stillschweigend.
    """
    monkeypatch.setattr(sd, "_gemeldet", False)
    con = duckdb.connect(":memory:")
    try:
        with caplog.at_level("INFO", logger="storage.duckdb"):
            sd.grenzen_setzen(con, {"DUCKDB_MEMORY_LIMIT": "512MB",
                                    "DUCKDB_TEMP_DIRECTORY": "/tmp/x"})
    finally:
        con.close()
    zeile = " ".join(caplog.messages)
    assert "memory_limit=512MB" in zeile
    assert "temp_directory=/tmp/x" in zeile


def test_auch_keine_grenze_ist_eine_nachricht(caplog, monkeypatch):
    """*Keine Grenze* heisst: DuckDB rechnet mit der ganzen Maschine. Das ist
    die wichtigere der beiden Meldungen und darf nicht stumm bleiben."""
    monkeypatch.setattr(sd, "_gemeldet", False)
    con = duckdb.connect(":memory:")
    try:
        with caplog.at_level("INFO", logger="storage.duckdb"):
            sd.grenzen_setzen(con, {})
    finally:
        con.close()
    assert "keine gesetzt" in " ".join(caplog.messages)


def test_die_meldung_kommt_einmal_je_prozess(caplog, monkeypatch):
    """Jede Stufe oeffnet mehrere Verbindungen; zehnmal dieselbe Zeile hilft
    niemandem."""
    monkeypatch.setattr(sd, "_gemeldet", False)
    con = duckdb.connect(":memory:")
    try:
        with caplog.at_level("INFO", logger="storage.duckdb"):
            for _ in range(3):
                sd.grenzen_setzen(con, {"DUCKDB_MEMORY_LIMIT": "512MB"})
    finally:
        con.close()
    assert sum("DuckDB-Grenzen" in m for m in caplog.messages) == 1
