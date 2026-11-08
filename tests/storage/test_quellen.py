"""Die Quellbeschreibung ``config/quellen.toml`` und ihr Leser ``quellen``.

Gelesen wird streng, weil ein stiller Fehler hier teuer ist: Ein vertipptes
``aenderungs_feld`` ergaebe keinen Fehler, sondern einen Delta-Lauf, der nie
etwas findet - oder jedes Mal den ganzen Jahrgang.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from storage import quellen
from storage.quellen import ArcGISQuelle, QuellenFehler, SocrataQuelle

PROJEKT = Path(__file__).resolve().parents[2]

CHICAGO = """
[chicago]
plattform = "socrata"
stadt = "chicago"
anzeigename = "Chicago"
domain = "data.example.org"
datensatz = "abcd-1234"
id_feld = "id"
tatzeit_feld = "date"
aenderungs_feld = "updated_on"
felder = ["id", "date", "updated_on", "arrest", "location"]
boolesche_felder = ["arrest"]
ortsfeld = "location"
ortsunterfelder = ["latitude", "longitude"]
"""


def schreibe(tmp_path: Path, text: str) -> Path:
    (tmp_path / quellen.QUELLDATEI).write_text(text, encoding="utf-8")
    return tmp_path


def test_die_abgelegte_datei_beschreibt_chicago_wie_es_im_code_stand():
    """Die Werte, die bis zum 8.11.2026 Konstanten in ``download_chicago`` waren.

    Aendert sich einer, aendern sich Raw und Bronze jedes folgenden Laufs -
    dann gehoert der Ladevertrag erhoeht, nicht dieser Test angepasst.
    """
    q = quellen.lade("chicago")
    assert isinstance(q, SocrataQuelle)
    assert q.api_url == "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
    assert q.metadaten_url == "https://data.cityofchicago.org/api/views/ijzp-q8t2.json"
    assert (q.stadt, q.datensatz, q.id_feld) == ("chicago", "ijzp-q8t2", "id")
    assert (q.tatzeit_feld, q.aenderungs_feld) == ("date", "updated_on")
    assert q.felder == (
        "id", "case_number", "date", "block", "iucr", "primary_type",
        "description", "location_description", "arrest", "domestic", "beat",
        "district", "ward", "community_area", "fbi_code", "x_coordinate",
        "y_coordinate", "year", "updated_on", "latitude", "longitude", "location",
    )
    assert q.boolesche_felder == ("arrest", "domestic")
    assert (q.ortsfeld, q.ortsunterfelder) == (
        "location", ("latitude", "longitude", "human_address"))


def test_die_standardablage_ist_das_config_verzeichnis_des_projekts():
    assert quellen.standard_config() == PROJEKT / "config"
    assert (PROJEKT / "config" / quellen.QUELLDATEI).is_file()


def test_jede_abgelegte_quelle_hat_einen_adapter():
    for name, quelle in quellen.alle().items():
        assert quelle.plattform in quellen.PLATTFORMEN, name


def test_eine_gueltige_beschreibung_wird_gelesen(tmp_path):
    q = quellen.lade("chicago", schreibe(tmp_path, CHICAGO))
    assert q.felder == ("id", "date", "updated_on", "arrest", "location")
    assert q.api_url == "https://data.example.org/resource/abcd-1234.json"


@pytest.mark.parametrize("aenderung, meldung", [
    (('ortsfeld = "location"', 'ortsfeld = "location"\nfarbe = "blau"'),
     "unbekannte Schluessel farbe"),
    (('aenderungs_feld = "updated_on"\n', ""), "aenderungs_feld"),
    (('plattform = "socrata"', 'plattform = "ckan"'), "unbekannte Plattform 'ckan'"),
    (('aenderungs_feld = "updated_on"', 'aenderungs_feld = "updated_at"'),
     "nicht in felder: updated_at"),
    (('boolesche_felder = ["arrest"]', 'boolesche_felder = ["arrest", "domestic"]'),
     "nicht in felder: domestic"),
    (('ortsunterfelder = ["latitude", "longitude"]', 'ortsunterfelder = []'),
     "ortsfeld ohne ortsunterfelder"),
    (('datensatz = "abcd-1234"', 'datensatz = 1234'), "datensatz muss Text sein"),
    (('felder = ["id", "date"', 'felder = ["id", "id", "date"'), "Dubletten"),
])
def test_eine_fehlerhafte_beschreibung_bricht_ab_und_nennt_den_grund(
        tmp_path, aenderung, meldung):
    alt, neu = aenderung
    assert alt in CHICAGO
    with pytest.raises(QuellenFehler, match=meldung):
        quellen.lade("chicago", schreibe(tmp_path, CHICAGO.replace(alt, neu, 1)))


def test_zwei_eintraege_fuer_dieselbe_stadt_brechen_ab(tmp_path):
    doppelt = CHICAGO + CHICAGO.replace("[chicago]", "[chicago_alt]")
    with pytest.raises(QuellenFehler, match="dieselbe Stadt"):
        quellen.alle(schreibe(tmp_path, doppelt))


def test_eine_unbekannte_quelle_nennt_die_beschriebenen(tmp_path):
    with pytest.raises(QuellenFehler, match="Keine Quelle 'dallas'.*chicago"):
        quellen.lade("dallas", schreibe(tmp_path, CHICAGO))


def test_eine_fehlende_datei_bricht_ab_und_nennt_den_pfad(tmp_path):
    with pytest.raises(QuellenFehler, match="Quellbeschreibung fehlt"):
        quellen.alle(tmp_path)


DETROIT = """
[detroit]
plattform = "arcgis"
stadt = "detroit"
anzeigename = "Detroit"
layer_url = "https://example.org/FeatureServer/0"
datensatz = "RMS"
quellsystem = "detroit_rms_crime"
zeitzone = "America/Detroit"
tatzeit_feld = "incident_occurred_at"
aenderungs_feld = "updated_at"
kategorie_feld = "offense_category"
erstes_jahr = 2016
"""


def test_die_abgelegte_datei_beschreibt_detroit_wie_es_im_code_stand():
    q = quellen.lade("detroit")
    assert isinstance(q, ArcGISQuelle)
    assert q.layer_url == (
        "https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/"
        "RMS_Crime_Incidents/FeatureServer/0")
    assert (q.stadt, q.datensatz, q.quellsystem, q.zeitzone) == (
        "detroit", "RMS_Crime_Incidents", "detroit_rms_crime", "America/Detroit")
    assert (q.tatzeit_feld, q.aenderungs_feld, q.kategorie_feld, q.erstes_jahr) == (
        "incident_occurred_at", "updated_at", "offense_category", 2016)


def test_die_beiden_staedte_der_studie_sind_beschrieben():
    from silver_pipeline import STUDIENSTAEDTE

    staedte = {q.stadt for q in quellen.alle().values()}
    assert {name.lower() for name in STUDIENSTAEDTE.values()} <= staedte


@pytest.mark.parametrize("aenderung, meldung", [
    (('zeitzone = "America/Detroit"', 'zeitzone = "Europe/Gotham"'), "unbekannte Zeitzone"),
    (("erstes_jahr = 2016", 'erstes_jahr = "2016"'), "erstes_jahr muss eine ganze Zahl sein"),
    (('layer_url = "https://', 'layer_url = "http://'), "layer_url muss https sein"),
    (('aenderungs_feld = "updated_at"', 'aenderungs_feld = "incident_occurred_at"'),
     "Tatzeit- und Aenderungsfeld gleich"),
    (('kategorie_feld = "offense_category"\n', ""), "kategorie_feld"),
])
def test_eine_fehlerhafte_arcgis_beschreibung_bricht_ab(tmp_path, aenderung, meldung):
    alt, neu = aenderung
    assert alt in DETROIT
    with pytest.raises(QuellenFehler, match=meldung):
        quellen.lade("detroit", schreibe(tmp_path, DETROIT.replace(alt, neu, 1)))
