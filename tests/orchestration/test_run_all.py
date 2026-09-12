"""Tests fuer den Run-Controller.

Sie laufen ohne Netz und ohne die echten Pipelines: Die Stufen werden durch
kleine Skripte ersetzt, die tun, was ein Test braucht - gelingen, scheitern
oder eine Spur hinterlassen.

Zwei Zusagen sind wichtiger als alle anderen und stehen deshalb als eigene
Tests da. **Beim ersten Fehler ist Schluss** - weiterzulaufen hiesse, auf einem
halben Stand aufzubauen und Erfolg zu melden. Und **das Gesamtmanifest nennt
jeden Eingabelauf** - bei Quellen, die sich staendig aendern, ist das die
Frage, die zaehlt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import run_all as ra


def manifest_schreiben(pfad: Path, **felder) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(felder), encoding="utf-8")


def bronze(data_root: Path, quelle: str, lauf: str, *,
           status: str = "complete", wann: str = "2026-09-01T10:00:00") -> None:
    manifest_schreiben(
        data_root / "bronze" / quelle / lauf / "manifest.json",
        status=status, run_id=lauf, completed_at_utc=wann,
    )


# --------------------------------------------------------------------------
# Die Reihenfolge
# --------------------------------------------------------------------------


def test_die_reihenfolge_haelt_die_abhaengigkeiten_ein():
    """tract vor crime_offense, place vor Gold, Ingestion vor allem.

    Das ist die eigentliche Aussage des Moduls. Faellt dieser Test, baut
    jemand ein Gold ohne Stadtzuordnung - und das scheitert nicht, es liefert
    eine Rate ohne Nenner.
    """
    namen = [s.name for s in ra.STUFEN]
    assert namen.index("tract") < namen.index("crime_offense")
    assert namen.index("tiger_tract") < namen.index("tract")
    assert namen.index("tiger_place") < namen.index("place")
    assert namen.index("crime_offense") < namen.index("gold")
    assert namen.index("gold") < namen.index("analyse_db")
    gruppen = [ra.GRUPPEN.index(s.gruppe) for s in ra.STUFEN]
    assert gruppen == sorted(gruppen), "die Gruppen stehen nicht in Reihenfolge"


def test_beide_tiger_auslieferungen_stehen_drin():
    """Ohne `place` bekommt dim_tract keine Stadtzuordnung - und scheitert nicht."""
    tiger = [s for s in ra.STUFEN if s.modul.endswith("download_tiger")]
    assert {s.argumente[-1] for s in tiger} == {"tract", "place"}


def test_ohne_ingestion_bleibt_die_ableitung_vollstaendig():
    stufen = ra.auswahl(ohne_ingestion=True, bis=None)
    assert not any(s.gruppe == "ingestion" for s in stufen)
    assert [s.name for s in stufen][:2] == ["tract", "place"]


def test_bis_schneidet_hinten_ab():
    stufen = ra.auswahl(ohne_ingestion=False, bis="silver")
    assert {s.gruppe for s in stufen} == {"ingestion", "silver"}


# --------------------------------------------------------------------------
# Der Lauf
# --------------------------------------------------------------------------


def falsche_stufe(tmp_path: Path, name: str, code: int, spur: Path | None = None):
    """Eine Stufe, die nur tut, was der Test braucht."""
    skript = tmp_path / f"{name}.py"
    zeilen = ["import sys"]
    if spur is not None:
        zeilen.append(f"open({str(spur)!r}, 'a').write({name!r} + '\\n')")
    zeilen.append(f"sys.exit({code})")
    skript.write_text("\n".join(zeilen), encoding="utf-8")
    return ra.Stufe("silver", name, name)


def test_beim_ersten_fehler_ist_schluss(tmp_path, monkeypatch):
    """Die wichtigste Zusage: keine Folgestufe auf einem halben Stand."""
    spur = tmp_path / "spur.txt"
    stufen = [
        falsche_stufe(tmp_path, "eins", 0, spur),
        falsche_stufe(tmp_path, "zwei", 3, spur),
        falsche_stufe(tmp_path, "drei", 0, spur),
    ]
    monkeypatch.syspath_prepend(str(tmp_path))
    protokoll = ra.fahre(stufen, tmp_path)

    assert [p["name"] for p in protokoll] == ["eins", "zwei"], (
        "nach dem Fehler lief noch etwas"
    )
    assert protokoll[-1]["exit"] == 3
    gelaufen = spur.read_text(encoding="utf-8").split()
    assert "drei" not in gelaufen


def test_ein_ganzer_lauf_schreibt_sein_manifest(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)

    manifest = ra.lauf(data_root, tmp_path)
    assert manifest["status"] == "complete"
    abgelegt = json.loads((data_root / ra.LAUF_MANIFEST).read_text("utf-8"))
    assert abgelegt == manifest


def test_ein_gescheiterter_lauf_heisst_failed(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    stufen = [falsche_stufe(tmp_path, "eins", 1)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)

    manifest = ra.lauf(data_root, tmp_path)
    assert manifest["status"] == "failed"
    assert manifest["output_rows"] == {}, (
        "ein gescheiterter Lauf darf keine Ergebniszahlen behaupten"
    )


# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------


def test_das_manifest_nennt_jeden_eingabelauf(tmp_path):
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    bronze(data_root, "city=chicago", "run_B")
    bronze(data_root, "city=detroit", "run_C")

    laeufe = ra.bronze_laeufe(data_root)
    assert laeufe == {"city=chicago": ["run_A", "run_B"], "city=detroit": ["run_C"]}


def test_ein_unfertiger_lauf_zaehlt_nicht(tmp_path):
    """Er liegt da, aber er gilt nicht - sonst ruht eine Zahl auf einem Abbruch."""
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    bronze(data_root, "city=chicago", "run_B", status="running")
    assert ra.bronze_laeufe(data_root) == {"city=chicago": ["run_A"]}


def test_detroits_eigenes_vokabular_wird_verstanden(tmp_path):
    """Acht Module schreiben 'complete', Detroits Ingestion 'SUCCESS'."""
    data_root = tmp_path / "data"
    manifest_schreiben(
        data_root / "bronze" / "city=detroit" / "run_X" / "manifest.json",
        status="SUCCESS", pipeline_run_id="run_X", finished_at="2026-09-12T09:00:00",
    )
    assert ra.bronze_laeufe(data_root) == {"city=detroit": ["run_X"]}
    assert ra.aktualitaet(data_root) == {"city=detroit": "2026-09-12T09:00:00"}


def test_derselbe_stand_traegt_denselben_fingerabdruck(tmp_path):
    """Damit sich eine Zahl einem Stand zuordnen laesst, statt ihn zu vermuten."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    for wurzel in (a, b):
        bronze(wurzel, "city=chicago", "run_A")
        bronze(wurzel, "city=detroit", "run_C")
    assert ra.fingerabdruck(ra.bronze_laeufe(a)) == ra.fingerabdruck(ra.bronze_laeufe(b))

    bronze(b, "city=chicago", "run_NEU")
    assert ra.fingerabdruck(ra.bronze_laeufe(a)) != ra.fingerabdruck(ra.bronze_laeufe(b))


def test_ein_kaputtes_manifest_bricht_die_herkunft_nicht(tmp_path):
    """Es zu ueberspringen ist richtig - es zaehlt ohnehin nicht als fertig."""
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    kaputt = data_root / "bronze" / "city=chicago" / "run_B" / "manifest.json"
    kaputt.parent.mkdir(parents=True, exist_ok=True)
    kaputt.write_text("{kein json", encoding="utf-8")
    assert ra.bronze_laeufe(data_root) == {"city=chicago": ["run_A"]}


def test_versteckte_laeufe_bleiben_draussen(tmp_path):
    """Ein .part-Verzeichnis ist ein Lauf, der noch nicht veroeffentlicht ist."""
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    bronze(data_root, "city=chicago", ".run_B.part")
    assert ra.bronze_laeufe(data_root) == {"city=chicago": ["run_A"]}
