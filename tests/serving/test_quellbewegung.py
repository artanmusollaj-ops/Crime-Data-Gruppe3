"""Die Quellbewegung - vom Silver-Unterschied bis zum Brett.

Die Faelle, in denen dieses Brett eine falsche Aussage macht, ohne zu werfen:
eine Rate ohne Zeit im Nenner (ein Monat Abstand gegen drei Stunden), ein
Eintrag, der so oft gezaehlt wird, wie sich Felder an ihm bewegt haben, ein
Test, der bei einer Handvoll Loeschungen Auffaelligkeit behauptet, und eine
Deliktsart, die beim Crosswalk verloren geht.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from serving import build_source_movement as bsm
from serving.dashboard import Bestand
from serving.dashboard.app import create_app
from serving.dashboard.quellbewegung import gleiche_rate
from silver_pipeline import build_source_change as bsc

from test_dashboard import RELEASE, TRACT_C, TRACT_D, jahr, stern

PROJEKT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Der Test auf gleiche Raten
# --------------------------------------------------------------------------


def test_gleiche_raten_und_gleiche_zahlen_sind_nicht_auffaellig():
    assert gleiche_rate(10, 100.0, 10, 100.0)["p_wert"] == pytest.approx(1.0)


def test_der_p_wert_ist_der_exakte_binomiale():
    """13 gegen 0 bei gleicher Exposition: zweiseitig 2 x 0,5^13 (R: binom.test(13, 13))."""
    assert gleiche_rate(13, 50.0, 0, 50.0)["p_wert"] == pytest.approx(2 * 0.5 ** 13)


def test_die_exposition_entscheidet_nicht_die_rohzahl():
    """Fuenf gegen null ist nicht auffaellig, wenn die eine Stadt elfmal mehr
    Eintragsmonate hat - genau der lokale Befund vom 8.11.2026."""
    test = gleiche_rate(5, 239_011.8, 0, 20_473.9)
    assert test["p_wert"] == pytest.approx(1.0)
    assert test["erwartet"] == [4.6, 0.4]
    assert test["faktor"] is None, "bei null Ereignissen gibt es keinen Faktor"


def test_ein_grosser_unterschied_ist_auffaellig_und_hat_einen_faktor():
    test = gleiche_rate(18, 1000.0, 806, 1000.0)
    assert test["p_wert"] < 1e-6
    assert test["faktor"] == pytest.approx(44.8)


def test_ohne_ereignis_gibt_es_keinen_test():
    assert gleiche_rate(0, 10.0, 0, 10.0) == {"p_wert": None, "erwartet": None, "faktor": None}


# --------------------------------------------------------------------------
# serving/source_movement
# --------------------------------------------------------------------------


def silver(root: Path, zeilen: list[dict]) -> None:
    """Eine Silver-Tabelle source_change, wie Vertrag 4 sie schreibt."""
    ziel = root / "silver" / f"dataset={bsc.TABLE}"
    ziel.mkdir(parents=True, exist_ok=True)
    grund = {s: None for s in bsc.SPALTEN}
    tabelle = pa.Table.from_pylist([grund | z for z in zeilen], schema=pa.schema(
        [(s, pa.timestamp("us") if s in ("vorher_am", "beobachtet_am", "zuerst_gesehen_am")
          else pa.int64() if s.startswith("bestand") else pa.string()) for s in bsc.SPALTEN]))
    pq.write_table(tabelle, ziel / "part-0001.parquet")
    (ziel / "manifest.json").write_text(json.dumps({
        "status": "complete", "row_count": len(zeilen), "built_at_utc": "2026-11-08T08:00:00Z",
        "input_fingerprint": "fp-source_change"}), encoding="utf-8")


PAAR_C = {"city": "chicago", "vorher_run_id": "c1", "run_id": "c2",
          "vorher_am": datetime(2026, 9, 5), "beobachtet_am": datetime(2026, 10, 5),
          "bestand_vorher": 3000, "bestand_nachher": 2999}
PAAR_D = {"city": "detroit", "vorher_run_id": "d1", "run_id": "d2",
          "vorher_am": datetime(2026, 9, 11), "beobachtet_am": datetime(2026, 9, 14),
          "bestand_vorher": 1000, "bestand_nachher": 1000}


def bewegung() -> list[dict]:
    return [
        # Chicago: eine Loeschung (IUCR 0320 -> 120), eine Aenderung an zwei Feldern.
        PAAR_C | {"offense_id": "1", "art": "verschwunden", "quellcode": "0320",
                  "quellkategorie": "ROBBERY"},
        PAAR_C | {"offense_id": "2", "art": "geaendert", "feld": "arrest", "wert_alt": "false",
                  "wert_neu": "true", "quellcode": "0486", "quellkategorie": "BATTERY"},
        PAAR_C | {"offense_id": "2", "art": "geaendert", "feld": "updated_on", "wert_alt": "a",
                  "wert_neu": "b", "quellcode": "0486", "quellkategorie": "BATTERY"},
        # Detroit: zwei Aenderungen am selben Eintrag in einem Paar, eine Beruehrung.
        PAAR_D | {"offense_id": "7", "art": "geaendert", "feld": "case_status",
                  "wert_alt": "ACTIVE", "wert_neu": "INACTIVE", "quellcode": "1300",
                  "quellkategorie": "ASSAULT"},
        PAAR_D | {"offense_id": "7", "art": "geaendert", "feld": "offense_description",
                  "wert_alt": "X", "wert_neu": "Y", "quellcode": "1300",
                  "quellkategorie": "ASSAULT"},
        PAAR_D | {"offense_id": "8", "art": "beruehrt", "feld": "updated_at",
                  "wert_alt": "1", "wert_neu": "2", "quellcode": "1300",
                  "quellkategorie": "ASSAULT"},
        # Ein ruhiges Paar: Markierungszeile, aber Bestand.
        PAAR_D | {"vorher_run_id": "d2", "run_id": "d3", "art": "unveraendert",
                  "vorher_am": datetime(2026, 9, 14), "beobachtet_am": datetime(2026, 9, 15)},
    ]


def gebaut(root: Path) -> list[dict]:
    datei = bsm.table_dir(root) / "part-0001.parquet"
    return pq.read_table(datei).to_pylist()


def test_die_arten_werden_uebersetzt_und_nichts_geht_verloren(tmp_path):
    silver(tmp_path, bewegung())
    bsm.build(tmp_path, PROJEKT / "config")
    zeilen = gebaut(tmp_path)
    assert len(zeilen) == len(bewegung())
    assert sorted({z["change_type"] for z in zeilen}) == [
        "changed", "removed", "touched", "unchanged"]


def test_die_deliktsart_kommt_ueber_den_crosswalk(tmp_path):
    """Erst auf NIBRS lassen sich die Loeschungen beider Staedte vergleichen."""
    silver(tmp_path, bewegung())
    bsm.build(tmp_path, PROJEKT / "config")
    [weg] = [z for z in gebaut(tmp_path) if z["change_type"] == "removed"]
    assert (weg["source_offense_category"], weg["nibrs_code"]) == ("ROBBERY", "120")


def test_zeitstempel_sind_markiert(tmp_path):
    silver(tmp_path, bewegung())
    bsm.build(tmp_path, PROJEKT / "config")
    stempel = {z["field"]: z["is_stamp"] for z in gebaut(tmp_path) if z["field"]}
    assert stempel["updated_on"] and stempel["updated_at"]
    assert not stempel["arrest"] and not stempel["case_status"]


def test_eine_unbekannte_art_bricht_den_bau_ab(tmp_path):
    silver(tmp_path, [PAAR_C | {"offense_id": "1", "art": "erfunden"}])
    with pytest.raises(Exception, match="unbekannte Art"):
        bsm.build(tmp_path, PROJEKT / "config")


def test_ohne_silver_entsteht_eine_leere_tabelle_mit_vermerk(tmp_path):
    """Ein Release ohne die Tabelle hiesse unvollstaendig; eine leere sagt, dass
    noch nichts zu vergleichen war."""
    bsm.build(tmp_path, PROJEKT / "config")
    assert gebaut(tmp_path) == []
    manifest = json.loads((bsm.table_dir(tmp_path) / "manifest.json").read_text(encoding="utf-8"))
    assert "keine_quelle" in manifest["notes"]
    assert list(manifest["schema"]) == list(bsm.SPALTEN)


def test_die_spalten_sind_die_angesagten(tmp_path):
    silver(tmp_path, bewegung())
    bsm.build(tmp_path, PROJEKT / "config")
    manifest = json.loads((bsm.table_dir(tmp_path) / "manifest.json").read_text(encoding="utf-8"))
    assert list(manifest["schema"]) == list(bsm.SPALTEN)


def test_die_quellbewegung_gehoert_zum_vollstaendigen_release():
    from orchestration.release import VOLLSTAENDIG

    assert "serving/dataset=source_movement" in VOLLSTAENDIG


def test_die_strecke_baut_sie_nach_silver():
    from orchestration.run_all import STUFEN

    module = [s.modul for s in STUFEN]
    assert module.index("serving.build_source_movement") > module.index(
        "silver_pipeline.build_source_change")


# --------------------------------------------------------------------------
# Das Brett
# --------------------------------------------------------------------------


def mit_bewegung(root: Path) -> Bestand:
    taten = (jahr("chicago", 2024, "120", TRACT_C, je=3) + jahr("chicago", 2024, "13A", TRACT_C)
             + jahr("detroit", 2024, "13A", TRACT_D))
    stern(root, taten)
    silver(root, bewegung())
    bsm.build(root, PROJEKT / "config")
    ziel = root / "releases" / f"release={RELEASE}" / "serving" / "dataset=source_movement"
    shutil.copytree(bsm.table_dir(root), ziel)
    return Bestand(root)


@pytest.fixture
def brett(tmp_path) -> Bestand:
    return mit_bewegung(tmp_path)


def test_ein_eintrag_zaehlt_einmal_je_paar_nicht_je_feld(brett):
    d = brett.quellbewegung({})
    detroit = next(s for s in d["staedte"] if s["stadt"] == "detroit")
    assert (detroit["geaendert"], detroit["beruehrt"]) == (1, 1)
    assert d["haeufigkeit"]["detroit"] == {"1": 1, "2": 0, "3+": 0}


def test_die_rate_teilt_durch_eintragsmonate(brett):
    """Bestand x Tage / 30 je Paar - auch das ruhige Paar zaehlt mit."""
    d = brett.quellbewegung({})
    chicago, detroit = d["staedte"]
    assert chicago["eintragsmonate"] == pytest.approx(3000 * 30 / 30)
    assert detroit["eintragsmonate"] == pytest.approx(1000 * 3 / 30 + 1000 * 1 / 30, abs=0.1)
    assert chicago["je_10000"]["entfernt"] == pytest.approx(10_000 / 3000, abs=0.01)
    assert detroit["paare"] == 2


def test_der_vergleich_steht_nur_bei_beiden_staedten(brett):
    assert [v["art"] for v in brett.quellbewegung({})["vergleich"]] == [
        "entfernt", "geaendert", "neu"]
    assert brett.quellbewegung({"stadt": "chicago"})["vergleich"] == []


def test_entfernte_eintraege_tragen_ihre_kategorie_und_ihren_anteil(brett):
    e = brett.quellbewegung({})["entfernt"]
    [k] = e["kategorien"]
    assert k["name"] == "Raub"
    assert k["anzahl"] == {"chicago": 1, "detroit": 0}
    # 36 von 48 Chicagoer Taten sind Raub.
    assert k["anteil_taten"]["chicago"] == pytest.approx(75.0)
    assert e["liste"][0]["offense_id"] == "1"


def test_stempel_sind_vorgabemaessig_ausgeblendet(brett):
    ohne = {f["feld"] for f in brett.quellbewegung({})["felder"]["chicago"]}
    mit = {f["feld"] for f in brett.quellbewegung({"felder": "alle"})["felder"]["chicago"]}
    assert ohne == {"arrest"} and mit == {"arrest", "updated_on"}


def test_ein_release_ohne_quellbewegung_laesst_das_dashboard_laden(tmp_path):
    bestand = Bestand(stern(tmp_path, jahr("chicago", 2024, "13A", TRACT_C)))
    assert bestand.quellbewegung({})["vorhanden"] is False
    assert bestand.ueberblick(bestand.auswahl({}))["kennzahlen"]["delikte"] == 12


@pytest.mark.parametrize("werte", [{"stadt": "berlin"}, {"felder": "manche"}])
def test_eine_unbekannte_wahl_ist_ein_eingabefehler(brett, werte):
    client = create_app(bestand=brett).test_client()
    antwort = client.get("/api/quellbewegung", query_string=werte)
    assert antwort.status_code == 400


def test_die_api_und_die_seite_antworten(brett):
    client = create_app(bestand=brett).test_client()
    assert client.get("/api/quellbewegung").get_json()["vorhanden"] is True
    html = client.get("/quellbewegung").get_data(as_text=True)
    assert re.search(r'<a class="aktiv" href="/quellbewegung"', html)
    assert client.get("/api/optionen").get_json()["vorgabe"]["felder"] == "inhalt"


def test_die_seite_braucht_keine_jahreswahl():
    """Die Leiste kennt nur die Stadt; starteBrett darf an fehlenden Feldern nicht scheitern."""
    js = (PROJEKT / "src/crime/serving/dashboard/static/gemeinsam.js").read_text(encoding="utf-8")
    assert "if (!select) return;" in js
