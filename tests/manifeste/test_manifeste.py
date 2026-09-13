"""Tests fuer den gemeinsamen Manifest-Leser.

Was elf Stellen je fuer sich richtig oder falsch machten, steht hier einmal
als Zusage: versteckte Laeufe zaehlen nie, beide Statusvokabulare gelten, ein
kaputtes Manifest wirft die Ausnahme des Aufrufers - oder warnt, wenn der nur
inventarisiert.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import manifeste as mf


class EigenerFehler(RuntimeError):
    pass


def lauf(wurzel: Path, name: str, **felder) -> Path:
    d = wurzel / name
    d.mkdir(parents=True, exist_ok=True)
    (d / mf.MANIFEST).write_text(json.dumps(felder), encoding="utf-8")
    return d


# --------------------------------------------------------------------------
# fertige_laeufe
# --------------------------------------------------------------------------


def test_sortiert_nach_pfad_der_letzte_ist_der_juengste(tmp_path):
    lauf(tmp_path, "run_20260901T000000Z", status="complete")
    lauf(tmp_path, "run_20260903T000000Z", status="complete")
    lauf(tmp_path, "run_20260902T000000Z", status="complete")
    namen = [lf.verzeichnis.name for lf in mf.fertige_laeufe(tmp_path, "run_*/manifest.json")]
    assert namen == ["run_20260901T000000Z", "run_20260902T000000Z", "run_20260903T000000Z"]


def test_beide_vokabulare_gelten(tmp_path):
    """Acht Module schreiben complete, Detroit SUCCESS. Beide sind fertig."""
    lauf(tmp_path, "run_a", status="complete")
    lauf(tmp_path, "run_b", status="SUCCESS")
    lauf(tmp_path, "run_c", status="running")
    lauf(tmp_path, "run_d", status="failed")
    assert {lf.verzeichnis.name for lf in mf.fertige_laeufe(tmp_path, "run_*/manifest.json")} == {"run_a", "run_b"}


def test_versteckte_laeufe_zaehlen_nie(tmp_path):
    """Ein .part-Verzeichnis ist ein Lauf, der noch nicht veroeffentlicht ist."""
    lauf(tmp_path, "run_a", status="complete")
    lauf(tmp_path, ".run_b.part", status="complete")
    lauf(tmp_path / ".partial", "run_c", status="complete")
    assert [lf.verzeichnis.name for lf in mf.fertige_laeufe(tmp_path)] == ["run_a"]


def test_punkt_punkt_im_pfad_versteckt_nichts(tmp_path, monkeypatch):
    """Unter ``--data-root ../data`` fand der Leser stumm nichts - jeder
    Pfadteil, der mit einem Punkt beginnt, galt als ``.part``."""
    lauf(tmp_path, "run_a", status="complete")
    monkeypatch.chdir(tmp_path / "run_a")
    relativ = Path("..")
    assert not mf.versteckt(relativ / "run_a" / "manifest.json")
    assert [lf.verzeichnis.name for lf in mf.fertige_laeufe(relativ)] == ["run_a"]


def test_kaputtes_manifest_wirft_die_ausnahme_des_aufrufers(tmp_path):
    """Die Ingestion sagt IngestionError, Silver TransformError - ihre Tests haengen daran."""
    d = tmp_path / "run_a"
    d.mkdir()
    (d / mf.MANIFEST).write_text("{kein json", encoding="utf-8")
    with pytest.raises(EigenerFehler, match="Invalid manifest"):
        mf.fertige_laeufe(tmp_path, "run_*/manifest.json", fehler=EigenerFehler)


def test_kaputtes_manifest_wird_beim_inventarisieren_uebersprungen(tmp_path):
    lauf(tmp_path, "run_a", status="complete")
    d = tmp_path / "run_b"
    d.mkdir()
    (d / mf.MANIFEST).write_text("{kein json", encoding="utf-8")
    assert [lf.verzeichnis.name for lf in mf.fertige_laeufe(tmp_path, streng=False)] == ["run_a"]


def test_fehlende_wurzel_ist_leer_nicht_rot(tmp_path):
    assert mf.fertige_laeufe(tmp_path / "gibt_es_nicht") == []


def test_das_muster_grenzt_ein(tmp_path):
    lauf(tmp_path / "ingest_date=2026-09-01", "run_a", status="complete")
    lauf(tmp_path / "anderswo", "run_b", status="complete")
    treffer = mf.fertige_laeufe(tmp_path, "ingest_date=*/run_*/manifest.json")
    assert [lf.verzeichnis.name for lf in treffer] == ["run_a"]


# --------------------------------------------------------------------------
# Lauf - die Schluessel, die je Quelle anders heissen
# --------------------------------------------------------------------------


def test_run_id_kennt_beide_namen(tmp_path):
    a = lauf(tmp_path, "run_a", status="complete", run_id="X")
    b = lauf(tmp_path, "run_b", status="SUCCESS", pipeline_run_id="Y")
    c = lauf(tmp_path, "run_c", status="complete")
    ids = {lf.verzeichnis.name: lf.run_id for lf in mf.fertige_laeufe(tmp_path)}
    assert ids == {"run_a": "X", "run_b": "Y", "run_c": "run_c"}
    assert a.exists() and b.exists() and c.exists()


def test_abgeschlossen_um_kennt_beide_namen(tmp_path):
    lauf(tmp_path, "run_a", status="complete", completed_at_utc="2026-09-01T00:00:00")
    lauf(tmp_path, "run_b", status="SUCCESS", finished_at="2026-09-02T00:00:00")
    wann = {lf.verzeichnis.name: lf.abgeschlossen_um for lf in mf.fertige_laeufe(tmp_path)}
    assert wann == {"run_a": "2026-09-01T00:00:00", "run_b": "2026-09-02T00:00:00"}


def test_zeilen_kennt_beide_namen(tmp_path):
    lauf(tmp_path, "run_a", status="complete", row_count=5)
    lauf(tmp_path, "run_b", status="SUCCESS", downloaded_count=7)
    assert {lf.verzeichnis.name: lf.zeilen for lf in mf.fertige_laeufe(tmp_path)} == {"run_a": 5, "run_b": 7}


def test_die_datei_kommt_aus_dem_manifest_oder_der_vorgabe(tmp_path):
    lauf(tmp_path, "run_a", status="complete")
    lauf(tmp_path, "run_b", status="SUCCESS", bronze_file="teil.parquet")
    dateien = {lf.verzeichnis.name: lf.datei().name for lf in mf.fertige_laeufe(tmp_path)}
    assert dateien == {"run_a": "part-0001.parquet", "run_b": "teil.parquet"}


# --------------------------------------------------------------------------
# tabellen
# --------------------------------------------------------------------------


def test_tabellen_findet_flach_und_unter_vintage(tmp_path):
    lauf(tmp_path / "silver", "dataset=crime_offense", status="complete", row_count=3)
    lauf(tmp_path / "silver" / "dataset=tract", "vintage=2024", status="complete", row_count=2)
    lauf(tmp_path / "gold", "dataset=fact_offense", status="complete", row_count=1)
    t = mf.tabellen(tmp_path)
    assert [(x.schicht, x.name, x.zeilen) for x in t] == [
        ("gold", "fact_offense", 1), ("silver", "crime_offense", 3), ("silver", "tract", 2),
    ]


def test_tabellen_ueberspringt_versteckte(tmp_path):
    lauf(tmp_path / "silver", "dataset=a", status="complete")
    lauf(tmp_path / "silver", ".dataset=b.part", status="complete")
    assert [x.name for x in mf.tabellen(tmp_path)] == ["a"]


def test_tabellen_ohne_schicht_ist_leer(tmp_path):
    assert mf.tabellen(tmp_path) == []
