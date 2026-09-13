"""Tests fuer die Aufbewahrungsregel.

Die Regel ist klein, aber jede ihrer vier Zeilen schuetzt etwas, das man
nicht zurueckholen kann: einen Lauf. Deshalb steht jede Zeile als eigener
Test da, und dazu die Zusage, die ueber allen steht - **ohne ``--loeschen``
passiert nichts.**
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import aufraeumen as au


def lauf(data_root: Path, quelle: str, name: str, *, wann: str,
         teile: tuple[str, ...] = ("",), status: str = "complete",
         mode: str | None = None, raw: bool = True, detroit: bool = False,
         zeilen: int = 10) -> None:
    """Ein Bronze-Lauf mit Raw-Gegenstueck, in einem oder mehreren Teilen."""
    for teil in teile:
        relativ = Path(quelle) / teil / name
        for schicht in ("bronze",) + (("raw",) if raw else ()):
            ordner = data_root / schicht / relativ
            ordner.mkdir(parents=True)
            (ordner / "part-0001.parquet").write_bytes(b"x" * 1000)
            if detroit:
                manifest = {"status": "SUCCESS", "pipeline_run_id": name.removeprefix("run_"),
                            "finished_at": wann, "downloaded_count": zeilen,
                            "extraction_mode": mode or "FULL"}
            else:
                manifest = {"status": status, "run_id": name,
                            "completed_at_utc": wann, "row_count": zeilen}
                if mode:
                    manifest["mode"] = mode
            (ordner / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def silver(data_root: Path, name: str, derived_from) -> None:
    ordner = data_root / "silver" / f"dataset={name}"
    ordner.mkdir(parents=True)
    (ordner / "manifest.json").write_text(
        json.dumps({"status": "complete", "derived_from": derived_from}), encoding="utf-8"
    )


def gruende(data_root: Path, quelle: str) -> dict[str, str | None]:
    return {e.bestand.run_id: e.grund for e in au.bericht(data_root)
            if e.bestand.quelle == quelle}


# --------------------------------------------------------------------------
# Die vier Zeilen der Regel
# --------------------------------------------------------------------------


def test_der_juengste_und_der_davor_bleiben_der_dritte_nicht(tmp_path):
    for i in (1, 2, 3):
        lauf(tmp_path, "dataset=noaa_ghcnd", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00")
    assert gruende(tmp_path, "dataset=noaa_ghcnd") == {
        "run_03": au.JUENGSTER, "run_02": au.VORHERIGER, "run_01": None,
    }


@pytest.mark.parametrize("derived_from", [
    {"chicago_bronze_runs": ["run_01"], "detroit_bronze_runs": []},   # crime_offense
    [{"layer": "bronze", "dataset": "x", "run_id": "run_01"}],         # die uebrigen
])
def test_was_silver_nennt_bleibt_auch_wenn_es_alt_ist(tmp_path, derived_from):
    for i in (1, 2, 3):
        lauf(tmp_path, "city=chicago", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00")
    silver(tmp_path, "irgendwas", derived_from)
    assert gruende(tmp_path, "city=chicago")["run_01"] == au.GENANNT


def test_ein_delta_haelt_seine_basis_fest(tmp_path):
    """Chicago: zwei Deltas auf einem vollen Schnappschuss. Der Schnappschuss
    ist der dritte Lauf - nach Zeile 1 entbehrlich, nach Zeile 3 nicht."""
    lauf(tmp_path, "city=chicago", "run_01", wann="2026-09-01T10:00:00", mode="full_snapshot")
    lauf(tmp_path, "city=chicago", "run_02", wann="2026-09-02T10:00:00", mode="full_snapshot")
    lauf(tmp_path, "city=chicago", "run_03", wann="2026-09-03T10:00:00", mode="delta")
    lauf(tmp_path, "city=chicago", "run_04", wann="2026-09-04T10:00:00", mode="delta")
    assert gruende(tmp_path, "city=chicago") == {
        "run_04": au.JUENGSTER, "run_03": au.VORHERIGER,
        "run_02": au.BASIS, "run_01": None,
    }


def test_ein_delta_das_geht_braucht_keine_basis(tmp_path):
    """Nach zwei neuen vollen Laeufen ist ein altes Delta samt Basis entbehrlich."""
    lauf(tmp_path, "city=chicago", "run_01", wann="2026-09-01T10:00:00", mode="full_snapshot")
    lauf(tmp_path, "city=chicago", "run_02", wann="2026-09-02T10:00:00", mode="delta")
    lauf(tmp_path, "city=chicago", "run_03", wann="2026-09-03T10:00:00", mode="full_snapshot")
    lauf(tmp_path, "city=chicago", "run_04", wann="2026-09-04T10:00:00", mode="full_snapshot")
    g = gruende(tmp_path, "city=chicago")
    assert g["run_02"] is None and g["run_01"] is None


def test_ohne_loeschen_bleibt_alles(tmp_path, monkeypatch, capsys):
    """Die Zusage ueber allen anderen."""
    for i in (1, 2, 3):
        lauf(tmp_path, "dataset=noaa_ghcnd", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00")
    vorher = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--data-root", str(tmp_path)])
    assert au.main() == 0
    assert sorted(p for p in tmp_path.rglob("*") if p.is_file()) == vorher
    out = capsys.readouterr().out
    assert "ENTBEHRLICH" in out and "Nichts geloescht" in out


# --------------------------------------------------------------------------
# Was ein Lauf ist
# --------------------------------------------------------------------------


def test_ein_lauf_ueber_zwei_partitionen_ist_ein_lauf(tmp_path):
    """ACS: state=17 und state=26 tragen dieselbe run_id."""
    for i in (1, 2, 3):
        lauf(tmp_path, "dataset=acs5_tract", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00",
             teile=("vintage=2024/state=17", "vintage=2024/state=26"))
    laeufe = au.bestaende(tmp_path)["dataset=acs5_tract"]
    assert [b.run_id for b in laeufe] == ["run_03", "run_02", "run_01"]
    assert all(len(b.bronze) == 2 and len(b.raw) == 2 for b in laeufe)
    assert laeufe[0].zeilen == 20


def test_detroits_vokabular_wird_verstanden(tmp_path):
    """SUCCESS, pipeline_run_id, finished_at - und Silver nennt die nackte UUID."""
    for i in (1, 2, 3):
        lauf(tmp_path, "city=detroit", f"run_uuid-0{i}", wann=f"2026-09-1{i}T10:00:00",
             teile=("full/year=2024",), detroit=True)
    silver(tmp_path, "crime_offense", {"detroit_bronze_runs": ["uuid-01"]})
    assert gruende(tmp_path, "city=detroit") == {
        "uuid-03": au.JUENGSTER, "uuid-02": au.VORHERIGER, "uuid-01": au.GENANNT,
    }


def test_ein_lauf_ohne_raw_wird_gemeldet(tmp_path, capsys):
    lauf(tmp_path, "city=detroit", "run_uuid-01", wann="2026-09-11T10:00:00",
         teile=("full/year=2024",), detroit=True, raw=False)
    (alleine,) = au.bestaende(tmp_path)["city=detroit"]
    assert alleine.ohne_raw
    au.zeige(au.bericht(tmp_path))
    assert "ohne Raw" in capsys.readouterr().out


def test_nicht_fertige_laeufe_zaehlen_nicht(tmp_path):
    lauf(tmp_path, "dataset=noaa_ghcnd", "run_01", wann="2026-09-01T10:00:00")
    lauf(tmp_path, "dataset=noaa_ghcnd", "run_02", wann="2026-09-02T10:00:00", status="failed")
    assert [b.run_id for b in au.bestaende(tmp_path)["dataset=noaa_ghcnd"]] == ["run_01"]


# --------------------------------------------------------------------------
# Loeschen
# --------------------------------------------------------------------------


def test_loeschen_nimmt_raw_und_bronze_zusammen_und_laesst_den_rest(tmp_path, monkeypatch):
    for i in (1, 2, 3):
        lauf(tmp_path, "city=chicago", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00",
             teile=(f"ingest_date=2026-09-0{i}",))
    lauf(tmp_path, "dataset=noaa_ghcnd", "run_09", wann="2026-09-09T10:00:00", status="failed")
    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--data-root", str(tmp_path), "--loeschen"])
    assert au.main() == 0

    for schicht in ("bronze", "raw"):
        assert not (tmp_path / schicht / "city=chicago" / "ingest_date=2026-09-01").exists(), (
            "der leere Partitionsordner sollte mitgehen"
        )
        assert (tmp_path / schicht / "city=chicago" / "ingest_date=2026-09-02" / "run_02").is_dir()
        assert (tmp_path / schicht / "city=chicago" / "ingest_date=2026-09-03" / "run_03").is_dir()
        assert (tmp_path / schicht / "city=chicago").is_dir(), "die Quelle selbst bleibt"
        # Ein nicht fertiger Lauf ist nicht entbehrlich - er ist gar nichts.
        # Angefasst wird er nicht.
        assert (tmp_path / schicht / "dataset=noaa_ghcnd" / "run_09").is_dir()


def test_loesche_ueberspringt_was_bleibt(tmp_path):
    lauf(tmp_path, "dataset=noaa_ghcnd", "run_01", wann="2026-09-01T10:00:00")
    alle = au.bericht(tmp_path)
    assert au.loesche(alle, tmp_path) == []
    assert (tmp_path / "bronze" / "dataset=noaa_ghcnd" / "run_01").is_dir()
