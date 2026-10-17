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

import csv
import json
from datetime import datetime, timezone
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
    # Mit Manifest, wie build_tract es schreibt - crime_offense nennt daraus
    # den Stand, auf dem es ruht.
    (ziel / "manifest.json").write_text(json.dumps({
        "status": "complete", "table": "tract", "layer": "silver",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_fingerprint": "t" * 64,
        "derived_from": [{"layer": "bronze", "dataset": "tiger_tract",
                          "run_id": "run_20260101T000000000000Z"}],
    }), encoding="utf-8")


def schreibe_chicago(
    data_root: Path,
    zeilen: list[dict],
    *,
    run_id: str = "run_20260101T000000000000Z",
    ingest_date: str = "2026-01-01",
    status: str = "complete",
    mode: str | None = None,
    event_year: int | None = None,
    started_at_utc: str | None = None,
) -> Path:
    """``mode``, ``event_year`` und ``started_at_utc`` sind **ohne Vorgabe**.

    Die echten Manifeste tragen sie; hier fehlen sie, und damit laeuft der
    Bau durch den Rueckfallzweig von ``ab_dem_juengsten_vollabzug`` - ohne
    Vollabzug bleiben alle Laeufe. Das ist Absicht: So bedeuten die siebzig
    Tests, die es vor dem 17.10.2026 gab, weiterhin dasselbe. Wer die Regel
    selbst pruefen will, setzt die drei Felder.
    """
    ziel = data_root / "bronze" / "city=chicago" / f"ingest_date={ingest_date}" / run_id
    ziel.mkdir(parents=True, exist_ok=True)
    # ``primary_type`` seit Silver-Vertrag 3: Chicagos Beschreibung besteht
    # aus zwei Haelften, und die Silber-Spalte fuehrt beide.
    spalten = ["id", "case_number", "date", "iucr", "primary_type", "description",
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
    manifest = {
        "status": status, "city": "chicago", "run_id": run_id,
        "row_count": len(zeilen),
    }
    if mode is not None:
        manifest["mode"] = mode
    if event_year is not None:
        manifest["event_year"] = event_year
    if started_at_utc is not None:
        manifest["started_at_utc"] = started_at_utc
    (ziel / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return ziel


def detroit_saetze(zeilen: list[dict]) -> list[dict]:
    """Die Quellfelder, wie Detroit sie unter ``attributes`` fuehrt."""
    return [{
        "incident_entry_id": z["incident_entry_id"],
        "report_number": z.get("report_number"),
        # Der Vorfall, zu dem die Zeile gehoert. Mehrere Anklagen zur selben
        # Tat teilen ihn sich; ohne ihn laesst sich das Tatebene nicht bilden.
        "case_id": z.get("case_id", z["incident_entry_id"]),
        "state_offense_code": z.get("state_offense_code"),
        # Die Anklage. Sie faellt bei 3,6 Prozent der echten Zeilen von der
        # Tat ab - genau daran haengt die Auswahl der zaehlenden Zeile.
        "charge_description": z.get(
            "charge_description", z.get("offense_description")),
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
    ziel = data_root / "bronze" / bc.DETROIT_BRONZE / unterpfad / lauf
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
    ziel = data_root / "bronze" / bc.DETROIT_BRONZE
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
        "nibrs_description,hierarchy,match,mapped,note\n"
        "1301,13001,ASSAULT,A,13A,Aggravated Assault,1,micr_manual_1110_2024,true,\n"
        "0910,09010,SOMETHING ELSE,B,90Z,All Other Offenses,9,micr_manual_1110_2024,true,\n"
        # Fuer die Auswahl der zaehlenden Zeile: zwei Codes mit verschiedenem
        # Rang. Im echten Handbuch steht 1302 auf 4 und 2901 auf 16 - hier
        # genuegt, dass der eine schwerer wiegt als der andere.
        "1302,13002,AGGRAVATED ASSAULT,A,13A,Aggravated Assault,4,micr_manual_1110_2024,true,\n"
        "1172,11002,CSC 3RD DEGREE,A,13A,Aggravated Assault,2,micr_arrest_charge_1110_2024,true,\n"
        "2307,23007,LARCENY - OTHER,A,90Z,All Other Offenses,6,micr_manual_1110_2024,true,\n"
        "1201,12001,CARJACKING,A,13A,Aggravated Assault,3,micr_manual_1110_2024,true,\n"
        "2901,29000,DAMAGE TO PROPERTY,A,90Z,All Other Offenses,16,micr_manual_1110_2024,true,\n"
        # Fuer das Fallebene: ein Eigentumsdelikt aus der Hierarchie (240) neben
        # einem Personendelikt (13A) und einem Auffangcode (90Z).
        "2401,24001,MOTOR VEHICLE THEFT,A,240,Motor Vehicle Theft,7,micr_manual_1110_2024,true,\n",
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
        "iucr": "0110", "primary_type": "HOMICIDE",
        "description": "FIRST DEGREE MURDER",
        "latitude": IN_CHICAGO[0], "longitude": IN_CHICAGO[1],
        "updated_on": "2024-02-01T00:00:00.000", "arrest": True}]
# 2024-01-15 13:30 UTC entspricht 08:30 Ortszeit in Detroit (EST, UTC-5).
DET = [{"incident_entry_id": "D1", "report_number": "R1", "case_id": "F1",
        "state_offense_code": "1301", "offense_description": "ASSAULT",
        "incident_occurred_at": 1705325400000,
        "latitude": IN_DETROIT[0], "longitude": IN_DETROIT[1]}]


# --------------------------------------------------------------------------
# Granularität und Zusammenfuehrung
# --------------------------------------------------------------------------


def test_beide_staedte_landen_in_einer_tabelle(tmp_path):
    zeilen = lies(baue(tmp_path, CHI, DET))
    assert [z["city"] for z in zeilen] == ["chicago", "detroit"]


def test_granularitaet_ist_ein_delikt(tmp_path):
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
    # Seit Vertrag 3 traegt die Spalte beide Haelften: "HOMICIDE: NEUE FASSUNG".
    assert zeilen[0]["source_offense_description"] == "HOMICIDE: NEUE FASSUNG", (
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


def test_ein_detroit_delta_loescht_den_bestand_darunter_nicht(tmp_path):
    """Seit dem 18.9.2026 bringt ein Detroit-Lauf nur noch das Geaenderte.

    Damit haengt Silver an der Vereinigung **aller** Laeufe, nicht mehr am
    juengsten allein. Wuerde hier nur der letzte gelesen, saehe man es der
    Tabelle nicht an: Sie waere nur kuerzer - um alles, was sich seit dem
    Vollschnappschuss nicht geaendert hat.
    """
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_detroit(data_root, [dict(DET[0], incident_entry_id="RUHIG",
                                      offense_description="UNBERUEHRT",
                                      updated_at=1000),
                                 dict(DET[0], incident_entry_id="BEWEGT",
                                      offense_description="ALT",
                                      updated_at=1000)],
                     lauf="run_voll", unterpfad="full/year=2024")
    schreibe_detroit(data_root, [dict(DET[0], incident_entry_id="BEWEGT",
                                      offense_description="NEU",
                                      updated_at=2000)],
                     lauf="run_delta", unterpfad="full/year=2024")
    schreibe_config(config_root)

    zeilen = {z["offense_id"]: z for z in lies(bc.build(data_root, config_root))
              if z["city"] == "detroit"}
    assert set(zeilen) == {"RUHIG", "BEWEGT"}, (
        "der Bestand aus dem Vollschnappschuss fehlt - Silver liest nur den "
        "juengsten Lauf statt aller"
    )
    assert zeilen["BEWEGT"]["source_offense_description"] == "NEU"
    assert zeilen["RUHIG"]["source_offense_description"] == "UNBERUEHRT"


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
    (data_root / "bronze" / bc.DETROIT_BRONZE).mkdir(parents=True)
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
    assert "tract" in herkunft["silver_tract"]["path"]
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


def test_manifest_nennt_das_granularitaet(tmp_path):
    """Seit dem Tatebene-Umbau ist eine Zeile eine **Anklage**, kein Delikt.

    Das Manifest sagte bis zum 12.9. weiter "ein Delikt" - und der Feldkatalog,
    der die Granularität aus den Manifesten liest, haette es so uebernommen. Genau
    dafuer steht es hier als Test: Die Granularität ist die Aussage, die eine Tabelle
    ueber sich selbst macht, und Detroits Zeilen sind Anklagen.
    """
    granularitaet = manifest_von(baue(tmp_path, CHI, DET))["grain"]
    assert granularitaet.startswith("eine Anklage"), granularitaet
    assert "counts" in granularitaet, "die Granularität muss sagen, welche Zeile zaehlt"
    assert "counts_case" in granularitaet, "und welche je Fall zaehlt"


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


# --------------------------------------------------------------------------
# Gegen die echten Daten, wenn vorhanden
# --------------------------------------------------------------------------


def echte_tabelle() -> Path | None:
    """Die gebaute Silver-Tabelle, oder None. ``data/`` ist nicht versioniert."""
    pfad = (PROJECT_ROOT / "data" / "silver" / "dataset=crime_offense"
            / bc.PARQUET_FILE)
    return pfad if pfad.exists() else None


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def gebaute_jahre() -> tuple[int, ...]:
    """Die Jahrgaenge, die der letzte Gesamtlauf gebaut hat - gelesen, nicht geraten.

    ``run_all`` schreibt am Ende ``data/pipeline_run.json`` und nennt darin
    ``years``. Eine Silver-Tabelle sagt es von sich aus nicht: Sie liegt an
    einem Pfad ohne ``year=``, und genau darum muss die Erwartung von aussen
    kommen. Bis zum 4.10.2026 stand hier die Zahl 2024 im Test, weil es nur
    einen Jahrgang gab.

    Gelesen wird die Datei hier direkt und nicht ueber ``storage``: Der Test
    prueft den Bestand auf dieser Platte, und eine Silver-Pruefung soll nicht
    das Orchestrierungspaket importieren muessen. Fehlt das Protokoll, kommt
    ``()`` zurueck - dann ueberspringen die Pruefungen, statt zu raten.
    """
    protokoll = PROJECT_ROOT / "data" / "pipeline_run.json"
    if not protokoll.is_file():
        return ()
    try:
        jahre = json.loads(protokoll.read_text(encoding="utf-8")).get("years")
    except (OSError, ValueError):
        return ()
    if not isinstance(jahre, list):
        return ()
    return tuple(sorted(int(j) for j in jahre if isinstance(j, int)))


def test_kein_fall_liegt_ausserhalb_der_gebauten_jahrgaenge():
    """Die Pruefung, die das falsche Abfragefenster sichtbar gemacht hat.

    Ein Jahrgang 2024 enthaelt keine Faelle aus 2023 - diese Aussage ist
    unabhaengig vom Code wahr und deshalb die einzige, die den Fehler zeigt.
    Detroits Fenster war frueher in UTC gezogen statt in Ortszeit; da Detroit
    fuenf Stunden hinter UTC liegt, nahm es den Abend des 31.12.2023 mit. 66
    Faelle lagen dadurch im falschen Jahr, und weder Schemapruefung noch
    Vollstaendigkeitsnachweis schlugen an: Die Werte waren gueltige
    Zeitstempel, die Zeilenzahlen stimmten, das Manifest meldete Erfolg.

    Geprueft wird die **Ortszeit**, nicht UTC. In UTC liegen Faelle vom
    Silvesterabend beider Staedte korrekt im Folgejahr; das ist kein Fehler,
    sondern der Grund, warum die Tabelle beide Achsen fuehrt.

    **Was der Mehrjahresbau an dieser Pruefung aendert.** Mit einem Jahrgang
    war jede Nachbarjahr-Zeile ein Fund. Mit sechs zusammenhaengenden
    Jahrgaengen in einer Tabelle faellt ein in UTC gezogenes Fenster nur noch
    an den **Aussenraendern** auf - Dezember 2020 oder Januar 2027 -, denn
    innen liegt das Nachbarjahr selbst in der Erwartungsmenge. Der Rand ist
    geblieben, weil dasselbe Fenster fuer jeden Jahrgang gezogen wird: Zieht
    es 2021 in UTC, liegen Faelle in 2020, und der Test schlaegt an. Was er
    nicht mehr sieht, ist eine Verschiebung **nur** in einem Innenjahr.
    """
    tabelle = echte_tabelle()
    jahre = gebaute_jahre()
    if tabelle is None:
        pytest.skip("silver/crime_offense nicht gebaut")
    if not jahre:
        pytest.skip("data/pipeline_run.json nennt keine Jahrgaenge")

    liste = ", ".join(str(j) for j in jahre)
    con = duckdb.connect()
    try:
        falsch = con.execute(f"""
            SELECT city, year(occurred_date_local) AS jahr, count(*)
            FROM read_parquet('{tabelle}')
            WHERE year(occurred_date_local) NOT IN ({liste})
            GROUP BY 1, 2 ORDER BY 1, 2
        """).fetchall()
    finally:
        con.close()
    assert not falsch, (
        f"Faelle ausserhalb der gebauten Jahrgaenge ({liste}), nach "
        f"Ortszeit: {falsch}. Ist ein Abfragefenster in UTC statt in "
        "Ortszeit gezogen?"
    )


def test_beide_staedte_liegen_in_jedem_gebauten_jahrgang():
    """Gegenprobe: sonst haelt der Test oben auch bei einer leeren Tabelle.

    Und sie ist seit dem Mehrjahresbau mehr als eine Gegenprobe: Faellt ein
    Jahrgang beim Bauen aus, bleibt die Tabelle gueltig und die Erwartungsmenge
    stimmt weiter - nur eine Stadt fehlt dann in einem Jahr. Geprueft wird
    deshalb jede Paarung aus Stadt und Jahr, nicht die Tabelle als Ganzes.
    """
    tabelle = echte_tabelle()
    jahre = gebaute_jahre()
    if tabelle is None:
        pytest.skip("silver/crime_offense nicht gebaut")
    if not jahre:
        pytest.skip("data/pipeline_run.json nennt keine Jahrgaenge")

    con = duckdb.connect()
    try:
        gezaehlt = dict(
            ((stadt, jahr), n) for stadt, jahr, n in con.execute(f"""
                SELECT city, year(occurred_date_local) AS jahr, count(*)
                FROM read_parquet('{tabelle}') GROUP BY 1, 2
            """).fetchall()
        )
    finally:
        con.close()
    erwartet = {(stadt, jahr) for stadt in ("chicago", "detroit")
                for jahr in jahre}
    assert set(gezaehlt) == erwartet, sorted(erwartet - set(gezaehlt))
    assert all(n > 1000 for n in gezaehlt.values()), gezaehlt


def test_die_gemessenen_zeilen_je_jahrgang_decken_dieselben_jahre_ab():
    """``config/zeilen_je_jahrgang.csv`` und der gebaute Stand im Gleichschritt.

    Die CSV traegt die an den beiden APIs **gemessenen** Zeilen je Stadt und
    Jahr; die Hochrechnung des Platzbedarfs rechnet damit. Verglichen wird hier
    nur die **Menge** der Jahre, nicht die Zeilenzahl: Die Messung ist vom
    3.10.2026, geladen wurde am 4.10., und der laufende Jahrgang waechst
    taeglich - Chicago 2021 weicht um eine Zeile ab, Detroit 2026 um 240. Eine
    Toleranz, die das traegt, muesste groesser sein als die 66 Zeilen, an denen
    der Zeitzonenfehler oben haengt; sie waere also eine Zusage, die weniger
    prueft als ihr eigenes Rauschen. Die Mengenaussage dagegen haelt: Wer einen
    Jahrgang dazubaut und die Messung nicht nachfuehrt, rechnet den Platzbedarf
    ohne ihn hoch.
    """
    jahre = gebaute_jahre()
    if not jahre:
        pytest.skip("data/pipeline_run.json nennt keine Jahrgaenge")
    pfad = PROJECT_ROOT / "config" / "zeilen_je_jahrgang.csv"
    if not pfad.is_file():
        pytest.skip(f"{pfad} fehlt")
    gemessen: dict[str, set[int]] = {}
    with pfad.open(encoding="utf-8", newline="") as datei:
        for zeile in csv.DictReader(datei):
            if zeile.get("stadt"):
                gemessen.setdefault(
                    zeile["stadt"].strip().lower(), set()
                ).add(int(zeile["jahr"]))
    assert set(gemessen) == {"chicago", "detroit"}, sorted(gemessen)
    for stadt, jahrgaenge in sorted(gemessen.items()):
        assert jahrgaenge == set(jahre), (
            f"{stadt}: gemessen {sorted(jahrgaenge)}, gebaut {list(jahre)}"
        )


def test_tabellenverzeichnis_traegt_keine_vintage():
    assert bc.table_dir(Path("data")).name == "dataset=crime_offense"


# --------------------------------------------------------------------------
# Tatebene: welche Zeile zaehlt
# --------------------------------------------------------------------------
#
# Detroits Zeilen sind Anklagen, Chicagos sind Delikte. Ein Ueberfall mit
# Schuessen und geraubtem Auto steht bei Detroit als fuenf Zeilen, bei Chicago
# als eine; wer beide summiert, zaehlt Detroit zu hoch.
#
# Welches Feld die Tat traegt, sagen die Daten: Bei Vorfaellen mit mehreren
# Zeilen ist offense_description in 38,4 Prozent konstant, charge_description
# nur in 2,3 Prozent. Silver behaelt jede Anklage und markiert je Tat eine
# Zeile mit ``counts``.
#
# Artan hat das gefunden, an einer Zeile mit offense_category LARCENY und
# offense_description "CSC 3RD DEGREE - PENIS / VAGINA".


def det_zeile(nr: str, fall: str, code: str, anklage: str, tat: str) -> dict:
    return {
        "incident_entry_id": nr, "report_number": f"R{fall}", "case_id": fall,
        "state_offense_code": code, "charge_description": anklage,
        "offense_description": tat, "incident_occurred_at": 1705325400000,
        "latitude": IN_DETROIT[0], "longitude": IN_DETROIT[1],
    }


def test_chicagos_zeile_zaehlt_immer(tmp_path):
    """Eine Chicago-Zeile ist bereits ein Delikt, keine Anklage."""
    zeilen = [z for z in lies(baue(tmp_path, CHI, DET)) if z["city"] == "chicago"]
    assert all(z["counts"] for z in zeilen)
    assert {z["counts_reason"] for z in zeilen} == {"eine_zeile_ist_ein_delikt"}


def test_zwei_anklagen_zur_selben_tat_zaehlen_einmal(tmp_path):
    """Artans Fall: eine CSC-Tat, dazu eine Larceny-Anklage.

    Beide Zeilen bleiben erhalten - die Anklage ist eine Tatsache und wird
    nicht weggeworfen. Gezaehlt wird die Zeile, deren Anklage die Tat selbst
    ist; sie traegt damit schon den richtigen MICR-Code.
    """
    detroit = [
        det_zeile("D1", "F1", "2307", "LARCENY - OTHER", "CSC 3RD DEGREE"),
        det_zeile("D2", "F1", "1172", "CSC 3RD DEGREE", "CSC 3RD DEGREE"),
    ]
    zeilen = {z["offense_id"]: z for z in lies(baue(tmp_path, CHI, detroit))
              if z["city"] == "detroit"}
    assert len(zeilen) == 2, "beide Anklagen bleiben in Silver"
    assert zeilen["D2"]["counts"] is True
    assert zeilen["D2"]["counts_reason"] == "anklage_ist_die_tat"
    assert zeilen["D1"]["counts"] is False
    assert zeilen["D1"]["counts_reason"] == "weitere_anklage_zur_selben_tat"
    assert zeilen["D1"]["offense_group_id"] == zeilen["D2"]["offense_group_id"]


def test_zwei_verschiedene_taten_im_selben_vorfall_zaehlen_zweimal(tmp_path):
    """Ein Vorfall kann mehrere Taten tragen - dann zaehlen sie einzeln."""
    detroit = [
        det_zeile("D1", "F1", "1302", "AGGRAVATED ASSAULT", "AGGRAVATED ASSAULT"),
        det_zeile("D2", "F1", "1201", "CARJACKING", "CARJACKING"),
    ]
    zeilen = [z for z in lies(baue(tmp_path, CHI, detroit)) if z["city"] == "detroit"]
    assert sum(1 for z in zeilen if z["counts"]) == 2
    assert len({z["offense_group_id"] for z in zeilen}) == 2


def test_ohne_passende_anklage_entscheidet_die_hierarchie(tmp_path):
    """Die 19 Faelle, in denen keine Anklage die Tat selbst nennt.

    Dann gilt die schwerste - die Hierarchie des MICR-Handbuchs, in der 1
    Mord ist und 16 Sachbeschaedigung. ``1302`` Aggravated Assault steht auf
    Rang 11, ``2901`` Damage to Property auf 16.
    """
    detroit = [
        det_zeile("D1", "F1", "2901", "DAMAGE TO PROPERTY", "THREATS - GENERAL"),
        det_zeile("D2", "F1", "1302", "AGGRAVATED ASSAULT", "THREATS - GENERAL"),
    ]
    zeilen = {z["offense_id"]: z for z in lies(baue(tmp_path, CHI, detroit))
              if z["city"] == "detroit"}
    assert zeilen["D2"]["counts"] is True, "die schwerere Anklage zaehlt"
    assert zeilen["D2"]["counts_reason"] == "schwerste_anklage"
    assert zeilen["D1"]["counts"] is False


def test_je_tat_zaehlt_genau_eine_zeile(tmp_path):
    """Die Zusage in einem Satz - sonst zaehlt Detroit doppelt."""
    detroit = [
        det_zeile("D1", "F1", "2307", "LARCENY - OTHER", "CSC 3RD DEGREE"),
        det_zeile("D2", "F1", "1172", "CSC 3RD DEGREE", "CSC 3RD DEGREE"),
        det_zeile("D3", "F1", "2901", "DAMAGE TO PROPERTY", "CSC 3RD DEGREE"),
        det_zeile("D4", "F2", "1302", "AGGRAVATED ASSAULT", "AGGRAVATED ASSAULT"),
    ]
    zeilen = [z for z in lies(baue(tmp_path, CHI, detroit)) if z["city"] == "detroit"]
    je_tat = {}
    for z in zeilen:
        je_tat.setdefault(z["offense_group_id"], []).append(z["counts"])
    for gruppe, marken in je_tat.items():
        assert sum(1 for m in marken if m) == 1, f"{gruppe}: {marken}"


# --------------------------------------------------------------------------
# mapping_status
# --------------------------------------------------------------------------


def test_mapping_status_deckt_jede_herkunft_der_crosswalks_ab():
    """Jeder ``match``-Wert in den Crosswalks braucht eine Einstufung.

    Sonst faellt der Bau erst auf, wenn die Daten den betroffenen Code
    enthalten - also moeglicherweise erst beim naechsten Jahrgang. Der Test
    liest die Crosswalks selbst statt einer gepflegten Liste.
    """
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    try:
        vorhanden = set()
        for datei in ("iucr_nibrs_mapping.csv", "micr_nibrs_mapping.csv"):
            pfad = PROJECT_ROOT / "config" / datei
            if not pfad.exists():
                continue
            vorhanden |= {
                z[0] for z in con.execute(
                    f"SELECT DISTINCT match FROM read_csv('{pfad}') "
                    "WHERE mapped = 'true'"
                ).fetchall() if z[0]
            }
    finally:
        con.close()
    fehlend = sorted(vorhanden - set(bc.MAPPING_STATUS))
    assert not fehlend, (
        f"ohne Einstufung in MAPPING_STATUS: {fehlend}. Eintragen und dabei "
        "entscheiden, ob die Zuordnung belegt (exact) oder eine Entscheidung "
        "(ambiguous) ist."
    )


def test_mapping_status_kennt_nur_die_vier_stufen():
    erlaubt = {"exact", "ambiguous", "fallback_90Z", "unmapped"}
    assert set(bc.MAPPING_STATUS.values()) <= erlaubt


def test_der_auffangcode_ist_keine_exakte_zuordnung():
    """90Z ist ein gueltiger Code und trotzdem kein vergleichbares Delikt.

    Er entsteht auf zwei Wegen: Chicagos Crosswalk fuehrt ihn als
    ``nibrs_auffang``, Detroits MICR-Handbuch bildet Codes direkt darauf ab.
    Der zweite Weg traegt eine Herkunft, die sonst ``exact`` waere - deshalb
    entscheidet in der Abfrage der **Code** und nicht die Herkunft.
    """
    assert bc.MAPPING_STATUS["nibrs_auffang"] == "fallback_90Z"
    assert bc.AUFFANG_CODE == "90Z"


# --------------------------------------------------------------------------
# Das Fallebene: je Fall zaehlt eine Zeile, fuer beide Staedte nach derselben
# Regel.
#
# Chicago fuehrt je Vorfall ein Delikt - die einzigen Mehrfachzeilen sind
# Mordopfer, ein Datensatz je Opfer (25 Faelle in 2024). Detroit fuehrt je
# Vorfall jedes Delikt (4'658 Faelle mit 2-4 Taten). Auf Tatebene zaehlt
# Detroit damit 6,4 Prozent, die Chicago nie zaehlt. ``counts_case`` gleicht
# das an: die Zeile mit dem schwersten Delikt, bei gleichem Delikt die
# frueheste. Christian hat gefragt, ob das fuer beide Staedte gelten muesse -
# ja, sonst waere es die naechste Schieflage.
# --------------------------------------------------------------------------


def chi_zeile(nr: str, fall: str | None, datum: str, iucr: str = "0110") -> dict:
    return {"id": nr, "case_number": fall, "date": datum, "iucr": iucr,
            "description": "X", "latitude": IN_CHICAGO[0], "longitude": IN_CHICAGO[1],
            "updated_on": "2024-02-01T00:00:00.000"}


def fallebene(tmp_path, chicago, detroit, stadt) -> dict[str, tuple[bool, bool]]:
    """offense_id -> (counts, counts_case) fuer eine Stadt."""
    return {z["offense_id"]: (z["counts"], z["counts_case"])
            for z in lies(baue(tmp_path, chicago, detroit)) if z["city"] == stadt}


def test_chicagos_mordopfer_zaehlen_je_fall_einmal(tmp_path):
    """Zwei Opfer, ein Fall: beide Zeilen sind Taten, eine ist der Fall.

    Gewaehlt wird bei gleichem Delikt die frueheste Zeile - das zweite Opfer
    von JH100028 starb zwei Tage nach dem ersten.
    """
    chicago = [chi_zeile("2", "JH1", "2024-01-03T20:59:00.000"),
               chi_zeile("1", "JH1", "2024-01-01T00:56:00.000")]
    assert fallebene(tmp_path, chicago, DET, "chicago") == {
        "1": (True, True), "2": (True, False),
    }


def test_detroits_mehrere_taten_zaehlen_je_fall_einmal(tmp_path):
    """Einbruch plus Koerperverletzung: zwei Taten, ein Fall, das schwerere zaehlt."""
    detroit = [
        det_zeile("D1", "F1", "2307", "LARCENY - OTHER", "LARCENY - OTHER"),
        det_zeile("D2", "F1", "1302", "AGGRAVATED ASSAULT", "AGGRAVATED ASSAULT"),
    ]
    assert fallebene(tmp_path, CHI, detroit, "detroit") == {
        "D1": (True, False), "D2": (True, True),
    }


def test_die_rangfolge_ist_die_hierarchieregel(tmp_path):
    """13A vor 240 (beide in der Hierarchie), 240 vor 90Z (nicht darin)."""
    detroit = [
        det_zeile("D1", "F1", "2401", "MOTOR VEHICLE THEFT", "MOTOR VEHICLE THEFT"),
        det_zeile("D2", "F1", "2307", "LARCENY - OTHER", "LARCENY - OTHER"),
        det_zeile("D3", "F1", "1302", "AGGRAVATED ASSAULT", "AGGRAVATED ASSAULT"),
        det_zeile("D4", "F2", "2401", "MOTOR VEHICLE THEFT", "MOTOR VEHICLE THEFT"),
        det_zeile("D5", "F2", "2307", "LARCENY - OTHER", "LARCENY - OTHER"),
    ]
    ergebnis = fallebene(tmp_path, CHI, detroit, "detroit")
    assert [k for k, (_, fall) in ergebnis.items() if fall] == ["D3", "D4"]
    assert bc.FALLKORN_RANG[0] == "09A", "Toetung steht ganz oben"
    assert bc.FALLKORN_RANG.index("13A") < bc.FALLKORN_RANG.index("240")


def test_eine_anklage_die_nicht_zaehlt_zaehlt_auch_nicht_je_fall(tmp_path):
    """Artans Fall: die Larceny-Anklage zur CSC-Tat ist keine Tat - und kein Fall."""
    detroit = [
        det_zeile("D1", "F1", "2307", "LARCENY - OTHER", "CSC 3RD DEGREE"),
        det_zeile("D2", "F1", "1172", "CSC 3RD DEGREE", "CSC 3RD DEGREE"),
    ]
    assert fallebene(tmp_path, CHI, detroit, "detroit") == {
        "D1": (False, False), "D2": (True, True),
    }


def test_ohne_fallnummer_ist_die_zeile_ihr_eigener_fall(tmp_path):
    """Sonst fielen alle Zeilen ohne Nummer in einen Fall zusammen."""
    chicago = [chi_zeile("1", None, "2024-01-01T00:56:00.000"),
               chi_zeile("2", None, "2024-01-02T00:56:00.000")]
    assert fallebene(tmp_path, chicago, DET, "chicago") == {
        "1": (True, True), "2": (True, True),
    }


def test_das_fallebene_gilt_fuer_beide_staedte_gleich(tmp_path):
    """Dieselbe Regel, derselbe Code, beide Staedte: kein Sonderweg."""
    chicago = [chi_zeile("1", "JH1", "2024-01-01T00:56:00.000"),
               chi_zeile("2", "JH1", "2024-01-01T00:57:00.000")]
    detroit = [
        det_zeile("D1", "F1", "1302", "AGGRAVATED ASSAULT", "AGGRAVATED ASSAULT"),
        det_zeile("D2", "F1", "1302", "AGGRAVATED ASSAULT", "AGGRAVATED ASSAULT 2"),
    ]
    zeilen = lies(baue(tmp_path, chicago, detroit))
    je_stadt = {}
    for z in zeilen:
        je_stadt.setdefault(z["city"], []).append(z["counts_case"])
    assert je_stadt == {"chicago": [True, False], "detroit": [True, False]}


# --------------------------------------------------------------------------
# Die Herkunftskette (seit 14.9.2026)
#
# Zwei Glieder waren bis dahin nur Pfade: die Crosswalks und silver/tract.
# Ein Pfad zeigt aber auf das, was gerade dort liegt - wer eine Zahl erklaeren
# will, braucht, *was* dort stand. Artan hat danach gefragt.
# --------------------------------------------------------------------------


def test_die_crosswalks_tragen_ihre_pruefsumme(tmp_path):
    """Sie werden aus amtlichen PDFs erzeugt und koennen sich aendern, ohne
    dass der Pfad sich aendert."""
    herkunft = manifest_von(baue(tmp_path, CHI, DET))["derived_from"]
    assert len(herkunft["crosswalks"]) == 3
    for eintrag in herkunft["crosswalks"]:
        assert set(eintrag) == {"path", "sha256"}
        assert len(eintrag["sha256"]) == 64, "SHA-256 in hex"
    assert len({e["sha256"] for e in herkunft["crosswalks"]}) == 3


def test_silver_tract_wird_als_stand_genannt_nicht_als_pfad(tmp_path):
    """Der Bauzeitpunkt gehoert dazu: Wird tract neu gebaut, ruht
    crime_offense danach auf etwas anderem - der Pfad bliebe derselbe."""
    tract = manifest_von(baue(tmp_path, CHI, DET))["derived_from"]["silver_tract"]
    assert "path" in tract
    assert tract.get("built_at_utc"), "ohne Zeitpunkt ist es wieder nur ein Pfad"


def test_derselbe_eingabestand_traegt_denselben_abdruck(tmp_path):
    """Der Abdruck haengt an den Eingaben, nicht an der Uhrzeit des Baus."""
    erst = manifest_von(baue(tmp_path / "a", CHI, DET))
    zweit = manifest_von(baue(tmp_path / "b", CHI, DET))
    assert erst["input_fingerprint"] == zweit["input_fingerprint"]
    assert erst["built_at_utc"] != zweit["built_at_utc"]


def test_ein_zusaetzlicher_bronze_lauf_aendert_den_abdruck(tmp_path):
    """Sonst waere der Abdruck wertlos - er soll den Stand unterscheiden.

    Eine Zeile mehr im **selben** Lauf aendert ihn dagegen nicht: Der Abdruck
    steht fuer die Eingaben, und die sind derselbe Lauf. Wer wissen will, ob
    sich der Inhalt bewegt hat, sieht auf die Zeilenzahl.
    """
    data_root, config_root = tmp_path / "data", tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_detroit(data_root, DET)
    schreibe_config(config_root)
    vorher = manifest_von(bc.build(data_root, config_root))["input_fingerprint"]

    schreibe_chicago(data_root, CHI, run_id="run_20260202T000000000000Z",
                     ingest_date="2026-02-02")
    assert manifest_von(bc.build(data_root, config_root))["input_fingerprint"] != vorher


def test_ein_geaenderter_crosswalk_aendert_den_abdruck(tmp_path):
    """Der Grund fuer die Pruefsummen: Die Crosswalks werden aus amtlichen
    PDFs erzeugt. Aendert sich einer, ist es ein anderer Eingabestand -
    obwohl kein Bronze-Lauf dazugekommen ist und der Pfad derselbe bleibt."""
    data_root, config_root = tmp_path / "data", tmp_path / "config"
    schreibe_tract(data_root)
    schreibe_chicago(data_root, CHI)
    schreibe_detroit(data_root, DET)
    schreibe_config(config_root)
    vorher = manifest_von(bc.build(data_root, config_root))["input_fingerprint"]

    pfad = config_root / bc.IUCR_MAPPING
    pfad.write_text(pfad.read_text(encoding="utf-8") +
                    "1310,CRIMINAL DAMAGE,X,I,true,290,DESTRUCTION,nibrs_definition,true,\n",
                    encoding="utf-8")
    assert manifest_von(bc.build(data_root, config_root))["input_fingerprint"] != vorher


# --------------------------------------------------------------------------
# Die beiden Zeitzonen-Randfaelle (H3 aus dem Konzept)
# --------------------------------------------------------------------------


def test_die_beiden_zeitzonen_randfaelle_werden_erkannt():
    """H3 verlangt, dass sie ausdruecklich als Sonderfaelle ausgewiesen werden.

    Chicago liefert Wanduhrzeit **ohne Zone**. Zweimal im Jahr ist das nicht
    eindeutig: Beim Vorstellen der Uhr gibt es eine Stunde nicht, beim
    Zurueckstellen gibt es eine zweimal. Bis zum 16.9.2026 wurde beides
    stillschweigend umgerechnet; 48 Chicagoer Zeilen lagen in der doppelten
    Stunde, ohne dass es ihnen anzusehen war.

    Erkannt wird ohne Sonderwissen ueber Wechseldaten: Hin und zurueck
    gerechnet muss dieselbe Ortszeit herauskommen, sonst gab es sie nicht.
    Und fuehrt eine Stunde davor oder danach auf dieselbe Ortszeit, gab es
    sie zweimal.
    """
    con = duckdb.connect()
    try:
        con.execute("INSTALL icu")
        con.execute("LOAD icu")
        con.execute("SET TimeZone='UTC'")
        zone = bc.TIMEZONES[bc.CHICAGO]
        faelle = [
            ("gewoehnlich",    "2024-06-15 12:00:00", False, False),
            ("Mitternacht",    "2024-01-01 00:56:00", False, False),
            ("Jahresgrenze",   "2024-12-31 23:30:00", False, False),
            ("nicht existent", "2024-03-10 02:30:00", True,  False),
            ("doppelt",        "2024-11-03 01:30:00", False, True),
            ("knapp davor",    "2024-11-03 00:59:00", False, False),
            ("knapp danach",   "2024-11-03 02:00:00", False, False),
        ]
        for name, ortszeit, erwartet_nicht, erwartet_doppelt in faelle:
            nicht, doppelt = con.execute(f"""
                WITH x AS (SELECT CAST('{ortszeit}' AS TIMESTAMP) AS lokal),
                     y AS (SELECT lokal, timezone('{zone}', lokal) AS instant FROM x)
                SELECT CAST(timezone('{zone}', instant) AS TIMESTAMP) <> lokal,
                       CAST(timezone('{zone}', instant - INTERVAL 1 HOUR)
                            AS TIMESTAMP) = lokal
                    OR CAST(timezone('{zone}', instant + INTERVAL 1 HOUR)
                            AS TIMESTAMP) = lokal
                FROM y
            """).fetchone()
            assert (nicht, doppelt) == (erwartet_nicht, erwartet_doppelt), (
                f"{name} ({ortszeit}): erkannt als "
                f"nicht_existent={nicht}, doppelt={doppelt}"
            )
    finally:
        con.close()


def test_die_abfrage_liefert_beide_spalten():
    """Sie muessen in der Endauswahl stehen, nicht nur in einem CTE."""
    quelle = Path(bc.__file__).read_text(encoding="utf-8")
    for spalte in ("local_time_ambiguous", "local_time_nonexistent"):
        assert f"b.{spalte}" in quelle, (
            f"{spalte} fehlt in der Endauswahl der Silver-Abfrage"
        )
    assert "FALSE                                          AS local_time_nonexistent" in quelle, (
        "Detroit muss die Spalten fuehren, auch wenn sie dort immer falsch sind"
    )


def test_reconcile_zaehlt_die_randfaelle():
    """Der Docstring hat das behauptet, bevor es stimmte.

    Eine Zahl, die niemand gegen etwas haelt, ist keine Kontrolle - aber eine
    Zahl, die gar nicht erst entsteht, ist noch weniger.
    """
    quelle = Path(bc.__file__).read_text(encoding="utf-8")
    for spalte in ("local_time_ambiguous", "local_time_nonexistent"):
        assert f'"{spalte}":' in quelle, f"{spalte} fehlt in den checks"
        assert f"count(*) FILTER ({spalte})" in quelle, (
            f"{spalte} wird in reconcile nicht gezaehlt"
        )



# --------------------------------------------------------------------------
# Die Pruefungen aus Artans SQL-Sammlung (S03, S04, Z05, M03)
# --------------------------------------------------------------------------
# Artan hat am Wochenende 37 SQL-Abfragen gegen die gebauten Schichten
# geschrieben und im Branch ``sql_check_scripts`` abgelegt. Vier davon haben
# etwas gefunden, was der Bau nicht selbst prueft. Sie stehen seit dem
# 17.9.2026 hart in ``reconcile`` - eine Review-Abfrage laeuft, wenn jemand
# daran denkt, eine harte Pruefung laeuft immer.
#
# Geprueft wird hier nicht, dass die Zahlen heute null sind - das tut der Bau
# selbst. Geprueft wird, dass die Kontrolle **anschlaegt**, wenn sie es nicht
# mehr sind. Eine Kontrolle, die nie jemand hat fallen sehen, ist eine
# Vermutung.


ZEITZONE_SPALTE = (
    "CAST(timezone(CASE city WHEN 'chicago' THEN 'America/Chicago' "
    "ELSE 'America/Detroit' END, u AT TIME ZONE 'UTC') AS TIMESTAMP)"
)

# Eine Relation, die fuer sich gueltig ist: zwei Staedte, je ein Fall mit zwei
# Anklagen, davon eine zaehlend je Tat und je Fall. Die Quellcodes und ihre
# Zuordnungen sind dieselben, die ``schreibe_config`` in die Testcrosswalks
# schreibt - sonst koennte M03 unten nichts belegen.
GUELTIG = f"""
    WITH roh(city, offense_id, event_id, u, counts, counts_case,
             source_offense_code, nibrs_code, nibrs_match) AS (VALUES
        ('chicago', 'c1', 'F1', TIMESTAMP '2024-06-15 17:30:00', TRUE,  TRUE,
         '0110', '13A', 'nibrs_definition'),
        ('chicago', 'c2', 'F1', TIMESTAMP '2024-06-15 17:30:00', TRUE,  FALSE,
         '0910', '240', 'nibrs_definition'),
        ('detroit', 'd1', 'G1', TIMESTAMP '2024-06-15 16:00:00', TRUE,  TRUE,
         '2401', '240', 'micr_manual_1110_2024'),
        ('detroit', 'd2', 'G1', TIMESTAMP '2024-06-15 16:00:00', FALSE, FALSE,
         '2901', '90Z', 'micr_manual_1110_2024')
    )
    SELECT city, offense_id, event_id, u AS occurred_at_utc,
           {ZEITZONE_SPALTE} AS occurred_at_local,
           counts, counts_case, source_offense_code, nibrs_code, nibrs_match,
           TRUE AS nibrs_mapped, TRUE AS located,
           FALSE AS local_time_nonexistent, FALSE AS local_time_ambiguous
    FROM roh
"""

QUELLEN = (
    bc.Source(bc.CHICAGO, [], [], row_count=1000),
    bc.Source(bc.DETROIT, [], [], row_count=1000),
)


@pytest.fixture
def con():
    verbindung = duckdb.connect()
    verbindung.execute("INSTALL icu")
    verbindung.execute("LOAD icu")
    verbindung.execute("SET TimeZone='UTC'")
    try:
        yield verbindung
    finally:
        verbindung.close()


def pruefe(con, ersetzung: str = "") -> str | None:
    """``reconcile`` auf die gueltige Relation, wahlweise mit einer Verletzung.

    Gibt die Fehlermeldung zurueck, oder ``None``, wenn nichts beanstandet
    wurde. ``ersetzung`` ist ein REPLACE-Ausdruck von DuckDB und aendert genau
    eine Spalte genau einer Zeile.
    """
    auswahl = f"SELECT * {ersetzung} FROM ({GUELTIG})" if ersetzung else GUELTIG
    con.execute(f"CREATE OR REPLACE VIEW probe AS {auswahl}")
    try:
        bc.reconcile(con, "probe", *QUELLEN)
    except bc.TransformError as fehler:
        return " ".join(str(fehler).split())
    return None


def test_die_gueltige_relation_geht_durch(con):
    """Der Nullpunkt: Ohne ihn belegt kein einziger Fall darunter etwas."""
    assert pruefe(con) is None


def zaehlung(con, ersetzung: str = "") -> dict:
    """Die Zaehlungen je Stadt, ohne dass ein Abbruch erwartet wird."""
    auswahl = f"SELECT * {ersetzung} FROM ({GUELTIG})" if ersetzung else GUELTIG
    con.execute(f"CREATE OR REPLACE VIEW probe AS {auswahl}")
    return bc.reconcile(con, "probe", *QUELLEN)["per_city"]


def test_s03_eine_zeile_ohne_event_id_wird_gezaehlt_nicht_beanstandet(con):
    """Artans S03 - aber weich, und das ist der interessante Teil.

    Seine Sorge stimmt: ``count(DISTINCT event_id)`` ueberspringt NULL, und
    eine Auswertung je Vorfall verloere die Zeile stillschweigend. Nur trifft
    das nicht den Bau. ``event_id`` ist die **Fallnummer der Quelle**, und die
    darf fehlen; der Bau rechnet solche Zeilen ueber
    ``coalesce(event_id, offense_id)`` als ihren eigenen Fall - siehe
    ``test_ohne_fallnummer_ist_die_zeile_ihr_eigener_fall``.

    Haette S03 hart abgebrochen, waere ein Bestand unbaubar geworden, den der
    Entwurf ausdruecklich vorsieht. Die Zahl steht deshalb im Manifest und
    bricht nichts ab.
    """
    # Genommen wird ``d1``: die Zeile ist schon jetzt die zaehlende ihres
    # Falls. Ohne Fallnummer wird sie ihr eigener Fall - und bleibt es.
    # (Bei ``c2``, die zu einem fremden Fall gehoert, entstuende dagegen ein
    # zweiter Fall ohne markierte Zeile, und das beanstandet der Bau zu Recht.)
    je_stadt = zaehlung(con, "REPLACE (CASE WHEN offense_id = 'd1' THEN NULL "
                             "ELSE event_id END AS event_id)")
    assert je_stadt["detroit"]["ohne_event_id"] == 1
    assert je_stadt["chicago"]["ohne_event_id"] == 0


def test_s03_zaehlt_auch_leerraum_als_fehlend(con):
    """Eine leere Zeichenkette ist kein Vorfall, sie sieht nur aus wie einer."""
    je_stadt = zaehlung(con, "REPLACE (CASE WHEN offense_id = 'd1' THEN '   ' "
                             "ELSE event_id END AS event_id)")
    assert je_stadt["detroit"]["ohne_event_id"] == 1


def test_s03_ist_am_referenzstand_null(con):
    """Der Normalfall: Beide Quellen liefern durchgehend Fallnummern."""
    je_stadt = zaehlung(con)
    assert [z["ohne_event_id"] for z in je_stadt.values()] == [0, 0]


def test_s04_ein_fall_ohne_zaehlende_tat_bricht_ab(con):
    """Ein Fall besteht aus Taten; die Fallebene muss eine davon treffen.

    Artans S04. Waere eine Zeile je Fall markiert, die je Tat nicht zaehlt,
    lieferten die beiden Zaehlperspektiven Ergebnisse, die sich nicht mehr
    ineinander ueberfuehren lassen - ohne dass eine Summe auffaellig waere.
    """
    meldung = pruefe(con, "REPLACE (CASE WHEN offense_id = 'd2' THEN TRUE "
                          "ELSE counts_case END AS counts_case)")
    assert meldung and "1 Zeilen zaehlen als Fall, aber nicht als Tat" in meldung


def test_z05_eine_verschobene_ortszeit_bricht_ab(con):
    """Hin und zurueck gerechnet muss dieselbe Ortszeit herauskommen."""
    meldung = pruefe(con, "REPLACE (CASE WHEN offense_id = 'd1' "
                          "THEN occurred_at_local + INTERVAL 1 HOUR "
                          "ELSE occurred_at_local END AS occurred_at_local)")
    assert meldung and "nicht zur Ortszeit passt" in meldung


def test_z05_findet_die_falsche_stadtzeitzone(con):
    """Der Fall, fuer den die Pruefung eigentlich da ist.

    Eine einzelne verschobene Zeile ist ein Datenfehler; eine Stadt, die mit
    der Zone der anderen gerechnet wird, ist ein Codefehler - und der verschoebe
    jede Stundenverteilung, jede Nacht-Tag-Auswertung, jede Hypothese ueber
    Tageszeiten.
    """
    meldung = pruefe(con, "REPLACE (CASE WHEN city = 'detroit' "
                          "THEN CAST(timezone('America/Chicago', "
                          "occurred_at_utc AT TIME ZONE 'UTC') AS TIMESTAMP) "
                          "ELSE occurred_at_local END AS occurred_at_local)")
    assert meldung and "detroit" in meldung and "nicht zur Ortszeit passt" in meldung


def test_z05_nimmt_die_nicht_existente_ortszeit_aus(con):
    """Sonst schluege die Pruefung bei jedem Vorstellen der Uhr an.

    Eine Ortszeit, die es nicht gab, kann nicht zurueckgerechnet werden - das
    ist der dokumentierte Fall, den ``local_time_nonexistent`` traegt, und
    keine Unstimmigkeit.
    """
    con.execute(f"""
        CREATE OR REPLACE VIEW probe AS
        SELECT * REPLACE (
            TIMESTAMP '2024-03-10 02:30:00' AS occurred_at_local,
            TRUE AS local_time_nonexistent)
        FROM ({GUELTIG}) WHERE offense_id = 'c1'
        UNION ALL
        SELECT * FROM ({GUELTIG}) WHERE offense_id <> 'c1'
    """)
    bc.reconcile(con, "probe", *QUELLEN)  # bricht nicht ab


def test_m03_ein_geaenderter_crosswalk_wird_bemerkt(tmp_path, con):
    """Silver darf nicht etwas anderes behaupten als sein eigener Crosswalk.

    Artans M03. Der Bau wendet den Crosswalk als Join an und ist im Moment des
    Baus zwangslaeufig konsistent; die Luecke oeffnet sich erst danach. Wird
    die CSV geaendert und Silver nicht neu gebaut, driftet die Tabelle von
    ihrer Referenz weg - und das Manifest haelt zwar die Pruefsumme der CSV
    fest, aber niemand vergleicht sie mit der Datei auf der Platte.
    """
    config_root = tmp_path / "config"
    schreibe_config(config_root)
    con.execute(f"CREATE OR REPLACE VIEW probe AS {GUELTIG}")

    # Erst der Nullpunkt: Die Relation traegt genau das, was der Crosswalk
    # sagt. Ohne diesen Schritt belegt der zweite nichts.
    assert bc.gegen_crosswalk(con, "probe", config_root) == {"abweichungen": 0}

    pfad = config_root / bc.IUCR_MAPPING
    pfad.write_text(
        pfad.read_text(encoding="utf-8").replace(",13A,", ",09A,"),
        encoding="utf-8")
    with pytest.raises(bc.TransformError, match="weicht vom heutigen Crosswalk ab"):
        bc.gegen_crosswalk(con, "probe", config_root)


def test_m03_bemerkt_auch_eine_zurueckgezogene_zuordnung(tmp_path, con):
    """``mapped = false`` heisst: Die Zeile soll in Silver keinen Code tragen.

    Das ist der Fall, den ein Vergleich nur der Codes uebersieht - er findet
    dann auf beiden Seiten nichts und ist zufrieden.
    """
    config_root = tmp_path / "config"
    schreibe_config(config_root)
    con.execute(f"CREATE OR REPLACE VIEW probe AS {GUELTIG}")

    pfad = config_root / bc.MICR_MAPPING
    pfad.write_text(
        pfad.read_text(encoding="utf-8").replace(
            "2401,24001,MOTOR VEHICLE THEFT,A,240,Motor Vehicle Theft,7,"
            "micr_manual_1110_2024,true,",
            "2401,24001,MOTOR VEHICLE THEFT,A,240,Motor Vehicle Theft,7,"
            "micr_manual_1110_2024,false,"),
        encoding="utf-8")
    with pytest.raises(bc.TransformError, match="detroit"):
        bc.gegen_crosswalk(con, "probe", config_root)


def test_m03_laeuft_im_bau_mit(tmp_path):
    """Die Pruefung nuetzt nur, wenn ``build`` sie auch aufruft."""
    ziel = baue(tmp_path, CHI, DET)
    assert ziel.exists()
    quelle = Path(bc.__file__).read_text(encoding="utf-8")
    assert "reconcile(con, TABLE, chicago, detroit, config_root)" in quelle, (
        "build ruft reconcile ohne config_root auf - gegen_crosswalk liefe nie"
    )


# --------------------------------------------------------------------------
# Wie gebaut wird - nicht nur was herauskommt
# --------------------------------------------------------------------------
# Am 16.10.2026 starb dieser Bau auf ``srv01`` viermal an seiner
# Speichergrenze, zuletzt bei 1,4 GiB und mit "failed to pin block". Gemessen
# wurde dann: als **eine** Anweisung braucht dieselbe Abfrage 896 MB, in
# Stufen und mit der Datenbank auf einer Datei laeuft sie mit **256 MB**. Beide
# Haelften sind noetig; jede allein genuegt nicht. Diese Tests halten sie fest,
# denn der Unterschied ist an keinem Ergebnis zu sehen - nur an einem Abbruch
# auf einem Rechner, auf dem die Suite nicht laeuft.


def test_der_bau_fuehrt_die_stufen_einzeln_aus(monkeypatch, tmp_path):
    """Geprueft wird, **was ausgefuehrt wird**, nicht was ``build_query`` zurueckgibt.

    Die erste Fassung dieses Tests pruefte die Form des Rueckgabewerts. Eine
    Mutationsprobe, die die Stufen wieder zu einem ``WITH`` zusammensetzt,
    liess sie gruen - und genau das ist der Defekt, der 896 statt 256 MB
    kostet. Gezaehlt werden deshalb die ``CREATE TABLE``-Anweisungen.
    """
    anweisungen = []
    echt = bc.connect

    class Mitschrift:
        """Ein Stellvertreter, weil ``execute`` an der Verbindung nicht
        ueberschreibbar ist. Alles andere geht unveraendert durch."""

        def __init__(self, con):
            self._con = con

        def execute(self, sql, *rest, **kw):
            anweisungen.append(sql)
            return self._con.execute(sql, *rest, **kw)

        def __getattr__(self, name):
            return getattr(self._con, name)

    def merke(*args, **kwargs):
        return Mitschrift(echt(*args, **kwargs))

    monkeypatch.setattr(bc, "connect", merke)
    schreibe_chicago(tmp_path, CHI[:1])
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    bc.build(tmp_path, Path("config"))

    bauten = [s for s in anweisungen if s.lstrip().upper().startswith("CREATE TABLE")]
    assert len(bauten) > 10, (
        f"nur {len(bauten)} CREATE TABLE - die Stufen werden wieder in einer "
        f"Anweisung gebaut, und das kostet das Dreieinhalbfache an Speicher")
    mit_with = [s for s in bauten if " WITH " in s.upper()]
    assert not mit_with, (
        f"{len(mit_with)} Stufe(n) tragen eine WITH-Liste - dann ist jede "
        f"Zwischenstufe wieder gleichzeitig gepinnt")


def test_jede_tabelle_die_der_schluss_nennt_wird_vorher_gebaut():
    """Eine Umbenennung darf nicht erst beim Bau auffallen.

    Die Stufen heissen wie die CTEs, die sie ersetzt haben. Faellt eine weg
    oder wird sie umbenannt, bindet der Schluss nicht mehr - und zwar erst
    beim Lauf, nicht hier.
    """
    import re
    stufen, schluss = bc.build_query(
        bc.Source("chicago", ["a.parquet"], ["r1"], 1),
        bc.Source("detroit", ["b.parquet"], ["r2"], 1),
        bc.TractQuelle("t.parquet", "vintage=2024"),
        Path("config"),
    )
    namen = {name for name, _ in stufen}
    genannt = set(re.findall(r"(?:FROM|JOIN)\s+([a-z_]+)\s", schluss))
    fehlen = genannt - namen
    assert not fehlen, f"der Schluss liest {sorted(fehlen)}, gebaut wird das nicht"


def test_der_bau_legt_die_datenbank_auf_eine_datei(monkeypatch, tmp_path):
    """``:memory:`` *ist* der Speicher - ``temp_directory`` erreicht sie nicht.

    Geprueft wird, **womit** ``connect`` gerufen wird, nicht ob der Bau
    gelingt: Mit einer Speichergrenze von 256 MB gelingt er in beiden
    Fassungen, wenn die Testdaten klein genug sind. Der Unterschied zeigt sich
    erst bei 1,9 Mio. Zeilen, und die liegen nicht in der Suite.
    """
    gesehen = []
    echt = bc.connect

    def merke(*args, **kwargs):
        gesehen.append(kwargs.get("datenbank", ":memory:"))
        return echt(*args, **kwargs)

    monkeypatch.setattr(bc, "connect", merke)
    schreibe_chicago(tmp_path, CHI[:1])
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    bc.build(tmp_path, Path("config"))

    assert gesehen, "connect wurde nicht gerufen"
    assert gesehen[0] != ":memory:", (
        "der Bau laeuft gegen eine Datenbank im Arbeitsspeicher - dann liegen "
        "die gebaute Tabelle und jede Zwischenstufe darin, und kein "
        "Auslagerungsverzeichnis hilft")
    assert str(gesehen[0]).endswith(".duckdb")


def test_die_datenbankdatei_bleibt_nicht_liegen(monkeypatch, tmp_path):
    """Sie ist so gross wie die Tabelle; zwei Laeufe die Woche und der
    Datentraeger ist voll.

    ``DUCKDB_TEMP_DIRECTORY`` wird hier **gesetzt**, und das ist der Punkt:
    Die erste Fassung sah unter ``tmp_path`` nach, wo nie etwas lag - ohne die
    Variable legt der Bau sein Verzeichnis ins System-Temp. Eine
    Mutationsprobe, die ``mkdtemp`` ohne Aufraeumen benutzt, liess sie gruen.
    """
    ablage = tmp_path / "ddtmp"
    ablage.mkdir()
    monkeypatch.setenv("DUCKDB_TEMP_DIRECTORY", str(ablage))
    schreibe_chicago(tmp_path, CHI[:1])
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    bc.build(tmp_path, Path("config"))
    uebrig = list(ablage.iterdir())
    assert not uebrig, f"im Auslagerungsverzeichnis liegengeblieben: {uebrig}"


@pytest.mark.referenzstand
def test_die_gebaute_datei_steht_in_der_zugesagten_ordnung():
    """``ORDNUNG`` ist nur dann eine Zusage, wenn sie eindeutig ist.

    Waere der Schluessel nicht eindeutig, bliebe die Ordnung innerhalb der
    Gruppen offen - und damit haengen die Bytes wieder am Plan, obwohl im
    Quelltext eine Ordnung steht. Das ist der Fehler, der sich nicht ansehen
    laesst.
    """
    datei = Path("data/silver/dataset=crime_offense") / "part-0001.parquet"
    if not datei.is_file():
        pytest.skip("crime_offense nicht gebaut")
    con = duckdb.connect()
    try:
        spalten = ", ".join(bc.ORDNUNG.split(", "))
        zeilen, gruppen = con.execute(f"""
            SELECT count(*), count(DISTINCT ({spalten}))
            FROM read_parquet('{datei}')""").fetchone()
        assert zeilen == gruppen, (
            f"{zeilen - gruppen} Zeilen teilen ihren Ordnungsschluessel - "
            f"'{bc.ORDNUNG}' ist nicht eindeutig, die Bytes haengen wieder "
            f"am Abfrageplan")
        unsortiert = con.execute(f"""
            SELECT count(*) FROM (
                SELECT row_number() OVER () AS gelesen,
                       row_number() OVER (ORDER BY {bc.ORDNUNG}) AS erwartet
                FROM read_parquet('{datei}')
            ) WHERE gelesen <> erwartet""").fetchone()[0]
        assert unsortiert == 0, (
            f"{unsortiert} Zeilen stehen nicht in der Ordnung '{bc.ORDNUNG}' - "
            f"publish hat nicht sortiert")
    finally:
        con.close()


# --------------------------------------------------------------------------
# Zurueckgezogene Zeilen verschwinden
# --------------------------------------------------------------------------
# Am 17.10.2026 gemessen: 89 Chicago-Zeilen hatten ihren Jahrgang verlassen,
# und alle 89 standen weiter in ``crime_offense`` - 2026 allein 80. Die
# Entdoppelung nimmt je ``id`` die Fassung mit dem juengsten ``updated_on``;
# eine zurueckgezogene Zeile hat aber nur noch eine Fassung, die alte, und die
# gewinnt ohne Konkurrenten. Dabei schrieb ``silver/source_change`` das
# Verschwinden laengst auf: Zwei Tabellen derselben Schicht sagten
# Verschiedenes.


def voll(data_root, zeilen, *, jahr, zeit, run_id):
    return schreibe_chicago(
        data_root, zeilen, run_id=run_id, ingest_date=zeit[:10],
        mode="full_snapshot", event_year=jahr, started_at_utc=zeit)


def delta(data_root, zeilen, *, jahr, zeit, run_id):
    return schreibe_chicago(
        data_root, zeilen, run_id=run_id, ingest_date=zeit[:10],
        mode="delta", event_year=jahr, started_at_utc=zeit)


def zeile(id_, *, datum="2024-05-22T08:00:00", updated="2025-05-17T15:40:52"):
    return {"id": id_, "case_number": f"JF{id_}", "date": datum,
            "iucr": "0110", "primary_type": "HOMICIDE",
            "description": "FIRST DEGREE MURDER",
            "latitude": "41.88", "longitude": "-87.63", "updated_on": updated}


def ids_in_silver(data_root) -> set[str]:
    con = duckdb.connect()
    try:
        datei = bc.table_dir(data_root) / bc.PARQUET_FILE
        return {z[0] for z in con.execute(
            f"SELECT offense_id FROM read_parquet('{datei}')").fetchall()}
    finally:
        con.close()


def test_eine_zurueckgezogene_zeile_steht_nicht_mehr_in_silver(tmp_path):
    """Der gemessene Fall, klein nachgebaut."""
    voll(tmp_path, [zeile("A1"), zeile("WEG")],
         jahr=2024, zeit="2026-09-05T17:46:33", run_id="run_alt")
    voll(tmp_path, [zeile("A1")],
         jahr=2024, zeit="2026-10-03T09:30:47", run_id="run_neu")
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    bc.build(tmp_path, Path("config"))

    drin = ids_in_silver(tmp_path)
    assert "A1" in drin
    assert "WEG" not in drin, (
        "die Zeile fehlt im juengsten Vollabzug ihres Jahrgangs, die Quelle "
        "hat sie also zurueckgezogen - sie darf nicht aus dem ueberholten "
        "Schnappschuss ueberleben")


def test_eine_umdatierte_zeile_bleibt(tmp_path):
    """Umdatierung ist keine Loeschung - 5 der 89 gemessenen Faelle.

    Korrigiert die Quelle das Datum in ein anderes Jahr, verlaesst die Zeile
    das Fenster ihres alten Jahrgangs und erscheint im neuen. Weil die Regel
    je Jahrgang greift, kommt sie ueber den Vollabzug ihres neuen Jahrgangs
    herein. Genau deshalb steht in Detroits Manifest zu Recht
    ``captures_source_deletions: False``: *ein* Jahrgang allein kann die
    beiden Faelle nicht unterscheiden.
    """
    voll(tmp_path, [zeile("A1"), zeile("UM")],
         jahr=2024, zeit="2026-09-05T17:46:33", run_id="run_2024_alt")
    voll(tmp_path, [zeile("A1")],
         jahr=2024, zeit="2026-10-03T09:30:47", run_id="run_2024_neu")
    voll(tmp_path, [zeile("UM", datum="2023-08-08T00:01:00")],
         jahr=2023, zeit="2026-10-04T16:37:02", run_id="run_2023")
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    bc.build(tmp_path, Path("config"))

    drin = ids_in_silver(tmp_path)
    assert "UM" in drin, (
        "die Zeile ist nur umdatiert und steht im Vollabzug ihres neuen "
        "Jahrgangs - sie darf nicht als geloescht gelten")
    con = duckdb.connect()
    try:
        datum = con.execute(
            f"SELECT occurred_at_local FROM "
            f"read_parquet('{bc.table_dir(tmp_path) / bc.PARQUET_FILE}') "
            f"WHERE offense_id = 'UM'").fetchone()[0]
    finally:
        con.close()
    assert str(datum).startswith("2023-08-08"), \
        f"die alte Fassung hat gewonnen: {datum}"


def test_ein_delta_unter_dem_vollabzug_bringt_nichts_zurueck(tmp_path):
    """Die stille Variante desselben Fehlers.

    Ein Delta von **vor** dem juengsten Vollabzug ist in ihm schon enthalten -
    er ist ja vollstaendig. Es mitzulesen kann nur eines: eine Zeile
    zurueckbringen, die der Vollabzug nicht mehr hat.
    """
    voll(tmp_path, [zeile("A1")],
         jahr=2024, zeit="2026-09-05T17:46:33", run_id="run_voll_alt")
    delta(tmp_path, [zeile("WEG", updated="2026-09-06T10:00:00")],
          jahr=2024, zeit="2026-09-06T09:07:14", run_id="run_delta_alt")
    voll(tmp_path, [zeile("A1")],
         jahr=2024, zeit="2026-10-03T09:30:47", run_id="run_voll_neu")
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    bc.build(tmp_path, Path("config"))

    assert "WEG" not in ids_in_silver(tmp_path), (
        "ein Delta unter dem Vollabzug hat eine zurueckgezogene Zeile "
        "zurueckgebracht")


def test_ein_delta_ueber_dem_vollabzug_wird_gelesen(tmp_path):
    """Die Gegenprobe: Die Regel darf nicht einfach alles ausser dem
    Vollabzug wegwerfen - sonst fehlt, was seit ihm dazugekommen ist."""
    voll(tmp_path, [zeile("A1")],
         jahr=2024, zeit="2026-10-03T09:30:47", run_id="run_voll")
    delta(tmp_path, [zeile("NEU", updated="2026-10-04T10:00:00")],
          jahr=2024, zeit="2026-10-04T16:38:39", run_id="run_delta_neu")
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    bc.build(tmp_path, Path("config"))

    drin = ids_in_silver(tmp_path)
    assert {"A1", "NEU"} <= drin, f"nach dem Vollabzug fehlt etwas: {drin}"


def test_ein_jahrgang_ohne_vollabzug_behaelt_alle_laeufe(tmp_path, caplog):
    """Besser geht es dann nicht - aber still bleiben darf es nicht."""
    delta(tmp_path, [zeile("D1")],
          jahr=2025, zeit="2026-09-05T17:46:33", run_id="run_d1")
    delta(tmp_path, [zeile("D2")],
          jahr=2025, zeit="2026-09-06T09:07:14", run_id="run_d2")
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    with caplog.at_level("WARNING"):
        bc.build(tmp_path, Path("config"))

    assert {"D1", "D2"} <= ids_in_silver(tmp_path)
    assert any("kein Vollabzug" in s for s in caplog.messages), (
        "ohne Schnappschuss sind zurueckgezogene Zeilen nicht erkennbar - "
        "das gehoert gemeldet, nicht verschwiegen")


def test_jeder_jahrgang_wird_fuer_sich_beschnitten(tmp_path):
    """Ein neuer Vollabzug fuer 2024 darf 2023 nicht leeren."""
    voll(tmp_path, [zeile("C2023", datum="2023-05-22T08:00:00")],
         jahr=2023, zeit="2026-09-01T10:00:00", run_id="run_2023")
    voll(tmp_path, [zeile("C2024_alt"), zeile("C2024")],
         jahr=2024, zeit="2026-09-05T17:46:33", run_id="run_2024_alt")
    voll(tmp_path, [zeile("C2024")],
         jahr=2024, zeit="2026-10-03T09:30:47", run_id="run_2024_neu")
    schreibe_detroit(tmp_path, DET[:1])
    schreibe_tract(tmp_path)
    bc.build(tmp_path, Path("config"))

    drin = ids_in_silver(tmp_path)
    assert "C2023" in drin, "der aeltere Jahrgang wurde mitbeschnitten"
    assert "C2024" in drin
    assert "C2024_alt" not in drin


@pytest.mark.referenzstand
def test_was_source_change_als_verschwunden_fuehrt_ist_weg_oder_umdatiert():
    """Die beiden Tabellen derselben Schicht muessen dasselbe sagen.

    Das ist die Zusage, um die es geht - nicht eine Zahl, sondern
    Widerspruchsfreiheit. Vor dem 17.10.2026 fuehrte ``source_change`` fuenf
    Chicago-Zeilen als ``verschwunden``, und alle fuenf standen in
    ``crime_offense``. Eine Auswertung, die beide verbindet - *"zeige mir die
    verschwundenen Faelle"* -, fand Zeilen, die gleichzeitig weg und da waren.

    **``verschwunden`` heisst "weg aus diesem Jahrgang", nicht "weg aus der
    Quelle".** Korrigiert die Quelle ein Datum ins Nachbarjahr, verlaesst die
    Zeile das Fenster ihres Jahrgangs und erscheint im naechsten - genau das
    meint Detroits ``captures_source_deletions: False``. Eine solche Zeile
    *darf* in ``crime_offense`` stehen, aber nur mit einem **anderen** Jahr
    als dem, aus dem sie verschwand. Von den 89 am 17.10.2026 gemessenen
    Faellen waren 5 solche.

    Geprueft wird gegen den gebauten Bestand, deshalb der Marker.
    """
    datenwurzel = Path("data")
    fakt = datenwurzel / "silver" / "dataset=crime_offense" / bc.PARQUET_FILE
    wechsel = datenwurzel / "silver" / "dataset=source_change" / bc.PARQUET_FILE
    if not fakt.is_file() or not wechsel.is_file():
        pytest.skip("crime_offense oder source_change nicht gebaut")

    from storage import for_root

    # Lauf -> Jahrgang, aus den Bronze-Manifesten. Ohne diese Zuordnung laesst
    # sich eine Umdatierung nicht von einem Widerspruch unterscheiden.
    ablage = for_root(datenwurzel)
    jahr_je_lauf: dict[str, str] = {}
    for praefix, muster in (("bronze/city=chicago", "ingest_date=*/run_*/manifest.json"),
                            ("bronze/city=detroit", "**/run_*/manifest.json")):
        for lauf in ablage.laeufe(praefix, muster, streng=False):
            jahr_je_lauf[lauf.run_id] = lauf.jahrgang

    con = duckdb.connect()
    try:
        # Nur das juengste Paar je Stadt: Eine Zeile, die zwischen zwei alten
        # Laeufen verschwand und spaeter wieder auftauchte, ist heute da - und
        # das ist Geschichte, kein Widerspruch.
        weg = con.execute(f"""
            WITH juengste AS (
                SELECT city, max(beobachtet_am) AS stand
                FROM read_parquet('{wechsel}') GROUP BY 1
            )
            SELECT w.city, w.offense_id, w.run_id,
                   year(f.occurred_at_local) AS jahr_heute
            FROM read_parquet('{wechsel}') w
            JOIN juengste j ON w.city = j.city AND w.beobachtet_am = j.stand
            JOIN read_parquet('{fakt}') f
              ON f.city = w.city AND f.offense_id = w.offense_id
            WHERE w.art = 'verschwunden'""").fetchall()
    finally:
        con.close()

    widerspruch = [
        (stadt, kennung, jahr_je_lauf.get(lauf, "?"), jahr_heute)
        for stadt, kennung, lauf, jahr_heute in weg
        if str(jahr_heute) == jahr_je_lauf.get(lauf, "")
    ]
    assert not widerspruch, (
        f"source_change fuehrt diese Zeilen als verschwunden, und "
        f"crime_offense hat sie mit **demselben** Jahr - also keine "
        f"Umdatierung, sondern ein Widerspruch: {widerspruch}")
