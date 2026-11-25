"""Tests fuer die Ingestion der Polizeibezirke, ohne Netzzugriff.

Die Grenzdateien entstehen hier als kleines GeoJSON; das Portal ersetzt eine
Sitzung, die je Adresse eine feste Antwort gibt.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pyarrow.parquet as pq
import pytest

pytest.importorskip("pyogrio", reason="pyogrio wird fuer die Grenzdateien gebraucht")

from gebiete_pipeline import download_gebiete as dg  # noqa: E402

STARTED = datetime(2026, 11, 25, 8, 0, tzinfo=timezone.utc)
RUN_ID = "run_20261125T080000000000Z"
CHICAGO, DETROIT = dg.AUSLIEFERUNGEN


def quadrat(x: float, y: float) -> dict:
    return {"type": "Polygon",
            "coordinates": [[[x, y], [x + 0.1, y], [x + 0.1, y + 0.1], [x, y + 0.1], [x, y]]]}


def sammlung(*eigenschaften: dict) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": p, "geometry": quadrat(-87.7 + i * 0.2, 41.8)}
        for i, p in enumerate(eigenschaften)]}).encode()


class Antwort:
    def __init__(self, inhalt, status=200):
        self.content = inhalt if isinstance(inhalt, bytes) else json.dumps(inhalt).encode()
        self.status_code = status
        self.headers = {"Last-Modified": "Tue, 24 Nov 2026 10:00:00 GMT"}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return json.loads(self.content)


class Portal:
    def __init__(self, antworten: dict):
        self.antworten = antworten

    def get(self, url, timeout=None):
        return self.antworten[url]


CHICAGO_DATEI = sammlung({"dist_num": "1", "dist_label": "1ST"},
                         {"dist_num": "31", "dist_label": "31ST"},
                         {"dist_num": "31", "dist_label": "31ST"})


def test_ein_lauf_haelt_raw_unveraendert_und_bronze_im_gepinnten_schema(tmp_path):
    portal = Portal({CHICAGO.zaehl_url: Antwort([{"count": "3"}]),
                     CHICAGO.url: Antwort(CHICAGO_DATEI)})
    lauf = dg.write_run(tmp_path, STARTED, CHICAGO, dg.lade(portal, CHICAGO))
    assert lauf.bronze == (tmp_path / "bronze/dataset=gebiete/ebene=polizeibezirk"
                           / "city=chicago" / RUN_ID)
    assert (lauf.raw / dg.RAW_FILE).read_bytes() == CHICAGO_DATEI
    tabelle = pq.read_table(lauf.bronze / dg.PARQUET_FILE)
    assert tabelle.schema.names == ["gebiet_id", "gebiet_name", "geometry", "_extra"]
    # Nichts wird gedeutet: District 31 kommt als drei Polygone, wie geliefert.
    assert tabelle.column("gebiet_id").to_pylist() == ["1", "31", "31"]
    manifest = json.loads((lauf.bronze / "manifest.json").read_text())
    assert manifest["status"] == "complete" and manifest["city"] == "chicago"
    assert manifest["completeness"] == {"verified": True, "source_count": 3,
                                        "features_written": 3,
                                        "downloaded_bytes": len(CHICAGO_DATEI)}
    assert manifest["contract_version"] == dg.CONTRACT_VERSION


def test_weitere_felder_der_quelle_gehen_nach_extra(tmp_path):
    datei = sammlung({"name": "02", "FID": 7, "folderpath": "2015 Precincts"})
    portal = Portal({DETROIT.zaehl_url: Antwort({"count": 1}), DETROIT.url: Antwort(datei)})
    lauf = dg.write_run(tmp_path, STARTED, DETROIT, dg.lade(portal, DETROIT))
    zeile = pq.read_table(lauf.bronze / dg.PARQUET_FILE).to_pylist()[0]
    assert (zeile["gebiet_id"], zeile["gebiet_name"]) == ("02", "02")
    assert json.loads(zeile["_extra"]) == {"FID": 7, "folderpath": "2015 Precincts"}


def test_weniger_polygone_als_das_portal_zaehlt_bricht_ab_und_hinterlaesst_nichts(tmp_path):
    portal = Portal({CHICAGO.zaehl_url: Antwort([{"count": "25"}]),
                     CHICAGO.url: Antwort(CHICAGO_DATEI)})
    with pytest.raises(dg.IngestionError, match="3 Polygone gelesen, das Portal nennt 25"):
        dg.write_run(tmp_path, STARTED, CHICAGO, dg.lade(portal, CHICAGO))
    # Lokal mit Absicht: Der Test prueft, dass kein Teillauf liegen bleibt.
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


def test_eine_fehlerantwort_mit_http_200_ist_keine_grenzdatei():
    # ArcGIS meldet Fehler mit HTTP 200 und {"error": ...}.
    portal = Portal({DETROIT.zaehl_url: Antwort({"count": 12}),
                     DETROIT.url: Antwort({"error": {"code": 400, "message": "Invalid"}})})
    with pytest.raises(dg.IngestionError, match="keine FeatureCollection"):
        dg.lade(portal, DETROIT)


def test_eine_unlesbare_zaehlung_bricht_ab():
    portal = Portal({CHICAGO.zaehl_url: Antwort(b"<html>Missing Key</html>"),
                     CHICAGO.url: Antwort(CHICAGO_DATEI)})
    with pytest.raises(dg.IngestionError, match="Zaehlung ist kein JSON"):
        dg.lade(portal, CHICAGO)


def test_ein_fehlendes_kennungsfeld_bricht_ab(tmp_path):
    datei = sammlung({"bezirk": "1"})
    portal = Portal({CHICAGO.zaehl_url: Antwort([{"count": "1"}]), CHICAGO.url: Antwort(datei)})
    with pytest.raises(dg.IngestionError, match="'dist_num' fehlt"):
        dg.write_run(tmp_path, STARTED, CHICAGO, dg.lade(portal, CHICAGO))


def test_jede_studienstadt_hat_ihre_polizeibezirke():
    from silver_pipeline import STUDIENSTAEDTE
    staedte = {name.lower() for name in STUDIENSTAEDTE.values()}
    assert {a.stadt for a in dg.AUSLIEFERUNGEN if a.ebene == "polizeibezirk"} == staedte
