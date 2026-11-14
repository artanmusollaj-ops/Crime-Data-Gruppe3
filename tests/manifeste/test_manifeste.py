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


# --------------------------------------------------------------------------
# Herkunft: Abdruck, Pruefsumme, Referenz
# --------------------------------------------------------------------------


def test_der_abdruck_haengt_am_inhalt_nicht_an_der_reihenfolge():
    assert mf.fingerabdruck({"a": [1], "b": 2}) == mf.fingerabdruck({"b": 2, "a": [1]})
    assert mf.fingerabdruck({"a": [1]}) != mf.fingerabdruck({"a": [2]})
    assert len(mf.fingerabdruck({})) == 64


def test_die_dateipruefsumme_erkennt_eine_aenderung(tmp_path):
    datei = tmp_path / "crosswalk.csv"
    datei.write_text("iucr,nibrs\n0110,09A\n", encoding="utf-8")
    vorher = mf.datei_hash(datei)
    datei.write_text("iucr,nibrs\n0110,13A\n", encoding="utf-8")
    assert mf.datei_hash(datei) != vorher


def test_eine_referenz_nennt_stand_und_herkunft():
    eintrag = mf.referenz(Path("/x/part-0001.parquet"), {
        "built_at_utc": "2026-09-14T08:00:00+00:00",
        "input_fingerprint": "b" * 64,
        "derived_from": [{"run_id": "run_A"}],
    })
    assert eintrag["path"].endswith("part-0001.parquet")
    assert eintrag["built_at_utc"] and eintrag["input_fingerprint"]
    assert eintrag["derived_from"] == [{"run_id": "run_A"}]


def test_eine_referenz_ohne_manifest_ist_nur_ein_pfad():
    """Kein Bestand von vor der Aenderung darf daran scheitern.

    Der Pfad wird mit ``str(Path(...))`` verglichen, nicht als Literal:
    Auf Windows ist das ``\\x\\y.parquet``, und der erste Anlauf ist genau
    daran gescheitert.
    """
    pfad = Path("/x/y.parquet")
    assert mf.referenz(pfad, {}) == {"path": str(pfad)}


def herkunft_an(ort: str, gebaut: str, sha: str = "c" * 64) -> list[dict]:
    """Eine Gold-Herkunft wie ``build_gold.herkunft_der_quelle`` sie schreibt."""
    return [
        {"layer": "silver", "table": "crime_offense",
         "path": f"{ort}/silver/dataset=crime_offense/part-0001.parquet",
         "built_at_utc": gebaut, "input_fingerprint": "a" * 64,
         "derived_from": [{"layer": "bronze", "run_id": "run_A",
                           "path": f"{ort}/bronze/run_A", "built_at_utc": gebaut}]},
        {"layer": "config", "table": "nibrs_codes.csv",
         "path": f"{ort}/config/nibrs_codes.csv", "sha256": sha},
    ]


def test_derselbe_stand_traegt_an_jedem_ort_denselben_abdruck():
    """FR-8 als Regel, ohne Daten: Ort und Bauzeit fallen aus dem Abdruck.

    Derselbe Stand liegt im Container unter ``/app/data`` oder im Eimer, auf
    dem Host unter ``/Users/...`` und auf einem Windows-Rechner unter
    ``C:\\...``; gebaut wird er jedesmal zu einer anderen Uhrzeit. Der Abdruck
    muss in allen Faellen derselbe sein - und sich aendern, sobald ein Byte
    der Eingaben sich aendert (hier die Pruefsumme einer ``config/``-Datei).
    """
    container = mf.eingabe_abdruck(herkunft_an("/app/data", "2026-11-14T09:06:37Z"))
    eimer = mf.eingabe_abdruck(herkunft_an("s3://urban-crime", "2026-11-14T09:07:00Z"))
    host = mf.eingabe_abdruck(herkunft_an("/Users/christian/data", "2026-11-14T17:51:00Z"))
    windows = mf.eingabe_abdruck(herkunft_an("C:\\Users\\artan\\data", "2026-11-15T08:00:00Z"))
    assert container == eimer == host == windows
    assert mf.eingabe_abdruck(herkunft_an("/app/data", "2026-11-14T09:06:37Z",
                                          sha="d" * 64)) != container


def test_referenzdatei_nennt_pfad_und_pruefsumme(tmp_path):
    datei = tmp_path / "codes.csv"
    datei.write_text("x\n", encoding="utf-8")
    eintrag = mf.referenzdatei(datei)
    assert set(eintrag) == {"path", "sha256"} and len(eintrag["sha256"]) == 64


# --------------------------------------------------------------------------
# Die Projektwurzel - genannt oder erkannt, nie geraten
# --------------------------------------------------------------------------
# Bis zum 6.10.2026 stand ``Path(__file__).resolve().parents[3]`` an zwei
# Stellen und traf genau einen Fall: die editierbare Installation im Projekt.
# Was sie sonst lieferte, war ein Verzeichnis, das zufaellig vier Ebenen
# hoeher lag - und ``run_all`` machte es zum Arbeitsverzeichnis aller
# Unterprozesse. Das scheitert nicht, es baut ein Gold ohne Crosswalks.


def projekt(wurzel: Path) -> Path:
    """Ein Verzeichnis mit beiden Kennzeichen - was ``projektwurzel`` sucht."""
    wurzel.mkdir(parents=True, exist_ok=True)
    for zeichen in mf.WURZELZEICHEN:
        ziel = wurzel / zeichen
        if ziel.suffix:
            ziel.write_text("", encoding="utf-8")
        else:
            ziel.mkdir(parents=True, exist_ok=True)
    return wurzel


def test_die_genannte_wurzel_gilt(tmp_path):
    """Die Umgebung sagt es, und sie wird nicht nachgerechnet."""
    gesetzt = projekt(tmp_path / "projekt")
    assert mf.projektwurzel({mf.WURZEL_VARIABLE: str(gesetzt)}) == gesetzt.resolve()


def test_eine_falsche_angabe_wird_nicht_durch_raten_ersetzt(tmp_path):
    """Ein Konfigurationsfehler ist kein Grund, doch wieder zu raten.

    Sonst liefe ein Lauf mit verschriebener Variable still im Projekt des
    Entwicklers weiter - und im Abbild irgendwo.
    """
    assert mf.projektwurzel({mf.WURZEL_VARIABLE: str(tmp_path / "nirgends")}) is None


def test_ohne_angabe_wird_die_paketlage_erkannt():
    """Der Fall des Entwicklungsrechners: editierbar installiert, kein PROJECT_ROOT."""
    erkannt = mf.projektwurzel({})
    assert erkannt == Path(__file__).resolve().parents[2]
    assert mf.ist_projektwurzel(erkannt)


def test_keine_ableitbare_wurzel_ist_ein_none_und_kein_fehler(monkeypatch):
    """Das installierte Paket in site-packages - dort liegt kein Projekt.

    ``None`` und nicht eine Ausnahme: ``code_stand`` ruft dasselbe, und ein
    Lauf darf an der Herkunftsangabe nie scheitern.
    """
    monkeypatch.setattr(mf, "ist_projektwurzel", lambda pfad: False)
    assert mf.projektwurzel({}) is None


# --------------------------------------------------------------------------
# Der Commit, wenn kein Repository da ist
# --------------------------------------------------------------------------


@pytest.fixture
def ohne_git(monkeypatch):
    """Kein git im Pfad - wie in einem Abbild ohne ``.git/``."""
    import subprocess

    def kein_git(*a, **kw):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", kein_git)
    mf.code_stand.cache_clear()
    yield
    mf.code_stand.cache_clear()


def test_der_commit_kommt_aus_der_umgebung(monkeypatch, ohne_git):
    """Der Weg des Abbilds: ``.git/`` draussen, Herkunft trotzdem da.

    ``dirty`` ist dann ``False`` - keine Annahme, sondern die Lage: Ein Abbild
    hat keinen Arbeitsbaum, der abweichen koennte.
    """
    monkeypatch.setenv(mf.COMMIT_VARIABLE, "a" * 40)
    assert mf.code_stand() == {"git_commit": "a" * 40, "git_dirty": False}


def test_weder_git_noch_angabe_laesst_den_lauf_laufen(ohne_git):
    """Ein fremdes Abbild, ein installiertes Paket - kein Fehler, nur kein Commit."""
    assert mf.code_stand() == {"git_commit": None, "git_dirty": None}


@pytest.mark.parametrize("wert", ["abc1234", "v1.2", "HEAD", "", "   ",
                                  "A" * 39, "z" * 40])
def test_was_keine_volle_commit_kennung_ist_gilt_nicht(monkeypatch, wert):
    """Eine Kurzform sieht nachschlagbar aus und ist es nicht.

    ``git_commit`` traegt entweder eine volle SHA-1 oder nichts. Eine
    Zwischenform waere die unangenehmste Variante: Sie steht in tausenden
    Manifesten und faellt erst auf, wenn jemand sie nachschlagen will.
    """
    monkeypatch.setenv(mf.COMMIT_VARIABLE, wert)
    assert mf.aus_der_umgebung() is None


def test_die_grossschreibung_stoert_nicht(monkeypatch):
    """``git rev-parse`` liefert Kleinbuchstaben; eine Kopie von Hand nicht immer."""
    monkeypatch.setenv(mf.COMMIT_VARIABLE, "AB" * 20)
    assert mf.aus_der_umgebung() == "ab" * 20
