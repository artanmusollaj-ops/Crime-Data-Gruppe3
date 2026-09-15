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
