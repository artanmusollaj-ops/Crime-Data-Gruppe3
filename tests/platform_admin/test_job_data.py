"""Job-Zeiger und Loeschregel fuer Job-Daten (E-5, Schritt fuer S-10).

Die Notebooks 34 und 37 brauchen im verwalteten Betrieb den Job-Ordner des
aktiven Release; das Release selbst traegt weder Bronze noch ganz Silver.
"""

import json
from pathlib import Path

import pytest

from orchestration.analyse import ZEIGER, waehle_analysebestand
from platform_admin import job_data
from platform_admin.jobs import run_one
from platform_admin.store import Store
from storage.analysesitzung import AnalyseFehler, datensperre
from tests.platform_admin.helpers import approve, bronze, synthetic_runner

PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_LOCK_ROOT", raising=False)
    monkeypatch.delenv("ADMIN_JOB_DATA_KEEP", raising=False)
    result = Store(PROJECT, tmp_path / "data")
    result.initialize("bootstrap")
    return result


def vorschlag(store, code):
    parent = store.current("mapping")["id"]
    return store.propose_mapping("detroit", code, "26B", parent, "Artan", "Synthetischer Test")


def freigegeben(store, code):
    """Ein Vorschlag, gebaut, freigegeben und aktiviert: die Impact-Zeile."""
    return approve(store, vorschlag(store, code))


def aktiv(store):
    return json.loads((store.data / "releases" / "AKTUELL.json").read_text())["release_id"]


def daten(store, jid):
    return store.root / "jobs" / jid / "data"


def test_die_aktivierung_setzt_den_zeiger_auf_den_job(store):
    row = freigegeben(store, "2403")
    zeiger = json.loads((store.root / "jobs" / ZEIGER).read_text())
    eintrag = zeiger["releases"][aktiv(store)]
    assert eintrag["impact_id"] == row["id"]
    assert eintrag["candidate_release_id"] == row["candidate_release_id"]
    assert eintrag["data"] == f"{row['id']}/data"
    wurzel, gefunden = waehle_analysebestand(store.data)
    assert wurzel == daten(store, row["id"]).resolve() and gefunden == eintrag


def test_zurueckschalten_waehlt_die_daten_des_aelteren_release(store):
    from storage.release import lies, setze_aktuell

    erstes = freigegeben(store, "2403")
    erstes_release = aktiv(store)
    zweites = freigegeben(store, "0901")
    assert waehle_analysebestand(store.data)[0] == daten(store, zweites["id"]).resolve()
    setze_aktuell(store.data / "releases" / "AKTUELL.json",
                  lies(store.data / "releases" / f"release={erstes_release}"))
    assert waehle_analysebestand(store.data)[0] == daten(store, erstes["id"]).resolve()


def test_ein_release_ohne_konsole_liest_weiter_die_datenwurzel(tmp_path):
    (tmp_path / "releases").mkdir()
    (tmp_path / "releases" / "AKTUELL.json").write_text(
        json.dumps({"release_id": "2026-11-14T09-09-47Z"}))
    assert waehle_analysebestand(tmp_path) == (tmp_path.resolve(), None)
    assert waehle_analysebestand(tmp_path / "leer") == ((tmp_path / "leer").resolve(), None)


def test_ein_konsolenrelease_ohne_zeiger_ist_ein_fehler(store):
    freigegeben(store, "2403")
    (store.root / "jobs" / ZEIGER).unlink()
    with pytest.raises(AnalyseFehler, match="keinen Job-Zeiger"):
        waehle_analysebestand(store.data)


def test_ein_aufgeraeumter_job_ist_ein_fehler_und_kein_rueckfall(store):
    import shutil

    row = freigegeben(store, "2403")
    shutil.rmtree(daten(store, row["id"]))
    with pytest.raises(AnalyseFehler, match="fehlt"):
        waehle_analysebestand(store.data)


def test_die_loeschregel_haelt_das_aktive_und_das_vorige_release(store):
    erstes = freigegeben(store, "2403")
    zweites = freigegeben(store, "0901")
    assert job_data.prune(store) == [], "Vorgabe 2: aktives und voriges Release bleiben"
    drittes = freigegeben(store, "0902")
    assert job_data.prune(store) == [erstes["id"]]
    assert not daten(store, erstes["id"]).exists()
    assert (store.root / "jobs" / erstes["id"] / "run.log").is_file(), "der Nachweis bleibt"
    for row in (zweites, drittes):
        assert daten(store, row["id"]).is_dir()
    zeiger = json.loads((store.root / "jobs" / ZEIGER).read_text())["releases"]
    assert {e["impact_id"] for e in zeiger.values()} == {zweites["id"], drittes["id"]}


def test_die_vorgabe_laesst_sich_enger_stellen(store, monkeypatch):
    erstes = freigegeben(store, "2403")
    zweites = freigegeben(store, "0901")
    monkeypatch.setenv("ADMIN_JOB_DATA_KEEP", "1")
    assert job_data.prune(store) == [erstes["id"]]
    assert daten(store, zweites["id"]).is_dir(), "das aktive Release bleibt immer"
    monkeypatch.setenv("ADMIN_JOB_DATA_KEEP", "0")
    with pytest.raises(Exception, match="mindestens 1"):
        job_data.prune(store)


def kandidat(store, code):
    """Ein gebauter Kandidat im Review, nicht entschieden."""
    rid = vorschlag(store, code)
    bronze(store.data)
    ergebnis = run_one(store, runner=synthetic_runner())
    assert ergebnis["status"] == "AWAITING_REVIEW", ergebnis
    return next(i for i in store.history()["impacts"] if i["revision_id"] == rid)


def status(store, iid, wert, **spalten):
    with store.db() as c:
        c.execute("UPDATE impact SET status=? WHERE id=?", (wert, iid))
        for name, v in spalten.items():
            c.execute(f"UPDATE impact SET {name}=? WHERE id=?", (v, iid))


def test_kandidaten_im_review_und_laufende_jobs_bleiben(store, monkeypatch):
    monkeypatch.setenv("ADMIN_JOB_DATA_KEEP", "1")
    freigegeben(store, "2403")
    review = kandidat(store, "0901")
    assert review["status"] == "READY" and review["baseline_release_id"] == aktiv(store)
    assert job_data.prune(store) == [], "Review auf dem aktiven Release"
    for laufend in ("RUNNING", "AWAITING_GIT", "APPROVED_PENDING_PUBLICATION"):
        status(store, review["id"], laufend)
        assert job_data.prune(store) == [], laufend
    status(store, review["id"], "READY", baseline_release_id="ein-aelteres-release")
    assert job_data.prune(store) == [review["id"]], (
        "ein Kandidat auf einer alten Basis ist nicht mehr freigabefaehig")


def test_ein_abgelehnter_kandidat_geht(store):
    freigegeben(store, "2403")
    review = kandidat(store, "0901")
    status(store, review["id"], "REJECTED")
    assert job_data.prune(store) == [review["id"]]


def test_eine_laufende_analyse_haelt_ihren_ordner(store):
    freigegeben(store, "2403")
    review = kandidat(store, "0901")
    status(store, review["id"], "REJECTED")
    with datensperre(daten(store, review["id"])):
        assert job_data.prune(store) == []
    assert job_data.prune(store) == [review["id"]], "der naechste Takt raeumt"


def test_der_takt_raeumt_vor_der_sicherung():
    quelle = (PROJECT / "src" / "crime" / "platform_admin" / "operations.py").read_text()
    takt = quelle[quelle.index("def _tick(store):"):]
    raeumen = takt.index("removed = prune(store)")
    sichern = takt.index("backup(store)")
    assert raeumen < sichern


def test_die_notebooks_lesen_die_aufgeloeste_wurzel():
    for name in ("34_gold_sternschema", "37_quellbewegung"):
        nb = json.loads((PROJECT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))
        start = "".join(nb["cells"][2]["source"])
        assert start.index("Analysesitzung(DATA_ROOT") < start.index("DATA_ROOT = analyse.root"), name


def test_der_trockenlauf_nennt_was_ginge_und_laesst_es_stehen(store):
    erstes = freigegeben(store, "2403")
    freigegeben(store, "0901")
    freigegeben(store, "0902")
    assert [jid for jid, _ in job_data.plan(store)] == [erstes["id"]]
    assert job_data.prune(store, dry_run=True) == [erstes["id"]]
    assert daten(store, erstes["id"]).is_dir()


def test_das_aktive_release_bleibt_auch_ohne_zeiger_eintrag(store, monkeypatch):
    # Vor dem Job-Zeiger aktiviert: nur die Kontrolldatenbank kennt den Job.
    monkeypatch.setenv("ADMIN_JOB_DATA_KEEP", "1")
    row = freigegeben(store, "2403")
    (store.root / "jobs" / ZEIGER).unlink()
    assert job_data.prune(store) == []
    assert daten(store, row["id"]).is_dir()


def test_die_loeschregel_loescht_keine_gehaltene_sperrdatei(store, monkeypatch):
    """Windows verweigert das Loeschen einer offenen Datei (WinError 32): Die
    Sperrdatei im Job-Ordner darf erst nach dem Freigeben weg - die Daten aber
    schon vorher, unter der Sperre. Seit #232 lief rmtree unter der Sperre,
    und der Windows-Lauf war auf main rot."""
    import os

    from storage import analysesitzung

    gehalten = set()
    acquire, release = analysesitzung._acquire, analysesitzung._release

    def nimm(stream):
        acquire(stream)
        gehalten.add(Path(stream.name).name)

    beim_freigeben = []

    def gib(stream):
        sperre = Path(stream.name)
        if sperre.name == "zugriff.lock":
            daten_ = sperre.parent.parent
            beim_freigeben.append(sorted(str(f.relative_to(daten_))
                                         for f in daten_.rglob("*") if f.is_file()))
        gehalten.discard(sperre.name)
        release(stream)

    echtes_unlink = os.unlink

    def wie_windows(pfad, *args, **kwargs):
        if Path(os.fsdecode(pfad)).name in gehalten:
            raise PermissionError(32, "The process cannot access the file", os.fsdecode(pfad))
        return echtes_unlink(pfad, *args, **kwargs)

    monkeypatch.setattr(analysesitzung, "_acquire", nimm)
    monkeypatch.setattr(analysesitzung, "_release", gib)
    monkeypatch.setattr(os, "unlink", wie_windows)
    freigegeben(store, "2403")
    review = kandidat(store, "0901")
    status(store, review["id"], "REJECTED")
    assert job_data.prune(store) == [review["id"]]
    assert not daten(store, review["id"]).exists()
    # Beim Freigeben lag nur noch die Sperre da: Die Daten gingen unter ihr.
    assert beim_freigeben[-1] == [".analyse/zugriff.lock"]
