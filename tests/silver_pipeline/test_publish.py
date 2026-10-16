"""Die atomare Ersetzung einer abgeleiteten Tabelle.

Geprueft wird das, was ``silver_pipeline.publish`` zusagt: Ein Leser sieht nie
einen halben Stand, und ein Lauf raeumt nicht weg, woran ein anderer gerade
schreibt. Der zweite Teil kam am 15.9.2026 dazu - eine externe Pruefung wies
darauf hin, dass die Arbeitsverzeichnisse feste Namen trugen.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from silver_pipeline import publish


@pytest.fixture
def con():
    verbindung = duckdb.connect()
    verbindung.execute("CREATE TABLE t AS SELECT 1 AS a")
    try:
        yield verbindung
    finally:
        verbindung.close()


def test_die_tabelle_entsteht_vollstaendig(con, tmp_path):
    ziel = publish(con, "t", tmp_path / "dataset=x", {"status": "complete"})
    assert (ziel / "part-0001.parquet").is_file()
    assert json.loads((ziel / "manifest.json").read_text())["status"] == "complete"
    assert not list(tmp_path.glob(".*")), "Arbeitsverzeichnis liegengeblieben"


def test_ein_fremdes_arbeitsverzeichnis_bleibt_unberuehrt(con, tmp_path):
    """Der Befund der externen Pruefung, als Zusage formuliert.

    Bis zum 15.9.2026 hiess das Arbeitsverzeichnis fest ``.<name>.part``, und
    jeder Lauf raeumte es zu Beginn weg. Zwei gleichzeitige Laeufe derselben
    Tabelle zerstoerten einander damit das halbfertige Ergebnis.

    Der Test stellt genau diesen Namen hin. Gegen den alten Code verschwindet
    das Verzeichnis, gegen den neuen bleibt es - denn der eigene Name traegt
    jetzt die Prozessnummer und kann mit keinem fremden zusammenfallen.
    """
    ziel = tmp_path / "dataset=x"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fremd = tmp_path / f".{ziel.name}.part"
    fremd.mkdir()
    (fremd / "halbfertig.parquet").write_bytes(b"gerade im Schreiben")

    publish(con, "t", ziel, {"status": "complete"})

    assert fremd.is_dir() and (fremd / "halbfertig.parquet").is_file(), (
        "der Lauf hat das Arbeitsverzeichnis eines anderen Prozesses entfernt"
    )


class BrichtAb:
    """Eine Verbindung, deren ``execute`` scheitert - der Rest bleibt echt.

    Direkt an ``con.execute`` laesst sich nichts binden; DuckDB-Verbindungen
    nehmen kein neues Attribut an.
    """

    def __init__(self, echt) -> None:
        self._echt = echt

    def execute(self, *_, **__):
        raise RuntimeError("Abbruch mitten im Schreiben")

    def __getattr__(self, name):
        return getattr(self._echt, name)


def test_ein_gescheiterter_lauf_laesst_den_alten_stand_stehen(con, tmp_path):
    ziel = publish(con, "t", tmp_path / "dataset=x",
                   {"status": "complete", "row_count": 1})
    with pytest.raises(RuntimeError):
        publish(BrichtAb(con), "t", ziel, {"status": "complete", "row_count": 2})

    assert json.loads((ziel / "manifest.json").read_text())["row_count"] == 1
    assert (ziel / "part-0001.parquet").is_file()


# ---------------------------------------------------------------------------
# Die Zeilenordnung der geschriebenen Datei
# ---------------------------------------------------------------------------
# Bis zum 16.10.2026 nahm ``publish`` die *physische* Ordnung der Tabelle, und
# die haengt am Abfrageplan: ``threads`` und ``preserve_insertion_order``
# veraendern sie, und damit die Parquet-Bytes. Das war der Grund, warum keiner
# der drei Auswege, die DuckDB bei einem Speicherfehler vorschlaegt, benutzbar
# war - die Reproduzierbarkeit ruhte auf einem Zufall statt auf einer Zusage.


def test_mit_ordnung_steht_die_datei_in_der_genannten_reihenfolge(tmp_path):
    """Nicht der SQL-Text wird geprueft, sondern die geschriebene Datei.

    Ein Test, der ``"ORDER BY" in sql`` prueft, bliebe gruen, wenn die
    Sortierung an der falschen Stelle stuende - genau der Fehler, der hier
    behoben wurde.
    """
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=false")
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES (3), (1), (2)) AS v(a)")
    ziel = publish(con, "t", tmp_path / "dataset=x", {"status": "complete"},
                   ordnung="a")
    gelesen = con.execute(
        f"SELECT a FROM read_parquet('{ziel / 'part-0001.parquet'}')"
    ).fetchall()
    con.close()
    assert [z[0] for z in gelesen] == [1, 2, 3], \
        "die Datei steht nicht in der zugesagten Ordnung"


def test_dieselbe_tabelle_in_anderer_einfuegeordnung_gibt_dieselben_bytes(tmp_path):
    """Die eigentliche Zusage: Die Bytes haengen am Schluessel, nicht am Plan.

    Zweimal dieselben Zeilen, einmal aufsteigend und einmal absteigend
    eingefuegt. Ohne ``ordnung`` unterscheiden sich die Dateien - mit ihr
    nicht. Das ist der Unterschied, der ``threads`` und
    ``preserve_insertion_order`` als Ausweg freigibt.
    """
    dateien = []
    for richtung in ("ASC", "DESC"):
        con = duckdb.connect()
        con.execute(
            f"CREATE TABLE t AS SELECT i AS a, i::VARCHAR AS b "
            f"FROM range(5000) r(i) ORDER BY i {richtung}"
        )
        ziel = publish(con, "t", tmp_path / f"dataset={richtung}",
                       {"status": "complete"}, ordnung="a")
        dateien.append((ziel / "part-0001.parquet").read_bytes())
        con.close()
    assert dateien[0] == dateien[1], \
        "die Bytes haengen noch an der Einfuegeordnung, nicht am Schluessel"


def test_ohne_ordnung_bleibt_es_beim_alten_verhalten(con, tmp_path):
    """Sechs Aufrufer nennen noch keine Ordnung - sie brauchen je einen
    eigenen eindeutigen Schluessel, und einen zu raten waere schlimmer als
    die heutige Lage. Bis dahin darf ``publish`` ohne Ordnung nicht brechen.
    """
    ziel = publish(con, "t", tmp_path / "dataset=x", {"status": "complete"})
    assert (ziel / "part-0001.parquet").is_file()
