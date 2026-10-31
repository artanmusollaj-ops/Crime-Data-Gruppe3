"""E-5: echte Prozesssperren, Abbruch und Herkunft statt nur Marker-Existenz."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from storage.analysesitzung import (
    AnalyseFehler, bestaetige, datensperre, schreibzugriff,
)

from orchestration.analyse import Analysesitzung

PROJECT = Path(__file__).resolve().parents[2]


def child(root, code, *, inherit=False):
    env = dict(os.environ, PYTHONPATH=str(PROJECT / "src" / "crime"))
    if not inherit:
        env.pop("CRIME_DATA_LOCKS", None)
    return subprocess.run([sys.executable, "-c", code, str(root)], env=env,
                          capture_output=True, text=True, timeout=20)


@pytest.fixture
def bestand(tmp_path):
    from gold_pipeline import TABELLEN

    paths = [f"gold/dataset={name}/part-0001.parquet" for name in TABELLEN]
    paths += ["silver/dataset=crime_offense/part-0001.parquet",
              "silver/dataset=source_change/part-0001.parquet",
              "silver/dataset=tract/vintage=2024/part-0001.parquet",
              "silver/dataset=place/vintage=2024/part-0001.parquet",
              "bronze/city=chicago/run=a/manifest.json"]
    # Hash-/Vollstaendigkeitspruefung; fachliche Parquet-Pruefung bleibt bei der Pipeline.
    for rel in paths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'{"run_id":"bronze-a"}' if p.suffix == ".json" else b"PAR1test")
    with schreibzugriff(tmp_path):
        bestaetige(tmp_path, run_id="build-a", projekt_root=PROJECT, release_id="candidate-a")
    return tmp_path


@pytest.mark.parametrize("schreiben", [False, True])
def test_ein_anderer_prozess_kommt_nicht_an_den_bestand(tmp_path, schreiben):
    with datensperre(tmp_path, schreiben=schreiben):
        result = child(tmp_path, """
import sys
from storage.analysesitzung import datensperre
with datensperre(sys.argv[1], schreiben=True):
    raise AssertionError('Sperre umgangen')
""")
        assert result.returncode != 0
        assert "Datenbestand belegt" in result.stderr
    with datensperre(tmp_path):
        pass


def test_kindpipeline_darf_unter_elternsperre_schreiben(tmp_path):
    with schreibzugriff(tmp_path):
        result = child(tmp_path, """
import sys
from storage.analysesitzung import schreibzugriff
with schreibzugriff(sys.argv[1]):
    print('Kindpipeline erlaubt')
""", inherit=True)
        assert result.returncode == 0, result.stderr


def test_prozessabbruch_gibt_die_os_sperre_frei(tmp_path):
    result = child(tmp_path, """
import os, sys
from storage.analysesitzung import datensperre
with datensperre(sys.argv[1], schreiben=True):
    os._exit(0)
""")
    assert result.returncode == 0, result.stderr
    with datensperre(tmp_path):
        pass


@pytest.mark.parametrize("notebook", ["34", "37"])
def test_sitzung_zeigt_den_belegten_aufbau_und_gibt_frei(bestand, notebook):
    with Analysesitzung(bestand, notebook) as session:
        assert session.herkunft["run_id"] == "build-a"
        assert session.herkunft["release_id"] == "candidate-a"
        with pytest.raises(AnalyseFehler, match="belegt"):
            with datensperre(bestand, schreiben=True):
                pass
    with schreibzugriff(bestand):
        pass


def test_fehlerhafter_schreiber_entwertet_alten_erfolg(bestand):
    with pytest.raises(ValueError):
        with schreibzugriff(bestand):
            raise ValueError("Abbruch beim Neubau")
    with pytest.raises(AnalyseFehler, match="Kein bestaetigter Aufbau"):
        Analysesitzung(bestand, "34")
    with datensperre(bestand):
        pass


@pytest.mark.parametrize("change", ["entfernt", "veraendert", "hinzugefuegt"])
def test_abweichende_dateien_werden_abgewiesen(bestand, change):
    p = bestand / "silver/dataset=crime_offense/part-0001.parquet"
    if change == "entfernt":
        p.unlink()
    elif change == "veraendert":
        p.write_bytes(b"veraendert")
    else:
        (p.parent / "part-0002.parquet").write_bytes(b"neu")
    with pytest.raises(AnalyseFehler, match="veraendert"):
        Analysesitzung(bestand, "34")


def test_silver_lauf_bestaetigt_kein_altes_gold(bestand):
    with schreibzugriff(bestand):
        bestaetige(bestand, run_id="silver-only", projekt_root=PROJECT, bereiche=["silver"])
    with pytest.raises(AnalyseFehler, match="Schichten"):
        Analysesitzung(bestand, "34")
    with Analysesitzung(bestand, "37"):
        pass


def test_ende_schliesst_verbindungen_und_weitere_verbinde_scheitert(bestand):
    session = Analysesitzung(bestand, "37")
    con = session.verbinde()
    assert con.execute("select 42").fetchone() == (42,)
    session.beenden()
    session.beenden()
    with pytest.raises(AnalyseFehler, match="beendet"):
        session.verbinde()
    with pytest.raises(Exception, match="closed"):
        con.execute("select 42")


def test_worker_laesst_queue_bei_belegtem_bestand_unberuehrt(bestand, monkeypatch):
    from platform_admin import operations

    def unexpected(_):
        pytest.fail("Queue trotz Analysesitzung betreten")

    monkeypatch.setattr(operations, "_tick", unexpected)
    with Analysesitzung(bestand, "37"):
        assert operations.tick(SimpleNamespace(data=bestand))["status"] == "BLOCKED"


def test_notebooks_sind_syntaktisch_gueltig_und_beenden_sitzung():
    for name in ("34_gold_sternschema", "37_quellbewegung"):
        nb = json.loads((PROJECT / "notebooks" / (name + ".ipynb")).read_text(encoding="utf-8"))
        cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
        for cell in cells:
            compile(cell, name, "exec")
        assert "Analysesitzung(DATA_ROOT" in cells[0]
        assert cells[-1] == "analyse.beenden()"


@pytest.mark.parametrize("name", ["34_gold_sternschema", "37_quellbewegung"])
def test_startzelle_ohne_daten_bricht_verstaendlich_ab(name, tmp_path, monkeypatch):
    monkeypatch.chdir(PROJECT)
    monkeypatch.setenv("CRIME_ANALYSIS_ROOT", str(tmp_path))
    nb = json.loads((PROJECT / "notebooks" / (name + ".ipynb")).read_text(encoding="utf-8"))
    start = next(c for c in nb["cells"] if c["cell_type"] == "code")
    with pytest.raises(AnalyseFehler, match="Kein bestaetigter Aufbau"):
        exec(compile("".join(start["source"]), name, "exec"), {})
    with datensperre(tmp_path):
        pass


def test_container_ohne_git_kann_einen_beleg_schreiben(tmp_path, monkeypatch):
    import storage.analysesitzung as module

    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    monkeypatch.setenv("GIT_COMMIT", "image-commit")
    with schreibzugriff(tmp_path):
        value = bestaetige(tmp_path, run_id="image-run", projekt_root=tmp_path)
    assert value["code_commit"] == "image-commit"
    assert value["code_dirty"] is None


def test_sitzung_verwendet_auch_fuer_aufraeumbericht_nur_lokale_daten(bestand):
    import storage

    vorher = storage.Storage(storage.Config(backend="hybrid"))
    storage.set_storage(vorher)
    with Analysesitzung(bestand, "37"):
        assert storage.for_root(bestand).backend == "local"
    assert storage.get_storage() is vorher


def test_nur_eine_sitzung_je_kernel(bestand, tmp_path):
    with Analysesitzung(bestand, "37"):
        with pytest.raises(AnalyseFehler, match="bereits eine Analysesitzung"):
            Analysesitzung(tmp_path / "anderer-bestand", "37")
