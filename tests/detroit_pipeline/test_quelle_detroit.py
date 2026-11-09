"""Der ArcGIS-Adapter liest seine Quelle aus ``config/quellen.toml``.

Bis zum 8.11.2026 standen Layer, Zeitzone und Feldnamen als Konstanten im
Code. Vor und nach dem Umzug wurden dieselben Laeufe aus festen Features
gebaut: Manifest, Zeilen und Raw-Antworten waren gleich. Diese Tests halten
die Eingaben, die das entschieden haben, und dass eine andere Quelle wirklich
jeden stadtgebundenen Wert aendert.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pyarrow.parquet as pq

import pytest

from detroit_pipeline import bronze_parquet, detroit_arcgis as da, extract_detroit as ed
from detroit_pipeline.detroit_arcgis import ArcGISLayerInfo
from storage.quellen import ArcGISQuelle, lade

JACKSONVILLE = ArcGISQuelle(
    name="jacksonville", stadt="jacksonville", anzeigename="Jacksonville",
    layer_url="https://services3.arcgis.com/x/arcgis/rest/services/Incidents/FeatureServer/0",
    datensatz="Public_Transparency_Data_View", quellsystem="jso_incidents",
    zeitzone="America/New_York", tatzeit_feld="IncidentDateTime",
    aenderungs_feld="ReportDateTime", kategorie_feld="nibrsDescription",
    erstes_jahr=2021,
)


@pytest.fixture
def andere_quelle():
    da.use_source(JACKSONVILLE)
    try:
        yield JACKSONVILLE
    finally:
        da.use_source(lade(da.DEFAULT_SOURCE))


def test_die_vorgabe_ist_detroit_wie_es_im_code_stand():
    assert da.QUELLE.name == "detroit"
    assert da.DETROIT_LAYER_URL == (
        "https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/"
        "RMS_Crime_Incidents/FeatureServer/0")
    assert (da.SOURCE_SYSTEM, da.SOURCE_TIMEZONE.key) == ("detroit_rms_crime", "America/Detroit")
    assert (da.QUELLE.tatzeit_feld, da.QUELLE.aenderungs_feld) == (
        "incident_occurred_at", "updated_at")
    assert (da.QUELLE.kategorie_feld, da.QUELLE.erstes_jahr) == ("offense_category", 2016)
    assert da.ArcGISClient().layer_url == da.DETROIT_LAYER_URL


def test_eine_andere_quelle_aendert_jeden_stadtgebundenen_wert(andere_quelle):
    assert da.build_year_where(2024) == (
        "IncidentDateTime >= TIMESTAMP '2024-01-01 05:00:00' "
        "AND IncidentDateTime < TIMESTAMP '2025-01-01 05:00:00'")
    assert da.delta_bedingung(datetime(2024, 5, 1, tzinfo=timezone.utc)) == (
        "(ReportDateTime >= TIMESTAMP '2024-05-01 00:00:00' OR ReportDateTime IS NULL)")
    assert da.build_local_date_window(date(2024, 7, 1), date(2024, 7, 2)).manifest_fields()[
        "window_timezone"] == "America/New_York"
    assert da.ArcGISClient().layer_url == andere_quelle.layer_url
    with pytest.raises(ValueError, match="erst ab 2021"):
        da.build_year_where(2020)
    with pytest.raises(ValueError, match="Nicht erlaubtes Datumsfeld: updated_at"):
        da.build_local_date_window(date(2024, 1, 1), date(2024, 1, 2)).where("updated_at")


class EinFeature:
    layer_url = JACKSONVILLE.layer_url
    aufzeichner = None
    FELDER = (("OBJECTID", "esriFieldTypeOID"), ("IncidentDateTime", "esriFieldTypeDate"),
              ("ReportDateTime", "esriFieldTypeDate"), ("nibrsDescription", "esriFieldTypeString"))
    FEATURE = {"attributes": {"OBJECTID": 7, "IncidentDateTime": 1717200000000,
                              "ReportDateTime": 1717300000000, "nibrsDescription": "VANDALISM"}}

    def get_layer_info(self):
        return ArcGISLayerInfo("OBJECTID", 10, "fp", tuple(n for n, _ in self.FELDER), self.FELDER)

    def get_count(self, where, *, name="count"):
        return 1

    def get_object_ids(self, where):
        return "OBJECTID", [7]

    def iter_features(self, ids, **kwargs):
        yield self.FEATURE


def test_ein_lauf_einer_anderen_quelle_traegt_ihre_namen(andere_quelle, tmp_path):
    bronze, manifest = ed.extract_delta(2024, tmp_path / "b", client=EinFeature(),
                                        pause_seconds=0)
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert (m["source_system"], m["dataset_id"]) == ("jso_incidents",
                                                     "Public_Transparency_Data_View")
    assert m["date_field"] == "IncidentDateTime"
    assert m["watermark"]["field"] == "ReportDateTime"
    assert m["offense_category_counts"] == {"VANDALISM": 1}
    assert m["window_timezone"] == "America/New_York"
    zeile = pq.read_table(bronze).to_pylist()[0]
    assert zeile["source_system"] == "jso_incidents"
    assert bronze_parquet.detroit_arcgis is da


def test_source_waehlt_die_verzeichnisse_der_stadt(tmp_path):
    args = ed.parse_args(["--source", "detroit", "--mode", "delta", "--years", "2024",
                          "--data-root", str(tmp_path)])
    assert args.output_dir.parts[-2:] == ("bronze", "city=detroit")
    assert args.raw_dir.parts[-2:] == ("raw", "city=detroit")


@pytest.mark.parametrize("name, meldung", [
    ("atlantis", "Keine Quelle 'atlantis'"),
    ("chicago", "chicago liegt nicht auf ArcGIS"),
])
def test_eine_unbrauchbare_quelle_bricht_beim_aufruf_ab(name, meldung, capsys):
    with pytest.raises(SystemExit) as abbruch:
        ed.parse_args(["--source", name, "--mode", "delta", "--years", "2024"])
    assert abbruch.value.code == 2
    assert meldung in capsys.readouterr().err
    assert da.QUELLE.name == "detroit"
