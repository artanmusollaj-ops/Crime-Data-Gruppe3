"""Tests fuer die Aufbewahrungsregel.

Die Regel ist klein, aber jede ihrer vier Zeilen schuetzt etwas, das man
nicht zurueckholen kann: einen Lauf. Deshalb steht jede Zeile als eigener
Test da, und dazu die Zusage, die ueber allen steht - **ohne ``--loeschen``
passiert nichts.**
"""

from __future__ import annotations

import json
import sys
from datetime import date
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


def test_auch_detroits_delta_haelt_seine_basis_fest(tmp_path):
    """Seit dem 18.9.2026 laedt Detroit ebenso - und heisst den Modus anders.

    Detroit schreibt ``extraction_mode: DELTA``, Chicago ``mode: delta``. Faellt
    dieser Test, haelt die Regel eine Stadt fuer eine Folge von Vollbestaenden,
    die keine mehr ist: Ein geloeschter Vollschnappschuss macht jedes Delta
    darueber wertlos.
    """
    lauf(tmp_path, "city=detroit", "run_uuid-01", wann="2026-09-01T10:00:00",
         teile=("full/year=2024",), detroit=True, mode="FULL")
    lauf(tmp_path, "city=detroit", "run_uuid-02", wann="2026-09-02T10:00:00",
         teile=("full/year=2024",), detroit=True, mode="FULL")
    lauf(tmp_path, "city=detroit", "run_uuid-03", wann="2026-09-03T10:00:00",
         teile=("full/year=2024",), detroit=True, mode="DELTA")
    lauf(tmp_path, "city=detroit", "run_uuid-04", wann="2026-09-04T10:00:00",
         teile=("full/year=2024",), detroit=True, mode="DELTA")
    assert gruende(tmp_path, "city=detroit") == {
        "uuid-04": au.JUENGSTER, "uuid-03": au.VORHERIGER,
        "uuid-02": au.BASIS, "uuid-01": None,
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


# --------------------------------------------------------------------------
# Regel 0: Gepinnt bleibt (seit 14.9.2026)
#
# Die drei anderen Regeln stehen der Historisierung im Weg: Regel 2 haelt nur,
# was das *aktuelle* Silver nennt. Nach einem Neubau werden die Laeufe des
# vorigen Stands entbehrlich - und eine veroeffentlichte Zahl von letzter
# Woche waere nicht mehr nachzubauen. Artans Punkt 1, Stufe B.
# --------------------------------------------------------------------------


def register(config_root: Path, *kennungen: str, grund: str = "LN1") -> None:
    config_root.mkdir(parents=True, exist_ok=True)
    zeilen = ["run_id,quelle,grund,seit"]
    zeilen += [f"{k},city=chicago,{grund},2026-09-14" for k in kennungen]
    (config_root / au.REFERENZSTAND_DATEI).write_text(
        "\n".join(zeilen) + "\n", encoding="utf-8")


def test_ein_gepinnter_lauf_ueberlebt_das_aufraeumen(tmp_path):
    """Der aelteste Lauf waere entbehrlich - gepinnt bleibt er."""
    for i in (1, 2, 3):
        lauf(tmp_path, "dataset=noaa_ghcnd", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00")
    config = tmp_path / "config"
    register(config, "run_01")
    gruende = {e.bestand.run_id: e.grund for e in au.bericht(tmp_path, config)}
    assert gruende["run_01"] == au.GEPINNT
    assert all(e.bleibt for e in au.bericht(tmp_path, config))


def test_ohne_register_bleibt_alles_wie_bisher(tmp_path):
    for i in (1, 2, 3):
        lauf(tmp_path, "dataset=noaa_ghcnd", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00")
    assert gruende(tmp_path, "dataset=noaa_ghcnd")["run_01"] is None


def test_ein_gepinnter_lauf_wird_nicht_geloescht(tmp_path, monkeypatch):
    for i in (1, 2, 3):
        lauf(tmp_path, "city=chicago", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00",
             teile=(f"ingest_date=2026-09-0{i}",))
    config = tmp_path / "config"
    register(config, "run_01")
    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--data-root", str(tmp_path),
                                      "--config-root", str(config), "--loeschen"])
    assert au.main() == 0
    assert (tmp_path / "bronze" / "city=chicago" / "ingest_date=2026-09-01" / "run_01").is_dir()


def test_detroits_nackte_uuid_wird_erkannt(tmp_path):
    """Silver nennt Detroit ohne das Praefix - das Register auch."""
    lauf(tmp_path, "city=detroit", "run_uuid-01", wann="2026-09-11T10:00:00",
         teile=("full/year=2024",), detroit=True)
    lauf(tmp_path, "city=detroit", "run_uuid-02", wann="2026-09-12T10:00:00",
         teile=("full/year=2024",), detroit=True)
    lauf(tmp_path, "city=detroit", "run_uuid-03", wann="2026-09-13T10:00:00",
         teile=("full/year=2024",), detroit=True)
    config = tmp_path / "config"
    register(config, "uuid-01")
    gruende_ = {e.bestand.run_id: e.grund for e in au.bericht(tmp_path, config)}
    assert gruende_["uuid-01"] == au.GEPINNT


# --------------------------------------------------------------------------
# Pinnen: abgeleitet, nicht getippt
# --------------------------------------------------------------------------


def gold(data_root: Path, derived_from) -> None:
    ordner = data_root / "gold" / "dataset=fact_offense"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "manifest.json").write_text(
        json.dumps({"status": "complete", "derived_from": derived_from}), encoding="utf-8")


def test_gepinnt_wird_woran_gold_haengt(tmp_path):
    """Der Ertrag der geschlossenen Herkunftskette: Ein Gold-Manifest nennt
    seine Silver-Quelle samt deren Herkunft - darin stehen die Bronze-Laeufe.
    Der Referenzstand wird daraus **abgeleitet**, nicht getippt."""
    for i in (1, 2):
        lauf(tmp_path, "city=chicago", f"run_0{i}", wann=f"2026-09-0{i}T10:00:00",
             teile=(f"ingest_date=2026-09-0{i}",))
    gold(tmp_path, [{"layer": "silver", "table": "crime_offense",
                     "derived_from": {"chicago_bronze_runs": ["run_01"]}}])
    config = tmp_path / "config"
    assert au.pinne(tmp_path, config, "LN1", jetzt=date(2026, 9, 14)) == ["run_01"]

    inhalt = (config / au.REFERENZSTAND_DATEI).read_text(encoding="utf-8")
    assert inhalt.splitlines()[0] == "run_id,quelle,grund,seit"
    assert "run_01,city=chicago,LN1,2026-09-14" in inhalt
    assert "run_02" not in inhalt, "Gold ruht nicht darauf"


def test_zweimal_pinnen_schreibt_nicht_doppelt(tmp_path):
    lauf(tmp_path, "city=chicago", "run_01", wann="2026-09-01T10:00:00")
    gold(tmp_path, [{"derived_from": {"chicago_bronze_runs": ["run_01"]}}])
    config = tmp_path / "config"
    assert au.pinne(tmp_path, config, "LN1") == ["run_01"]
    assert au.pinne(tmp_path, config, "LN2") == []
    inhalt = (config / au.REFERENZSTAND_DATEI).read_text(encoding="utf-8")
    assert inhalt.count("run_01") == 1 and "LN2" not in inhalt


def test_gepinnt_wird_nur_was_es_gibt(tmp_path):
    """Ein Manifest kann eine Kennung nennen, deren Lauf laengst weg ist."""
    lauf(tmp_path, "city=chicago", "run_01", wann="2026-09-01T10:00:00")
    gold(tmp_path, [{"derived_from": {"chicago_bronze_runs": ["run_01", "run_weg"]}}])
    assert au.pinne(tmp_path, tmp_path / "config", "LN1") == ["run_01"]
