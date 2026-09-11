"""Tests fuer die Silver-Tabelle ``crime_offense``.

Sie laufen ohne Netzzugriff und ohne die echten Daten: Beide Bronze-Bestaende
und ``silver/tract`` werden zur Laufzeit erzeugt, mit denselben Eigenheiten wie
die Quellen - Chicagos Ortszeit ohne Zonenangabe, Detroits Millisekunden seit
Epoch, ueberlappende Delta-Laeufe, Platzhalterkoordinaten.

Der Schwerpunkt liegt auf dem, was beim Zusammenfuehren zweier Staedte
stillschweigend schieflaeuft: eine Zeitachse, die nur fuer eine der beiden
stimmt; ein Crosswalk, der auf die falsche Stadt angewandt wird; ein Fall, der
beim Verorten verlorengeht.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_crime_offense as bc


# --------------------------------------------------------------------------
# Hilfsmittel: Bronze und Referenzdaten erzeugen
# --------------------------------------------------------------------------

# Ein Quadrat um (-87.6, 41.9) - Chicago - und eines um (-83.1, 42.3) - Detroit.
TRACT_CHICAGO = "17031010100"
TRACT_DETROIT = "26163510100"
POLYGONE = {
    TRACT_CHICAGO: "POLYGON((-87.7 41.8, -87.5 41.8, -87.5 42.0, -87.7 42.0, -87.7 41.8))",
    TRACT_DETROIT: "POLYGON((-83.2 42.2, -83.0 42.2, -83.0 42.4, -83.2 42.4, -83.2 42.2))",
}
IN_CHICAGO = (41.9, -87.6)
IN_DETROIT = (42.3, -83.1)
IM_MEER = (0.0, -30.0)


def schreibe_tract(data_root: Path) -> None:
    ziel = data_root / "silver" / "dataset=tract" / "vintage=2024"
    ziel.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")
    werte = ", ".join(f"('{g}', '{wkt}')" for g, wkt in POLYGONE.items())
    con.execute(f"""
        COPY (SELECT geoid, ST_AsWKB(ST_GeomFromText(wkt)) AS geometry
              FROM (VALUES {werte}) AS t(geoid, wkt))
        TO '{ziel / bc.PARQUET_FILE}' (FORMAT PARQUET)
    """)
    con.close()


def schreibe_chicago(
    data_root: Path,
    zeilen: list[dict],
    *,
    run_id: str = "run_20260101T000000000000Z",
    ingest_date: str = "2026-01-01",
    status: str = "complete",
) -> Path:
    ziel = data_root / "bronze" / "city=chicago" / f"ingest_date={ingest_date}" / run_id
    ziel.mkdir(parents=True, exist_ok=True)
    spalten = ["id", "case_number", "date", "iucr", "description",
               "latitude", "longitude", "updated_on"]
    tabelle = pa.table({
        s: pa.array([str(z.get(s)) if z.get(s) is not None else None for z in zeilen],
                    type=pa.string())
        for s in spalten
    })
    tabelle = tabelle.append_column(
        "arrest", pa.array([z.get("arrest", False) for z in zeilen], type=pa.bool_())
    )
    pq.write_table(tabelle, ziel / bc.PARQUET_FILE)
    (ziel / "manifest.json").write_text(json.dumps({
        "status": status, "city": "chicago", "run_id": run_id,
        "row_count": len(zeilen),
    }), encoding="utf-8")
    return ziel


def detroit_saetze(zeilen: list[dict]) -> list[dict]:
    """Die Quellfelder, wie Detroit sie unter ``attributes`` fuehrt."""
    return [{
        "incident_entry_id": z["incident_entry_id"],
        "report_number": z.get("report_number"),
        "state_offense_code": z.get("state_offense_code"),
        "offense_description": z.get("offense_description"),
        "incident_occurred_at": z.get("incident_occurred_at"),
        "updated_at": z.get("updated_at", 0),
        "case_status": z.get("case_status"),
        "latitude": z.get("latitude"),
        "longitude": z.get("longitude"),
    } for z in zeilen]


def schreibe_detroit(
    data_root: Path,
    zeilen: list[dict],
    *,
    lauf: str = "run_aaa",
    unterpfad: str = "full/year=2024",
    status: str = "SUCCESS",
) -> Path:
    """Detroits Bronze im Parquet-Vertrag: ein Laufverzeichnis je Lauf."""
    ziel = data_root / "bronze" / "detroit" / unterpfad / lauf
    ziel.mkdir(parents=True, exist_ok=True)
    saetze = detroit_saetze(zeilen)
    tabelle = pa.table({
        "attributes": pa.array(saetze),
        "source_system": pa.array(["detroit_rms_crime"] * len(saetze)),
        "pipeline_run_id": pa.array([lauf] * len(saetze)),
    })
    pq.write_table(tabelle, ziel / bc.PARQUET_FILE)
    (ziel / "manifest.json").write_text(json.dumps({
        "status": status, "bronze_contract_version": 2,
        "storage_format": "PARQUET", "pipeline_run_id": lauf,
        "bronze_file": bc.PARQUET_FILE, "downloaded_count": len(saetze),
    }), encoding="utf-8")
    return ziel


def schreibe_detroit_ndjson(
    data_root: Path,
    zeilen: list[dict],
    *,
    lauf: str = "detroit_2024_alt",
    status: str = "SUCCESS",
) -> Path:
    """Der Bestand vor dem Parquet-Umbau: eine NDJSON flach im Verzeichnis."""
    ziel = data_root / "bronze" / "detroit"
    ziel.mkdir(parents=True, exist_ok=True)
    ndjson = ziel / f"{lauf}.ndjson"
    with ndjson.open("w", encoding="utf-8") as datei:
        for satz, z in zip(detroit_saetze(zeilen), zeilen):
            datei.write(json.dumps({
                "attributes": satz,
                "geometry": {"x": z.get("longitude"), "y": z.get("latitude")},
            }) + "\n")
    (ziel / f"{lauf}.manifest.json").write_text(json.dumps({
        "status": status, "pipeline_run_id": lauf, "downloaded_count": len(zeilen),
    }), encoding="utf-8")
    return ndjson


def schreibe_config(config_root: Path) -> None:
    """Kleine Crosswalks statt der echten - geprueft werden sie anderswo."""
    config_root.mkdir(parents=True, exist_ok=True)
    (config_root / bc.NIBRS_CODES).write_text(
        "nibrs_code,nibrs_description,nibrs_group,crime_against,federal_only,source\n"
        "13A,Aggravated Assault,A,Person,false,spec\n"
        "240,Motor Vehicle Theft,A,Property,false,spec\n"
        "90Z,All Other Offenses,B,Society,false,spec\n",
        encoding="utf-8")
    (config_root / bc.IUCR_MAPPING).write_text(
        "iucr,primary_description,secondary_description,index_code,active,"
        "ibr_code,ibr_category,match,mapped,note\n"
        "0110,HOMICIDE,X,I,true,13A,AGGRAVATED ASSAULT,nibrs_definition,true,\n"
        "0910,MOTOR VEHICLE THEFT,X,I,true,240,MOTOR VEHICLE THEFT,nibrs_definition,true,\n"
        "1481,NON-CRIMINAL,X,N,true,,,,false,kein Delikt\n",
        encoding="utf-8")
    (config_root / bc.MICR_MAPPING).write_text(
        "micr_code,micr_file_class,micr_description,nibrs_group,nibrs_code,"
        "nibrs_description,hierarchy,match,mapped,seen_in_detroit_2024,note\n"
        "1301,13001,ASSAULT,A,13A,Aggravated Assault,1,micr_manual_1110_2024,true,true,\n"
        "0910,09010,SOMETHING ELSE,B,90Z,All Other Offenses,9,micr_manual_1110_2024,true,true,\n",
        encoding="utf-8")


def baue(tmp_path: Path, chicago: list[dict], detroit: list[dict]) -> Path:
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, chicago)
    schreibe_detroit(data_root, detroit)
    schreibe_config(config_root)
    return bc.build(data_root, config_root)


def lies(ziel: Path) -> list[dict]:
    con = duckdb.connect()
    try:
        spalten = [r[0] for r in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{ziel / bc.PARQUET_FILE}')").fetchall()]
        return [dict(zip(spalten, r)) for r in con.execute(
            f"SELECT * FROM read_parquet('{ziel / bc.PARQUET_FILE}') "
            "ORDER BY city, offense_id").fetchall()]
    finally:
        con.close()


def manifest_von(ziel: Path) -> dict:
    return json.loads((ziel / "manifest.json").read_text(encoding="utf-8"))


CHI = [{"id": "1", "case_number": "JA1", "date": "2024-01-15T08:30:00.000",
        "iucr": "0110", "description": "FIRST DEGREE MURDER",
        "latitude": IN_CHICAGO[0], "longitude": IN_CHICAGO[1],
        "updated_on": "2024-02-01T00:00:00.000", "arrest": True}]
# 2024-01-15 13:30 UTC entspricht 08:30 Ortszeit in Detroit (EST, UTC-5).
DET = [{"incident_entry_id": "D1", "report_number": "R1", "state_offense_code": "1301",
        "offense_description": "ASSAULT", "incident_occurred_at": 1705325400000,
        "latitude": IN_DETROIT[0], "longitude": IN_DETROIT[1]}]


# --------------------------------------------------------------------------
# Korn und Zusammenfuehrung
# --------------------------------------------------------------------------


def test_beide_staedte_landen_in_einer_tabelle(tmp_path):
    zeilen = lies(baue(tmp_path, CHI, DET))
    assert [z["city"] for z in zeilen] == ["chicago", "detroit"]


def test_korn_ist_ein_delikt(tmp_path):
    ziel = baue(tmp_path, CHI, DET)
    pruefung = manifest_von(ziel)["checks"]["per_city"]
    for stadt, zahlen in pruefung.items():
        assert zahlen["rows"] == zahlen["distinct_offense_id"], stadt


def test_ueberlappende_delta_laeufe_erzeugen_keine_doppelten_zeilen(tmp_path):
    """Chicagos Deltas ueberlappen; dieselbe id kommt in mehreren Laeufen vor."""
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    alt = dict(CHI[0], description="ALTE FASSUNG",
               updated_on="2024-01-01T00:00:00.000")
    neu = dict(CHI[0], description="NEUE FASSUNG",
               updated_on="2024-06-01T00:00:00.000")
    schreibe_chicago(data_root, [alt], run_id="run_20260101T000000000000Z",
                     ingest_date="2026-01-01")
    schreibe_chicago(data_root, [neu], run_id="run_20260102T000000000000Z",
                     ingest_date="2026-01-02")
    schreibe_detroit(data_root, DET)
    schreibe_config(config_root)

    zeilen = [z for z in lies(bc.build(data_root, config_root))
              if z["city"] == "chicago"]
    assert len(zeilen) == 1
    assert zeilen[0]["source_offense_description"] == "NEUE FASSUNG", (
        "behalten werden muss die Fassung mit dem juengsten updated_on"
    )


def test_ueberlappende_detroit_laeufe_erzeugen_keine_doppelten_zeilen(tmp_path):
    """Seit dem Parquet-Umbau kann auch Detroit mehrere Laeufe haben.

    Ein Full Load plus taegliche Nachlaeufe ueberlappen einander; derselbe
    incident_entry_id kommt dann in mehreren Laeufen vor. Behalten wird die
    Fassung mit dem juengsten updated_at - dieselbe Regel wie bei Chicago.
    """
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_detroit(data_root, [dict(DET[0], offense_description="ALT",
                                      updated_at=1000)],
                     lauf="run_voll", unterpfad="full/year=2024")
    schreibe_detroit(data_root, [dict(DET[0], offense_description="NEU",
                                      updated_at=2000)],
                     lauf="run_taeglich", unterpfad="incremental/run_date=2026-09-11")
    schreibe_config(config_root)

    zeilen = [z for z in lies(bc.build(data_root, config_root))
              if z["city"] == "detroit"]
    assert len(zeilen) == 1
    assert zeilen[0]["source_offense_description"] == "NEU"


# --------------------------------------------------------------------------
# Der Formatwechsel: Detroit schrieb frueher NDJSON, jetzt Parquet
# --------------------------------------------------------------------------


def test_neues_laufverzeichnis_wird_gelesen(tmp_path):
    manifest = manifest_von(baue(tmp_path, CHI, DET))
    assert manifest["derived_from"]["detroit_bronze_format"] == "PARQUET"
    assert manifest["checks"]["per_city"]["detroit"]["rows"] == 1


def test_alter_ndjson_bestand_wird_nicht_mehr_gelesen(tmp_path):
    """Ein Bestand von vor dem Umbau ist nicht bloss alt, sondern falsch.

    Sein Jahresfenster war in UTC gezogen statt in Detroiter Ortszeit; er
    enthaelt 66 Faelle vom 31.12.2023 und vermisst 56 vom Jahresende 2024. Ihn
    stillschweigend weiterzulesen waere schlimmer als ein Fehler - deshalb
    nennt die Meldung den Grund und den Befehl, der es behebt.
    """
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_detroit_ndjson(data_root, DET)
    schreibe_config(config_root)

    with pytest.raises(bc.TransformError) as fehler:
        bc.build(data_root, config_root)
    meldung = str(fehler.value)
    assert "falschen Jahr" in meldung, "die Meldung muss den Grund nennen"
    assert "extract_detroit" in meldung, "und den Weg heraus"


def test_liegengebliebenes_ndjson_wird_ignoriert(tmp_path):
    """Der gefaehrlichste Fall: beide Bestaende liegen nebeneinander.

    Nach dem Umbau bleibt eine alte NDJSON-Datei womoeglich liegen. Wuerde sie
    mitgelesen, mischte die Tabelle zwei Staende - einen davon mit Faellen aus
    dem falschen Jahr. Ein Fehler, der wie ein Erfolg aussieht.
    """
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_detroit_ndjson(data_root, [dict(DET[0], incident_entry_id="ALT",
                                             offense_description="ALTER BESTAND")])
    schreibe_detroit(data_root, [dict(DET[0], incident_entry_id="NEU",
                                      offense_description="NEUER BESTAND")])
    schreibe_config(config_root)

    zeilen = [z for z in lies(bc.build(data_root, config_root))
              if z["city"] == "detroit"]
    assert [z["offense_id"] for z in zeilen] == ["NEU"]


def test_unveroeffentlichter_lauf_wird_nicht_gelesen(tmp_path):
    """Ein abgebrochener Lauf liegt in einem versteckten .partial-Verzeichnis."""
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_detroit(data_root, DET, lauf="run_fertig")
    schreibe_detroit(data_root, [dict(DET[0], incident_entry_id="HALB")],
                     lauf="run_halb", unterpfad="full/year=2024/.run_halb.partial")
    schreibe_config(config_root)

    zeilen = [z for z in lies(bc.build(data_root, config_root))
              if z["city"] == "detroit"]
    assert [z["offense_id"] for z in zeilen] == ["D1"]


def test_nicht_erfolgreicher_lauf_wird_uebergangen(tmp_path):
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_detroit(data_root, DET, lauf="run_ok")
    schreibe_detroit(data_root, [dict(DET[0], incident_entry_id="KAPUTT")],
                     lauf="run_kaputt", status="FAILED")
    schreibe_config(config_root)

    zeilen = [z for z in lies(bc.build(data_root, config_root))
              if z["city"] == "detroit"]
    assert [z["offense_id"] for z in zeilen] == ["D1"]


def test_fehlender_detroit_bestand_nennt_den_befehl(tmp_path):
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    (data_root / "bronze" / "detroit").mkdir(parents=True)
    schreibe_config(config_root)
    with pytest.raises(bc.TransformError, match="extract_detroit"):
        bc.build(data_root, config_root)


# --------------------------------------------------------------------------
# Zeitzonen - der Grund, warum es diese Tabelle braucht
# --------------------------------------------------------------------------


def test_chicago_ortszeit_wird_nach_utc_gerechnet(tmp_path):
    """``date`` ist Ortszeit ohne Zonenangabe. Im Januar gilt UTC-6."""
    zeilen = lies(baue(tmp_path, CHI, DET))
    chicago = next(z for z in zeilen if z["city"] == "chicago")
    assert str(chicago["occurred_at_local"]) == "2024-01-15 08:30:00"
    assert str(chicago["occurred_at_utc"]) == "2024-01-15 14:30:00"


def test_sommerzeit_verschiebt_den_versatz(tmp_path):
    """Im Juli gilt UTC-5 - ein fester Versatz waere eine Stunde daneben."""
    sommer = [dict(CHI[0], id="2", date="2024-07-15T08:30:00.000")]
    zeilen = lies(baue(tmp_path, sommer, DET))
    chicago = next(z for z in zeilen if z["city"] == "chicago")
    assert str(chicago["occurred_at_utc"]) == "2024-07-15 13:30:00"


def test_detroit_epoch_ist_bereits_utc(tmp_path):
    """Detroit liefert Millisekunden seit Epoch, also einen echten Zeitpunkt."""
    zeilen = lies(baue(tmp_path, CHI, DET))
    detroit = next(z for z in zeilen if z["city"] == "detroit")
    assert str(detroit["occurred_at_utc"]) == "2024-01-15 13:30:00"
    assert str(detroit["occurred_at_local"]) == "2024-01-15 08:30:00"


def test_gleiche_ortszeit_ist_nicht_derselbe_zeitpunkt(tmp_path):
    """Der eigentliche Befund: Chicago und Detroit liegen eine Stunde auseinander.

    Beide Delikte geschehen um 08:30 Ortszeit. Ohne Umrechnung sehen sie
    gleichzeitig aus; sie sind es nicht.
    """
    zeilen = lies(baue(tmp_path, CHI, DET))
    chicago = next(z for z in zeilen if z["city"] == "chicago")
    detroit = next(z for z in zeilen if z["city"] == "detroit")
    assert chicago["occurred_at_local"] == detroit["occurred_at_local"]
    assert chicago["occurred_at_utc"] != detroit["occurred_at_utc"]
    assert (chicago["occurred_at_utc"] - detroit["occurred_at_utc"]).seconds == 3600


def test_ortsdatum_folgt_der_ortszeit(tmp_path):
    """Fuer den Join auf weather_day zaehlt der Tag in der Stadt, nicht in UTC."""
    spaet = [dict(CHI[0], id="3", date="2024-01-15T23:30:00.000")]
    zeilen = lies(baue(tmp_path, spaet, DET))
    chicago = next(z for z in zeilen if z["city"] == "chicago")
    assert str(chicago["occurred_at_utc"]).startswith("2024-01-16"), "in UTC schon der Folgetag"
    assert str(chicago["occurred_date_local"]) == "2024-01-15"


# --------------------------------------------------------------------------
# NIBRS
# --------------------------------------------------------------------------


def test_jede_stadt_benutzt_ihren_eigenen_crosswalk(tmp_path):
    """Der Code 0910 steht in beiden Tabellen - und bedeutet Verschiedenes.

    In Chicagos IUCR ist er Motor Vehicle Theft, in der MICR-Testtabelle etwas
    anderes. Wuerde ein Crosswalk auf die falsche Stadt angewandt, faellt es
    genau hier auf - und sonst nirgends.
    """
    chicago = [dict(CHI[0], id="4", iucr="0910")]
    detroit = [dict(DET[0], incident_entry_id="D2", state_offense_code="0910")]
    zeilen = lies(baue(tmp_path, chicago, detroit))
    assert next(z for z in zeilen if z["city"] == "chicago")["nibrs_code"] == "240"
    assert next(z for z in zeilen if z["city"] == "detroit")["nibrs_code"] == "90Z"


def test_gruppe_und_crime_against_kommen_aus_der_amtlichen_liste(tmp_path):
    zeilen = lies(baue(tmp_path, CHI, DET))
    chicago = next(z for z in zeilen if z["city"] == "chicago")
    assert chicago["nibrs_description"] == "Aggravated Assault"
    assert chicago["nibrs_group"] == "A"
    assert chicago["crime_against"] == "Person"


def test_herkunft_der_zuordnung_bleibt_erhalten(tmp_path):
    zeilen = lies(baue(tmp_path, CHI, DET))
    assert next(z for z in zeilen if z["city"] == "chicago")["nibrs_match"] == "nibrs_definition"
    assert next(z for z in zeilen if z["city"] == "detroit")["nibrs_match"] == "micr_manual_1110_2024"


def test_unzugeordneter_code_faellt_nicht_heraus(tmp_path):
    """Ein Delikt ohne NIBRS-Zuordnung bleibt in der Tabelle, gekennzeichnet."""
    chicago = [dict(CHI[0], id="5", iucr="9999")]
    zeilen = lies(baue(tmp_path, chicago, DET))
    chi = next(z for z in zeilen if z["city"] == "chicago")
    assert chi["nibrs_mapped"] is False
    assert chi["nibrs_code"] is None
    assert chi["source_offense_code"] == "9999", "der Quellcode bleibt lesbar"


def test_nicht_zugeordnete_zeile_des_crosswalks_wirkt_nicht(tmp_path):
    """1481 steht mit mapped=false im Crosswalk und darf keinen Code erben."""
    chicago = [dict(CHI[0], id="6", iucr="1481")]
    zeilen = lies(baue(tmp_path, chicago, DET))
    assert next(z for z in zeilen if z["city"] == "chicago")["nibrs_mapped"] is False


# --------------------------------------------------------------------------
# Raum
# --------------------------------------------------------------------------


def test_punkt_im_tract_bekommt_die_geoid(tmp_path):
    zeilen = lies(baue(tmp_path, CHI, DET))
    assert next(z for z in zeilen if z["city"] == "chicago")["tract_geoid"] == TRACT_CHICAGO
    assert next(z for z in zeilen if z["city"] == "detroit")["tract_geoid"] == TRACT_DETROIT


def test_unverorteter_fall_bleibt_in_der_tabelle(tmp_path):
    """Absprache 2.4: sonst verschwindet die Verzerrung unbemerkt."""
    chicago = [dict(CHI[0], id="7", latitude=IM_MEER[0], longitude=IM_MEER[1])]
    zeilen = lies(baue(tmp_path, chicago, DET))
    chi = next(z for z in zeilen if z["city"] == "chicago")
    assert chi["located"] is False
    assert chi["tract_geoid"] is None
    assert chi["nibrs_code"] == "13A", "das Delikt bleibt auswertbar"


def test_fehlende_koordinaten_sind_kein_fehler(tmp_path):
    chicago = [dict(CHI[0], id="8", latitude=None, longitude=None)]
    zeilen = lies(baue(tmp_path, chicago, DET))
    chi = next(z for z in zeilen if z["city"] == "chicago")
    assert chi["latitude"] is None and chi["located"] is False


def test_platzhalterkoordinaten_gelten_nicht_als_ort(tmp_path):
    """Detroit setzt 0/0 statt NULL. Das ist ein Punkt im Golf von Guinea."""
    detroit = [dict(DET[0], incident_entry_id="D3", latitude=0.0, longitude=0.0)]
    zeilen = lies(baue(tmp_path, CHI, detroit))
    det = next(z for z in zeilen if z["city"] == "detroit")
    assert det["latitude"] is None
    assert det["located"] is False


# --------------------------------------------------------------------------
# Kennzeichnungen
# --------------------------------------------------------------------------


def test_unfounded_wird_gekennzeichnet_nicht_entfernt(tmp_path):
    detroit = [dict(DET[0], incident_entry_id="D4", case_status="UNFOUNDED")]
    zeilen = lies(baue(tmp_path, CHI, detroit))
    det = next(z for z in zeilen if z["city"] == "detroit")
    assert det["unfounded"] is True
    assert det["nibrs_code"] == "13A"


def test_arrest_bleibt_chicagos_angabe(tmp_path):
    """Detroit fuehrt kein vergleichbares Feld - dann steht dort NULL."""
    zeilen = lies(baue(tmp_path, CHI, DET))
    assert next(z for z in zeilen if z["city"] == "chicago")["arrest"] is True
    assert next(z for z in zeilen if z["city"] == "detroit")["arrest"] is None


# --------------------------------------------------------------------------
# Manifest und Betrieb
# --------------------------------------------------------------------------


def test_manifest_nennt_jeden_quelllauf(tmp_path):
    manifest = manifest_von(baue(tmp_path, CHI, DET))
    herkunft = manifest["derived_from"]
    assert herkunft["chicago_bronze_runs"] == ["run_20260101T000000000000Z"]
    assert herkunft["detroit_bronze_runs"] == ["run_aaa"]
    assert "tract" in herkunft["silver_tract"]
    assert len(herkunft["crosswalks"]) == 3
    # Aus welchem Format gelesen wurde, gehoert zur Herkunft: Detroit hat das
    # Format gewechselt, und beide Bestaende koennen nebeneinander liegen.
    assert herkunft["chicago_bronze_format"] == "PARQUET"
    assert herkunft["detroit_bronze_format"] == "PARQUET"


def test_manifest_nennt_die_vergleichbaren_delikte(tmp_path):
    """Die Zahl, um derentwillen die Tabelle gebaut wurde."""
    chicago = [dict(CHI[0], id="9", iucr="0110")]
    detroit = [dict(DET[0], incident_entry_id="D5", state_offense_code="1301")]
    manifest = manifest_von(baue(tmp_path, chicago, detroit))
    gemeinsam = {e["nibrs_code"]: e for e in manifest["comparable_offenses"]}
    assert "13A" in gemeinsam
    assert gemeinsam["13A"]["chicago"] == 1
    assert gemeinsam["13A"]["detroit"] == 1


def test_manifest_nennt_die_zeitzonen(tmp_path):
    manifest = manifest_von(baue(tmp_path, CHI, DET))
    assert manifest["timezones"] == {
        "chicago": "America/Chicago", "detroit": "America/Detroit"
    }


def test_manifest_nennt_das_korn(tmp_path):
    assert manifest_von(baue(tmp_path, CHI, DET))["grain"] == "ein Delikt"


def test_unvollstaendiger_lauf_wird_uebergangen(tmp_path):
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_chicago(data_root, [dict(CHI[0], id="99")],
                     run_id="run_20260102T000000000000Z",
                     ingest_date="2026-01-02", status="running")
    schreibe_detroit(data_root, DET)
    schreibe_config(config_root)
    zeilen = [z for z in lies(bc.build(data_root, config_root)) if z["city"] == "chicago"]
    assert [z["offense_id"] for z in zeilen] == ["1"]


def test_fehlende_bronze_ist_ein_klarer_fehler(tmp_path):
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_config(config_root)
    with pytest.raises(bc.TransformError, match="Chicago-Bronze-Lauf"):
        bc.build(data_root, config_root)


def test_fehlendes_tract_nennt_den_naechsten_schritt(tmp_path):
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_chicago(data_root, CHI)
    schreibe_detroit(data_root, DET)
    schreibe_config(config_root)
    with pytest.raises(bc.TransformError, match="build_tract"):
        bc.build(data_root, config_root)


def test_neubau_ersetzt_statt_anzuhaeufen(tmp_path):
    ziel = baue(tmp_path, CHI, DET)
    erst = len(lies(ziel))
    ziel = bc.build(tmp_path / "data", tmp_path / "config")
    assert len(lies(ziel)) == erst
    assert not list(ziel.parent.glob(".*"))


def test_tabellenverzeichnis_traegt_keine_vintage():
    assert bc.table_dir(Path("data")).name == "dataset=crime_offense"
