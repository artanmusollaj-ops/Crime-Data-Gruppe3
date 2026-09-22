"""Der Weg vom Release nach ClickHouse - geprueft ohne ClickHouse.

Kein Test hier braucht eine Datenbank. Der Klient ist ``FalscheDatenbank``,
ein paar Listen - dieselbe Bauart wie ``FakeS3Client`` in ``storage``, und aus
demselben Grund: Ein Test, der einen Dienst braucht, laeuft irgendwann nicht
mehr, und dann prueft niemand mehr, was er prueft.

Die Beispiele erzeugt der Test selbst. Nur eine einzige Pruefung fasst das
echte Release an - die, ob fuer **jede** Gold-Spalte ein ClickHouse-Typ
entschieden ist; sie traegt deshalb ``referenzstand``.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from serving import load_clickhouse as lc


# --------------------------------------------------------------------------
# Werkzeug
# --------------------------------------------------------------------------


def beispiel(tmp_path: Path, *, ohne_koordinate: int = 1) -> Path:
    """Ein winziges fact_offense mit genau den Eigenheiten, auf die es ankommt.

    Zwei Staedte, ein Delikt ohne Koordinate, eines ohne NIBRS-Code - das sind
    die drei Faelle, an denen sich Nullbarkeit und Schluesselwahl entscheiden.
    """
    import duckdb

    ziel = tmp_path / "part-0001.parquet"
    zeilen = [
        ("o1", "e1", "chicago", "2024-01-01 06:56:00", "2024-01-01 00:56:00",
         "2024-01-01", 0, "13A", 41.7, -87.6, "exact", "inside_city"),
        ("o2", "e2", "detroit", "2024-03-05 17:00:00", "2024-03-05 12:00:00",
         "2024-03-05", 12, "23C", 42.3, -83.0, "exact", "inside_city"),
    ]
    werte = ", ".join(
        f"('{a}', '{b}', '{c}', TIMESTAMP '{d}', TIMESTAMP '{e}', DATE '{f}', "
        f"{g}::TINYINT, '{h}', {i}::DOUBLE, {j}::DOUBLE, '{k}', '{m}')"
        for a, b, c, d, e, f, g, h, i, j, k, m in zeilen
    )
    fehlend = ", ".join(
        f"('x{n}', 'ex{n}', 'chicago', TIMESTAMP '2024-02-02 06:00:00', "
        f"TIMESTAMP '2024-02-02 00:00:00', DATE '2024-02-02', 0::TINYINT, "
        f"NULL::VARCHAR, NULL::DOUBLE, NULL::DOUBLE, 'unmapped', "
        f"'missing_coordinate')"
        for n in range(ohne_koordinate)
    )
    alle = werte + (", " + fehlend if fehlend else "")
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * FROM (VALUES {alle}) AS t(offense_id, event_id, "
        f"reporting_city, occurred_at_utc, occurred_at_local, date, "
        f"hour_of_day, nibrs_code, latitude, longitude, mapping_status, "
        f"geo_status)) TO '{ziel}' (FORMAT PARQUET)")
    con.close()
    return ziel


class FalscheDatenbank:
    """ClickHouse als drei Listen. Sie merkt sich, was ihr gesagt wurde."""

    def __init__(self, antworten: dict[str, list[tuple]]):
        self.antworten = antworten
        self.befehle: list[str] = []

    def befehl(self, sql: str) -> None:
        self.befehle.append(sql)

    def abfrage(self, sql: str) -> list[tuple]:
        # Die Reihenfolge ist wichtig: Die Verteilungsabfrage enthaelt
        # ebenfalls count(), und wer nur darauf prueft, gibt ihr die
        # Zeilenzahl zurueck. Das spezifischste Merkmal zuerst.
        if "GROUP BY" in sql:
            return self.antworten["verteilung"]
        if "uniqExact" in sql:
            return self.antworten["schluessel"]
        if "count()" in sql:
            return self.antworten["zeilen"]
        raise AssertionError(f"unerwartete Abfrage: {sql}")


def antworten_aus(parquet: Path) -> dict[str, list[tuple]]:
    """Eine Datenbank, die genau das enthaelt, was im Release steht."""
    echt = lc.abgleich_release(parquet, lc.NACH_NAME["fact_offense"])
    return {"zeilen": [(echt["zeilen"],)],
            "schluessel": [(echt["schluessel"],)],
            "verteilung": echt["verteilung"]}


# --------------------------------------------------------------------------
# Was abgelesen wird
# --------------------------------------------------------------------------


def test_die_spalten_kommen_aus_der_datei_nicht_aus_einer_liste(tmp_path):
    namen = [s.name for s in lc.spalten(beispiel(tmp_path))]
    assert namen[:3] == ["offense_id", "event_id", "reporting_city"]
    assert "dataset" not in namen, (
        "dataset ist eine Hive-Spalte aus dem Pfad und steht nicht in der Datei"
    )


def test_nullbarkeit_wird_gezaehlt_und_nicht_aus_dem_schema_geglaubt(tmp_path):
    """Parquet markiert alles als nullbar - das waere die falsche Antwort."""
    nach_name = {s.name: s for s in lc.spalten(beispiel(tmp_path))}
    assert not nach_name["offense_id"].nullable, "offense_id traegt nie NULL"
    assert not nach_name["reporting_city"].nullable
    assert nach_name["latitude"].nullable, "eine Zeile hat keine Koordinate"
    assert nach_name["nibrs_code"].nullable, "eine Zeile ist unmapped"


def test_ohne_fehlende_werte_ist_nichts_nullable(tmp_path):
    felder = lc.spalten(beispiel(tmp_path, ohne_koordinate=0))
    assert not any(s.nullable for s in felder), [s.name for s in felder if s.nullable]


# --------------------------------------------------------------------------
# Die erzeugte DDL
# --------------------------------------------------------------------------


def test_lowcardinality_liegt_aussen_um_nullable(tmp_path):
    """ClickHouse verweigert Nullable(LowCardinality(...)) - andersherum geht es."""
    nach_name = {s.name: s for s in lc.spalten(beispiel(tmp_path))}
    assert nach_name["nibrs_code"].clickhouse == "LowCardinality(Nullable(String))"
    assert nach_name["reporting_city"].clickhouse == "LowCardinality(String)"
    assert nach_name["latitude"].clickhouse == "Nullable(Float64)"


def test_jede_spalte_steht_in_der_ddl(tmp_path):
    felder = lc.spalten(beispiel(tmp_path))
    fakten = lc.NACH_NAME["fact_offense"]
    anweisung = lc.ddl("ziel", felder, fakten)
    for s in felder:
        assert f"    {s.name} {s.clickhouse}" in anweisung, s.name
    assert f"ORDER BY ({', '.join(fakten.sortierung)})" in anweisung
    assert f"PARTITION BY {fakten.partition}" in anweisung


def test_ein_unentschiedener_typ_bricht_ab_statt_zu_raten():
    with pytest.raises(lc.LadeFehler, match="kein ClickHouse-Typ"):
        lc.Spalte("irgendwas", "decimal128(9, 2)", False).clickhouse


def test_ein_nullbarer_sortierschluessel_bricht_ab(tmp_path):
    """Der Schalter allow_nullable_key wuerde das umschiffen - genau das nicht."""
    felder = [s if s.name != "reporting_city"
              else lc.Spalte(s.name, s.arrow, True)
              for s in lc.spalten(beispiel(tmp_path))]
    with pytest.raises(lc.LadeFehler, match="traegt NULL und steht im Schluessel"):
        lc.ddl("ziel", felder, lc.NACH_NAME["fact_offense"])


def test_der_tabellenname_traegt_das_release(tmp_path):
    name = lc.tabellenname("2026-09-21T12-55-05Z")
    assert name == "fact_offense_20260921T125505Z"
    assert "-" not in name and ":" not in name, "ClickHouse-Bezeichner vertragen das nicht"


# --------------------------------------------------------------------------
# Der Ablauf - und die Gegenprobe, die mehr zeigt
# --------------------------------------------------------------------------


def test_der_gute_fall_legt_die_sicht_zuletzt_um(tmp_path):
    parquet = beispiel(tmp_path)
    db = FalscheDatenbank(antworten_aus(parquet))
    bericht = lc.lade(db, "2026-09-21T12-55-05Z", parquet,
                      einfuegen=lambda z: lc.einfuegen_aus_s3(z, "u", "k", "g"))

    assert bericht["zeilen"] == 3 and bericht["schluessel"] == 3
    assert db.befehle[0].startswith("CREATE TABLE")
    assert db.befehle[1].startswith("INSERT INTO")
    assert db.befehle[-1].startswith("CREATE OR REPLACE VIEW fact_offense"), (
        "die Sicht muss zuletzt kommen - vorher darf niemand den neuen Stand sehen"
    )


def test_eine_fehlende_zeile_laesst_die_sicht_stehen(tmp_path):
    """Der Fall, fuer den es den Abgleich gibt.

    Ohne ihn zeigte ``fact_offense`` auf eine Tabelle, der eine Zeile fehlt -
    und niemand saehe es, weil die Abfrage ja ein Ergebnis liefert.
    """
    parquet = beispiel(tmp_path)
    antworten = antworten_aus(parquet)
    antworten["zeilen"] = [(antworten["zeilen"][0][0] - 1,)]
    db = FalscheDatenbank(antworten)

    with pytest.raises(lc.LadeFehler, match="zeilen"):
        lc.lade(db, "2026-09-21T12-55-05Z", parquet,
                einfuegen=lambda z: lc.einfuegen_aus_s3(z, "u", "k", "g"))
    assert not any(b.startswith("CREATE OR REPLACE VIEW") for b in db.befehle), (
        "nach einem gescheiterten Abgleich darf die Sicht nicht wandern"
    )


def test_eine_verschobene_verteilung_faellt_auch_auf(tmp_path):
    """Gleiche Zeilenzahl, andere Zusammensetzung - das faengt keine Summe."""
    parquet = beispiel(tmp_path)
    antworten = antworten_aus(parquet)
    _stadt, mapping, geo, n = antworten["verteilung"][0]
    antworten["verteilung"] = ([("detroit", mapping, geo, n)]
                               + antworten["verteilung"][1:])
    db = FalscheDatenbank(antworten)

    with pytest.raises(lc.LadeFehler, match="Verteilung"):
        lc.lade(db, "2026-09-21T12-55-05Z", parquet,
                einfuegen=lambda z: lc.einfuegen_aus_s3(z, "u", "k", "g"))


# --------------------------------------------------------------------------
# Die eine Pruefung am echten Release
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Gegen ein echtes ClickHouse - wenn eines laeuft
# --------------------------------------------------------------------------
# Die uebrigen Tests pruefen erzeugten Text. Ob ClickHouse ihn auch annimmt,
# sagen sie nicht: ``Nullable(LowCardinality(String))`` sah bis zum ersten
# echten Lauf voellig richtig aus und wird von ClickHouse verweigert. Dieser
# Test schliesst die Luecke und ueberspringt sich, wo keine Datenbank steht.
#
#     docker run -d --name crime-clickhouse -p 18123:8123 \
#         clickhouse/clickhouse-server:latest
#     CLICKHOUSE_URL=http://localhost:18123/ python -m pytest tests/serving

CLICKHOUSE = os.environ.get("CLICKHOUSE_URL", "http://localhost:18123/")


class HttpKlient:
    """So duenn, wie das Modul es verlangt: ``befehl`` und ``abfrage``.

    ``datenbank`` ist nicht Bequemlichkeit, sondern Notwendigkeit:
    ``sicht_umlegen`` benennt die Sicht immer nach dem Ziel, also
    ``fact_offense``. Liefe der Test in ``default``, loeschte sein Aufraeumen
    die Sicht, die dort einen echten Stand bedient - genau das ist beim ersten
    Lauf passiert. Er bekommt deshalb eine eigene Datenbank und raeumt die ganz
    weg.
    """

    def __init__(self, url: str, datenbank: str = "default"):
        import requests

        self.url, self.requests = url, requests
        self.datenbank = datenbank

    def befehl(self, sql: str) -> None:
        antwort = self.requests.post(f"{self.url}?database={self.datenbank}",
                                     data=sql.encode("utf-8"), timeout=60)
        if antwort.status_code != 200:
            raise AssertionError(f"{antwort.status_code}: {antwort.text[:300]}")

    def abfrage(self, sql: str) -> list[tuple]:
        # JSONCompact und nicht TSV: TSV liefert alles als Text, und wer ihn
        # zurueckrät, macht aus dem County '001' die Zahl 1.
        antwort = self.requests.post(
            f"{self.url}?database={self.datenbank}",
            data=(sql + " FORMAT JSONCompact").encode("utf-8"), timeout=60)
        if antwort.status_code != 200:
            raise AssertionError(f"{antwort.status_code}: {antwort.text[:300]}")
        return [tuple(zeile) for zeile in antwort.json()["data"]]


@pytest.fixture
def clickhouse():
    """Eine eigene Datenbank je Test - und sie verschwindet danach ganz."""
    requests = pytest.importorskip("requests")
    try:
        antwort = requests.post(CLICKHOUSE, data=b"SELECT 1", timeout=2)
        antwort.raise_for_status()
    except Exception:
        pytest.skip(f"kein ClickHouse unter {CLICKHOUSE}")

    name = f"pruefung_{uuid4().hex[:12]}"
    verwalter = HttpKlient(CLICKHOUSE)
    verwalter.befehl(f"CREATE DATABASE {name}")
    try:
        yield HttpKlient(CLICKHOUSE, name)
    finally:
        verwalter.befehl(f"DROP DATABASE IF EXISTS {name}")


def werte_anweisung(parquet: Path):
    """Die Zeilen des Beispiels als INSERT - der Weg der Daten ist hier egal."""
    import duckdb

    con = duckdb.connect()
    try:
        felder = [s.name for s in lc.spalten(parquet)]
        zeilen = con.execute(f"SELECT * FROM read_parquet('{parquet}')").fetchall()
    finally:
        con.close()

    def als_wert(v):
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "\\'") + "'"

    tupel = ", ".join("(" + ", ".join(als_wert(v) for v in z) + ")" for z in zeilen)
    return lambda ziel: f"INSERT INTO {ziel} ({', '.join(felder)}) VALUES {tupel}"


def test_clickhouse_nimmt_die_erzeugte_ddl_an(tmp_path, clickhouse):
    """Der Test, der die Schachtelung von LowCardinality gefunden haette."""
    parquet = beispiel(tmp_path)
    kennung = "9999-01-01T00-00-00Z"
    tabelle = lc.tabellenname(kennung)

    bericht = lc.lade(clickhouse, kennung, parquet,
                      einfuegen=werte_anweisung(parquet))

    assert bericht["zeilen"] == 3
    assert clickhouse.abfrage(f"SELECT count() FROM {tabelle}")[0][0] == 3
    typen = dict(clickhouse.abfrage(
        f"SELECT name, type FROM system.columns WHERE table = '{tabelle}' "
        f"AND database = '{clickhouse.datenbank}'"))
    assert typen["reporting_city"] == "LowCardinality(String)"
    assert typen["nibrs_code"] == "LowCardinality(Nullable(String))"
    assert typen["offense_id"] == "String", "ohne NULL kein Nullable"


def test_ein_unvollstaendiger_lauf_bewegt_die_sicht_nicht(tmp_path, clickhouse):
    """Dieselbe Gegenprobe wie oben, nur gegen eine echte Datenbank."""
    parquet = beispiel(tmp_path)
    voll, halb = "9999-01-01T00-00-00Z", "9999-02-02T00-00-00Z"
    einfuegen = werte_anweisung(parquet)

    lc.lade(clickhouse, voll, parquet, einfuegen=einfuegen)
    vorher = clickhouse.abfrage("SELECT count() FROM fact_offense")[0][0]

    with pytest.raises(lc.LadeFehler, match="zeilen"):
        lc.lade(clickhouse, halb, parquet,
                einfuegen=lambda z: einfuegen(z).rsplit(", (", 1)[0])

    assert clickhouse.abfrage("SELECT count() FROM fact_offense")[0][0] == vorher
    assert clickhouse.abfrage(
        f"SELECT count() FROM {lc.tabellenname(halb)}")[0][0] == 2, (
        "die halbe Tabelle liegt daneben und stoert niemanden")


# --------------------------------------------------------------------------
# Die Entscheidungen je Ziel
# --------------------------------------------------------------------------


def test_jedes_ziel_hat_eine_quelle_im_release():
    """Ein Ziel ohne Datei waere eine Entscheidung ohne Gegenstand."""
    for ziel in lc.ZIELE:
        assert ziel.quelle_im_release.startswith("gold/dataset=")
        assert ziel.quelle_im_release.endswith("part-0001.parquet")
    assert [z.name for z in lc.ZIELE][0] == "fact_offense", "die Fakten zuerst"


def test_schluessel_und_sortierung_stehen_in_der_verteilung_nicht_im_weg():
    """Wahrheitswerte gehoeren nicht in den Abgleich.

    DuckDB liefert ``True``, ClickHouse ueber TSV ``1`` - der Vergleich
    schlaege an, ohne dass etwas fehlt. Deshalb nur Text und ganze Zahlen.
    """
    for ziel in lc.ZIELE:
        assert ziel.verteilung, f"{ziel.name} hat keine Verteilung"
        assert ziel.schluessel, f"{ziel.name} hat keinen Schluessel"
        assert ziel.sortierung, f"{ziel.name} hat keine Sortierung"


def test_kleine_dimensionen_tragen_kein_lowcardinality():
    """Bei 85 Zeilen ist das Woerterbuch teurer als der Text."""
    for name in ("dim_offense", "dim_date", "dim_city_day"):
        assert not lc.NACH_NAME[name].niedrige_kardinalitaet, name
    assert lc.NACH_NAME["fact_offense"].niedrige_kardinalitaet
    assert lc.NACH_NAME["dim_tract"].niedrige_kardinalitaet


def test_ein_nullbares_array_bricht_ab():
    """ClickHouse: *Nested type Array(String) cannot be inside Nullable type*."""
    with pytest.raises(lc.LadeFehler, match="nicht in Nullable"):
        lc.Spalte("quality_flags", "list<element: string>", True,
                  "dim_city_day").clickhouse


def test_ein_array_ohne_null_geht_durch():
    assert lc.Spalte("quality_flags", "list<element: string>", False,
                     "dim_city_day").clickhouse == "Array(String)"


@pytest.mark.referenzstand
def test_fuer_jede_spalte_jedes_ziels_ist_ein_typ_entschieden():
    """Nicht nur fuer die Fakten - auch die vier Dimensionen."""
    wurzel = Path(__file__).resolve().parents[2] / "data"
    try:
        kennung, verzeichnis = lc.aktuelles_release(wurzel)
    except lc.LadeFehler as fehler:
        pytest.skip(str(fehler))
    for ziel in lc.ZIELE:
        felder = lc.spalten(lc.quelle(verzeichnis, ziel), ziel.name)
        assert felder, ziel.name
        lc.ddl(lc.tabellenname(kennung, ziel.name), felder, ziel)
