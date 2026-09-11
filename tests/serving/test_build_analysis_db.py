"""Tests fuer die Auswertungsdatenbank.

Sie laufen ohne Netz und ohne die echten Daten: Die Schichten werden zur
Laufzeit als kleine Parquet-Dateien erzeugt.

Die wichtigste Eigenschaft dieser Datei ist eine **Abwesenheit** - sie haelt
keine Daten, nur Namen. Das laesst sich nicht durch Hinsehen pruefen, deshalb
steht es hier als Test: Die Datenbank muss deutlich kleiner sein als die
Parquet-Dateien, auf die sie zeigt, und ``information_schema`` darf ausser den
Sichten nichts kennen.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_analysis_db as bad


def schreibe_tabelle(
    data_root: Path,
    name: str,
    zeilen: int,
    *,
    layer: str = "silver",
    partition: str = "",
    spalte: str = "wert",
) -> Path:
    """Legt eine Tabelle im Schichtenlayout ab."""
    ziel = data_root / layer / f"dataset={name}"
    if partition:
        ziel = ziel / partition
    ziel.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table({spalte: pa.array(list(range(zeilen)), type=pa.int64())}),
        ziel / bad.PARQUET_FILE,
    )
    return ziel / bad.PARQUET_FILE


def oeffne(ziel: Path, **kwargs) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(ziel), **kwargs)


# --------------------------------------------------------------------------
# Finden und Benennen
# --------------------------------------------------------------------------


def test_jede_tabelle_wird_eine_sicht(tmp_path):
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "crime_offense", 5)
    schreibe_tabelle(data_root, "weather_day", 3)

    con = oeffne(bad.build(data_root), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM crime_offense").fetchone()[0] == 5
        assert con.execute("SELECT count(*) FROM weather_day").fetchone()[0] == 3
    finally:
        con.close()


def test_der_partitionsschluessel_verschwindet_aus_dem_namen(tmp_path):
    """``dataset=tract`` wird ``tract`` - sonst muesste man Anfuehrungszeichen
    setzen, und das ist bei einer Ad-hoc-Abfrage genau die Huerde, die diese
    Schicht beseitigen soll."""
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "tract", 4, partition="vintage=2024")

    con = oeffne(bad.build(data_root), read_only=True)
    try:
        namen = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables").fetchall()}
        assert "tract" in namen
        assert not any("dataset=" in n for n in namen)
    finally:
        con.close()


def test_juengste_vintage_gewinnt(tmp_path):
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "tract", 2, partition="vintage=2023")
    schreibe_tabelle(data_root, "tract", 7, partition="vintage=2024")

    ziel = bad.build(data_root)
    con = oeffne(ziel, read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM tract").fetchone()[0] == 7
        partition = con.execute(
            "SELECT partition FROM tabellen WHERE name = 'tract'").fetchone()[0]
        assert partition == "vintage=2024", "die Sicht muss ihren Stand nennen"
    finally:
        con.close()


def test_gold_hat_vorrang_vor_silver(tmp_path):
    """Traegt Gold denselben Namen, ist es die aufbereitetere Fassung."""
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "fact_tract_month", 2, layer="silver")
    schreibe_tabelle(data_root, "fact_tract_month", 9, layer="gold")

    con = oeffne(bad.build(data_root), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM fact_tract_month").fetchone()[0] == 9
        schicht = con.execute("SELECT schicht FROM tabellen "
                              "WHERE name = 'fact_tract_month'").fetchone()[0]
        assert schicht == "gold"
    finally:
        con.close()


def test_gold_taucht_ohne_codeaenderung_auf(tmp_path):
    """Gold ist heute leer. Sobald dort etwas liegt, muss es erscheinen."""
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "crime_offense", 3)
    con = oeffne(bad.build(data_root), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM tabellen").fetchone()[0] == 1
    finally:
        con.close()

    schreibe_tabelle(data_root, "fact_city_day", 6, layer="gold")
    con = oeffne(bad.build(data_root), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM fact_city_day").fetchone()[0] == 6
    finally:
        con.close()


# --------------------------------------------------------------------------
# Die Datei haelt keine Daten
# --------------------------------------------------------------------------


def test_die_datei_haelt_keine_daten(tmp_path):
    """Der Kern der Entscheidung, als Test.

    Waeren die Tabellen materialisiert, waere die Datenbank mindestens so gross
    wie die Parquet-Dateien. Sie ist ein Bruchteil davon.
    """
    data_root = tmp_path / "data"
    quelle = schreibe_tabelle(data_root, "crime_offense", 50_000)

    ziel = bad.build(data_root)
    assert ziel.stat().st_size < quelle.stat().st_size, (
        f"Die Datenbank ({ziel.stat().st_size} B) ist nicht kleiner als die "
        f"Quelle ({quelle.stat().st_size} B) - haelt sie doch Daten?"
    )


def test_es_gibt_nur_sichten_keine_tabellen(tmp_path):
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "crime_offense", 5)

    con = oeffne(bad.build(data_root), read_only=True)
    try:
        arten = dict(con.execute(
            "SELECT table_type, count(*) FROM information_schema.tables "
            "WHERE table_schema = 'main' GROUP BY 1").fetchall())
        assert "BASE TABLE" not in arten, f"materialisierte Tabellen gefunden: {arten}"
    finally:
        con.close()


def test_neue_daten_sind_sofort_sichtbar(tmp_path):
    """Der Vorteil gegenueber einer Kopie: kein Re-Import noetig.

    Eine materialisierte Tabelle wuerde hier den alten Stand zeigen, ohne dass
    man ihr das ansieht.
    """
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "crime_offense", 5)
    ziel = bad.build(data_root)

    # Silver neu gebaut, die Datenbank bleibt unangetastet
    schreibe_tabelle(data_root, "crime_offense", 11)

    con = oeffne(ziel, read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM crime_offense").fetchone()[0] == 11
    finally:
        con.close()


# --------------------------------------------------------------------------
# Eigene Abfragen und eigene Tabellen
# --------------------------------------------------------------------------


def test_eigene_tabelle_liegt_neben_den_sichten(tmp_path):
    """Wer ein Zwischenergebnis behalten will, soll das koennen."""
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "crime_offense", 10)
    ziel = bad.build(data_root)

    con = oeffne(ziel)
    try:
        con.execute("CREATE TABLE meins AS SELECT wert FROM crime_offense WHERE wert > 5")
        assert con.execute("SELECT count(*) FROM meins").fetchone()[0] == 4
    finally:
        con.close()

    # Auch nach dem Schliessen noch da, und die Sicht ist unberuehrt.
    con = oeffne(ziel, read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM meins").fetchone()[0] == 4
        assert con.execute("SELECT count(*) FROM crime_offense").fetchone()[0] == 10
    finally:
        con.close()


def test_join_ueber_zwei_sichten(tmp_path):
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "links", 10, spalte="id")
    schreibe_tabelle(data_root, "rechts", 4, spalte="id")

    con = oeffne(bad.build(data_root), read_only=True)
    try:
        n = con.execute(
            "SELECT count(*) FROM links l JOIN rechts r ON l.id = r.id").fetchone()[0]
        assert n == 4
    finally:
        con.close()


# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------


def test_herkunft_ist_abfragbar(tmp_path):
    """Wer die Datei oeffnet, soll sie fragen koennen, was er vor sich hat."""
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "crime_offense", 5)

    con = oeffne(bad.build(data_root), read_only=True)
    try:
        herkunft = dict(con.execute("SELECT schluessel, wert FROM herkunft").fetchall())
        assert herkunft["tabellen"] == "1"
        assert "gebaut_am_utc" in herkunft
        assert "keine Daten" in herkunft["hinweis"]
    finally:
        con.close()


def test_tabellen_nennt_die_quelldatei(tmp_path):
    data_root = tmp_path / "data"
    quelle = schreibe_tabelle(data_root, "crime_offense", 5)

    con = oeffne(bad.build(data_root), read_only=True)
    try:
        datei = con.execute(
            "SELECT datei FROM tabellen WHERE name = 'crime_offense'").fetchone()[0]
        assert Path(datei) == quelle.resolve()
        assert Path(datei).is_absolute(), (
            "DuckDB loest relative Pfade gegen das Arbeitsverzeichnis auf, "
            "nicht gegen den Ort der Datenbank"
        )
    finally:
        con.close()


# --------------------------------------------------------------------------
# Betrieb
# --------------------------------------------------------------------------


def test_fehlende_schichten_nennen_den_naechsten_schritt(tmp_path):
    with pytest.raises(RuntimeError, match="silver_pipeline"):
        bad.build(tmp_path / "data")


def test_unlesbare_quelle_faellt_beim_bauen_auf(tmp_path):
    """Sonst merkt es erst der, der auswerten will."""
    data_root = tmp_path / "data"
    quelle = schreibe_tabelle(data_root, "crime_offense", 5)
    quelle.write_bytes(b"kein parquet")

    with pytest.raises(RuntimeError, match="nicht lesbar"):
        bad.build(data_root)


def test_gescheiterter_bau_laesst_keine_halbe_datenbank_zurueck(tmp_path):
    """Eine halbe Datenbank ist schlimmer als keine.

    In ihr fehlt ein Teil der Sichten, ohne dass man es ihr ansieht - wer sie
    oeffnet, haelt sie fuer vollstaendig.
    """
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "gut", 5)
    kaputt = schreibe_tabelle(data_root, "kaputt", 5)
    kaputt.write_bytes(b"kein parquet")

    with pytest.raises(RuntimeError):
        bad.build(data_root)

    ziel = bad.database_path(data_root)
    assert not ziel.exists(), "unvollstaendige Datenbank veroeffentlicht"
    assert not list(ziel.parent.glob(".*.part")), "Arbeitsdatei liegengeblieben"


def test_gescheiterter_bau_laesst_den_alten_stand_stehen(tmp_path):
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "gut", 5)
    ziel = bad.build(data_root)
    vorher = ziel.stat().st_mtime_ns

    kaputt = schreibe_tabelle(data_root, "kaputt", 5)
    kaputt.write_bytes(b"kein parquet")
    with pytest.raises(RuntimeError):
        bad.build(data_root)

    assert ziel.exists() and ziel.stat().st_mtime_ns == vorher
    con = oeffne(ziel, read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM gut").fetchone()[0] == 5
    finally:
        con.close()


def test_neubau_ersetzt_und_laesst_nichts_liegen(tmp_path):
    data_root = tmp_path / "data"
    schreibe_tabelle(data_root, "crime_offense", 5)
    ziel = bad.build(data_root)
    erst = ziel.stat().st_mtime_ns

    schreibe_tabelle(data_root, "weather_day", 2)
    ziel = bad.build(data_root)

    assert ziel.stat().st_mtime_ns != erst
    assert not list(ziel.parent.glob(".*.part")), "halbe Datenbank liegengeblieben"
    con = oeffne(ziel, read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM tabellen").fetchone()[0] == 2
    finally:
        con.close()


def test_pfad_liegt_in_der_serving_schicht(tmp_path):
    ziel = bad.database_path(tmp_path / "data")
    assert ziel.parent.name == "serving"
    assert ziel.name == "analyse.duckdb"
