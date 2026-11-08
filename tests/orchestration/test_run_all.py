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
    # Die Namen tragen seit dem 3.10.2026 ihren Jahrgang beziehungsweise ihr
    # Vintage, damit das Protokoll sagt, welcher Durchgang wie lange brauchte.
    assert [s.name for s in stufen][:2] == ["tract_2024", "place_2024"]


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


# --------------------------------------------------------------------------
# Aktualitaet - aufgezeichnet war sie schon, jetzt wird sie geprueft
# --------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402


def stempel(tage_alt: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=tage_alt)).isoformat()


def test_veraltete_quellen_nennt_quelle_und_alter(tmp_path):
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A", wann=stempel(2))
    bronze(data_root, "city=detroit", "run_B", wann=stempel(20))
    zu_alt = ra.veraltete_quellen(data_root, maximal_alter_tage=8,
                                  erwartet=("city=chicago", "city=detroit"))
    assert list(zu_alt) == ["city=detroit"]
    assert 19.9 < zu_alt["city=detroit"] < 20.1


def test_detroits_zeitstempel_mit_zone_wird_verstanden(tmp_path):
    """finished_at traegt +00:00, completed_at_utc nicht - beide muessen gehen."""
    data_root = tmp_path / "data"
    manifest_schreiben(
        data_root / "bronze" / "city=detroit" / "run_X" / "manifest.json",
        status="SUCCESS", pipeline_run_id="run_X",
        finished_at=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
    )
    assert "city=detroit" in ra.veraltete_quellen(data_root, 8)


def test_ohne_schwelle_wird_nur_aufgezeichnet(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A", wann=stempel(400))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    manifest = ra.lauf(data_root, tmp_path)
    assert manifest["status"] == "complete"
    assert manifest["freshness_check"] == {"max_age_days": None, "stale": {}}


def test_ohne_ingestion_faellt_ein_veralteter_bestand_vor_der_ersten_stufe(tmp_path, monkeypatch):
    """Die Daten werden dabei nicht frischer - also lohnt keine Stufe."""
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A", wann=stempel(30))
    spur = tmp_path / "spur.txt"
    stufen = [falsche_stufe(tmp_path, "eins", 0, spur)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)

    manifest = ra.lauf(data_root, tmp_path, ohne_ingestion=True, maximal_alter_tage=8)

    assert manifest["status"] == "failed"
    assert manifest["stages"] == [], "es darf keine Stufe gelaufen sein"
    assert not spur.exists()
    assert "city=chicago" in manifest["freshness_check"]["stale"]


def test_mit_ingestion_wird_vor_dem_ableiten_geprueft(tmp_path, monkeypatch):
    """Die Frische entscheidet, bevor Gold entsteht - nicht danach.

    Bis zum 15.9.2026 lief die Pruefung nach allen dreizehn Stufen. Der Lauf
    endete mit "failed", aber Gold und Serving waren gebaut - aus Daten, die
    er selbst als zu alt erkannt hatte. Eine externe Pruefung hat das
    vorgefuehrt; dieser Test haelt die Korrektur fest.
    """
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A", wann=stempel(30))
    spur = tmp_path / "spur.txt"
    stufen = [
        falsche_stufe(tmp_path, "laden", 0, spur)._replace(gruppe="ingestion"),
        falsche_stufe(tmp_path, "ableiten", 0, spur)._replace(gruppe="gold"),
    ]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)

    manifest = ra.lauf(data_root, tmp_path, maximal_alter_tage=8)

    gefahren = spur.read_text(encoding="utf-8").split()
    assert gefahren == ["laden"], (
        f"abgeleitet wurde trotz veralteter Quelle: {gefahren}"
    )
    assert manifest["status"] == "failed"
    assert "city=chicago" in manifest["freshness_check"]["stale"]
    assert manifest["output_rows"] == {}


def test_eine_fehlende_quelle_faellt_auf(tmp_path, monkeypatch):
    """Der Befund der externen Pruefung: leerer Bestand galt als frisch.

    Geprueft wurde nur, was ``aktualitaet`` gefunden hatte - also genau die
    vorhandenen Quellen. Vier fehlende von fuenf ergaben ``{}``.
    """
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A", wann=stempel(1))
    zu_alt = ra.veraltete_quellen(
        data_root, maximal_alter_tage=8,
        erwartet=("city=chicago", "city=detroit", "dataset=noaa_ghcnd"),
    )
    assert zu_alt == {"city=detroit": None, "dataset=noaa_ghcnd": None}
    assert "kein fertiger Lauf" in ra.alterssatz("city=detroit", None, 8.0)


def test_die_erwarteten_quellen_kommen_aus_den_stufen():
    """Sonst waere es eine zweite Liste, die als erste veraltet."""
    aus_stufen = sorted(s.quelle for s in ra.STUFEN if s.quelle)
    assert sorted(ra.ERWARTETE_QUELLEN) == aus_stufen
    assert len(aus_stufen) == sum(1 for s in ra.STUFEN if s.gruppe == "ingestion"), (
        "jede Ingestion-Stufe muss den Bestand nennen, den sie fuellt"
    )


def test_frische_daten_gehen_durch(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A", wann=stempel(1))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    monkeypatch.setattr(ra, "ERWARTETE_QUELLEN", ("city=chicago",))
    manifest = ra.lauf(data_root, tmp_path, ohne_ingestion=True, maximal_alter_tage=8)
    assert manifest["status"] == "complete"
    assert manifest["freshness_check"]["stale"] == {}


# --------------------------------------------------------------------------
# --data-root erreicht die Stufen (externe Pruefung vom 15.9.2026)
# --------------------------------------------------------------------------


def test_jede_stufe_bekommt_die_datenwurzel(tmp_path, monkeypatch):
    """Der Befund: Der Lauf inventarisierte anderswo, als er baute.

    ``--data-root`` wurde ausgewertet, aber nicht weitergereicht. Die
    dreizehn Unterprozesse arbeiteten im Standardverzeichnis, waehrend
    Inventar und Protokoll im gewaehlten lagen.
    """
    data_root = tmp_path / "anderswo"
    for quelle in ra.ERWARTETE_QUELLEN:
        bronze(data_root, quelle, "run_A", wann=stempel(1))

    befehle: list[list[str]] = []

    class Fertig:
        returncode = 0

    monkeypatch.setattr(ra.subprocess, "run",
                        lambda cmd, cwd=None, **_: (befehle.append(cmd), Fertig())[1])
    ra.lauf(data_root, tmp_path, maximal_alter_tage=8)

    assert len(befehle) == len(ra.STUFEN)
    ohne = [c[2] for c in befehle if "--data-root" not in c]
    assert not ohne, f"diese Stufen bekamen die Wurzel nicht: {ohne}"
    for c in befehle:
        assert c[c.index("--data-root") + 1] == str(data_root)


def test_jedes_stufenmodul_kennt_die_option():
    """Die Option weiterzureichen hilft nur, wenn sie drueben ankommt.

    ``detroit_pipeline.extract_detroit`` kannte sie als einziges Modul nicht -
    es nahm ``--output-dir`` und ``--raw-dir`` einzeln.
    """
    wurzel = Path(ra.__file__).resolve().parents[1]
    ohne = []
    for stufe in ra.STUFEN:
        datei = wurzel / (stufe.modul.replace(".", "/") + ".py")
        if datei.is_file() and "--data-root" not in datei.read_text(encoding="utf-8"):
            ohne.append(stufe.modul)
    assert not ohne, f"diese Module kennen --data-root nicht: {sorted(set(ohne))}"



# --------------------------------------------------------------------------
# Das Release am Ende eines gruenen Laufs (seit 17.9.2026)
# --------------------------------------------------------------------------
# Ein Release ist der ganze Stand unter einer Kennung. Es entsteht nur nach
# einem vollstaendigen gruenen Lauf - und in publizierenden Modi von selbst.
# Ein halber Stand bekommt keine Kennung; ein Modus, der publizieren soll und
# es nicht kann, hat den Lauf nicht geschafft.

import sys  # noqa: E402

from storage import Config, FakeS3Client, Storage, set_storage  # noqa: E402
from tests.storage.test_release import gebaut as gold_und_serving  # noqa: E402


def gruener_lauf(tmp_path, monkeypatch, *, backend: str = "local", **kw) -> tuple[dict, Path, FakeS3Client]:
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    gold_und_serving(data_root)
    fake = FakeS3Client()
    set_storage(Storage(Config(backend=backend, local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    return ra.lauf(data_root, tmp_path, **kw), data_root, fake


def test_lokal_entsteht_ohne_ausdruecklichen_wunsch_kein_release(tmp_path, monkeypatch):
    manifest, data_root, _ = gruener_lauf(tmp_path, monkeypatch)
    assert manifest["status"] == "complete"
    assert manifest["release"] is None
    assert not (data_root / "releases").exists()


def test_release_erzwingt_eines_auch_lokal(tmp_path, monkeypatch):
    manifest, data_root, fake = gruener_lauf(tmp_path, monkeypatch, release=True)
    assert manifest["release"]["published"] is False
    kennung = manifest["release"]["release_id"]
    assert (data_root / "releases" / f"release={kennung}" / "release.json").is_file()
    assert fake.uploads == []


def test_das_release_traegt_die_jahrgaenge_des_laufs(tmp_path, monkeypatch):
    """Nur hier steht, welche Jahrgaenge im Stand liegen - also reicht es hier hinein.

    Ein Release sagt es von sich aus nicht: Gold und Serving liegen an Pfaden
    ohne ``year=``. ``orchestration.platzbedarf`` braucht die Angabe, um die
    Basis je Jahrgang herauszuteilen; ohne sie rechnet es einen Stand mit sechs
    Jahrgaengen noch einmal mit 5,38 hoch.
    """
    jahre = (2021, 2022, 2023, 2024, 2025, 2026)
    manifest, data_root, _ = gruener_lauf(tmp_path, monkeypatch, release=True,
                                          jahre=jahre)
    kennung = manifest["release"]["release_id"]
    abgelegt = json.loads(
        (data_root / "releases" / f"release={kennung}" / "release.json")
        .read_text(encoding="utf-8"))
    assert abgelegt["years"] == list(jahre)
    assert manifest["years"] == list(jahre), "dasselbe im Laufprotokoll"


def test_im_hybridmodus_entsteht_es_von_selbst_und_geht_hoch(tmp_path, monkeypatch):
    manifest, _, fake = gruener_lauf(tmp_path, monkeypatch, backend="hybrid")
    assert manifest["release"]["published"] is True
    assert fake.uploads[-1] == "releases/AKTUELL.json"
    assert json.loads(fake.get("releases/AKTUELL.json"))["release_id"] == manifest["release"]["release_id"]


def test_ohne_release_unterlaesst_es_auch_im_hybridmodus(tmp_path, monkeypatch):
    manifest, _, fake = gruener_lauf(tmp_path, monkeypatch, backend="hybrid", release=False)
    assert manifest["release"] is None and fake.uploads == []


def test_ein_roter_lauf_bekommt_kein_release(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    gold_und_serving(data_root)
    set_storage(Storage(Config(backend="hybrid", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), FakeS3Client()))
    stufen = [falsche_stufe(tmp_path, "kaputt", 2)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    manifest = ra.lauf(data_root, tmp_path)
    assert manifest["status"] == "failed" and manifest["release"] is None
    assert not (data_root / "releases").exists()


def test_bis_vor_serving_bekommt_kein_release(tmp_path, monkeypatch):
    manifest, _, _ = gruener_lauf(tmp_path, monkeypatch, backend="hybrid", bis="gold")
    assert manifest["status"] == "complete" and manifest["release"] is None


def test_ein_gescheitertes_release_macht_den_lauf_rot(tmp_path, monkeypatch):
    """Ein publizierender Modus, der nicht publiziert, hat nichts geschafft."""
    from orchestration import release as rel
    from storage.release import ReleaseFehler

    def kaputt(*_a, **_k):
        raise ReleaseFehler("Platte voll")

    monkeypatch.setattr(rel, "bilde_und_publiziere", kaputt)
    manifest, _, _ = gruener_lauf(tmp_path, monkeypatch, backend="hybrid")
    assert manifest["status"] == "failed"
    assert manifest["release"] == {"status": "failed", "error": "Platte voll"}


# --------------------------------------------------------------------------
# Raw und Bronze holen, bevor irgendetwas laeuft (seit 17.9.2026)
# --------------------------------------------------------------------------


def oben_lauf(fake: FakeS3Client, rel_dir: str) -> None:
    fake.put(f"{rel_dir}/part-0001.parquet", b"PAR1")
    fake.put(f"{rel_dir}/manifest.json",
             json.dumps({"status": "complete", "run_id": rel_dir.rsplit("/", 1)[-1],
                         "completed_at_utc": "2026-09-17T00:00:00+00:00"}).encode())


def test_im_hybridmodus_werden_fehlende_laeufe_zuerst_geholt(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    fake = FakeS3Client()
    oben_lauf(fake, "raw/city=chicago/ingest_date=2026-09-06/run_A")
    oben_lauf(fake, "bronze/city=chicago/ingest_date=2026-09-06/run_A")
    set_storage(Storage(Config(backend="hybrid", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    spur = tmp_path / "spur.txt"
    stufen = [falsche_stufe(tmp_path, "eins", 0, spur)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)

    manifest = ra.lauf(data_root, tmp_path, release=False)
    assert manifest["fetched_runs"] == [
        "raw/city=chicago/ingest_date=2026-09-06/run_A",
        "bronze/city=chicago/ingest_date=2026-09-06/run_A",
    ]
    assert (data_root / "bronze/city=chicago/ingest_date=2026-09-06/run_A/manifest.json").is_file()
    assert manifest["status"] == "complete"
    assert manifest["input_bronze_runs"] == {"city=chicago": ["run_A"]}, (
        "der geholte Lauf gehoert zum Stand dieses Laufs"
    )


def test_lokal_wird_nichts_geholt(tmp_path, monkeypatch):
    manifest, _, _ = gruener_lauf(tmp_path, monkeypatch)
    assert manifest["fetched_runs"] == [] and manifest["fetch_error"] is None


def test_ohne_holen_unterlaesst_es(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    fake = FakeS3Client()
    oben_lauf(fake, "bronze/city=chicago/ingest_date=2026-09-06/run_A")
    bronze(data_root, "city=chicago", "run_B")
    set_storage(Storage(Config(backend="hybrid", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    manifest = ra.lauf(data_root, tmp_path, release=False, holen=False)
    assert manifest["fetched_runs"] == []
    assert not (data_root / "bronze/city=chicago/ingest_date=2026-09-06/run_A").exists()


def test_scheitert_das_holen_laeuft_nichts(tmp_path, monkeypatch):
    """Silver auf einem halben Bronze waere der Stand, den niemand erklaeren kann."""
    data_root = tmp_path / "data"
    fake = FakeS3Client()
    oben_lauf(fake, "bronze/city=chicago/ingest_date=2026-09-06/run_A")
    echt = fake.get

    def kaputt(key):
        if key.endswith("part-0001.parquet"):
            raise OSError("Verbindung weg")
        return echt(key)

    fake.get = kaputt
    set_storage(Storage(Config(backend="hybrid", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    spur = tmp_path / "spur.txt"
    stufen = [falsche_stufe(tmp_path, "eins", 0, spur)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    manifest = ra.lauf(data_root, tmp_path, release=False)
    assert manifest["status"] == "failed"
    assert "Download fehlgeschlagen" in manifest["fetch_error"]
    assert manifest["stages"] == [] and not spur.exists(), "keine Stufe ist gelaufen"


def test_im_s3_modus_wird_nicht_von_selbst_geholt(tmp_path, monkeypatch):
    """s3 ist definiert als ohne lokalen Bestand - ein Lauf, der ihn fuellte,
    widerspraeche der eigenen Definition. Von Hand geht es weiterhin."""
    data_root = tmp_path / "data"
    fake = FakeS3Client()
    oben_lauf(fake, "bronze/city=chicago/ingest_date=2026-09-06/run_A")
    set_storage(Storage(Config(backend="s3", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    manifest = ra.lauf(data_root, tmp_path, release=False)
    assert manifest["status"] == "complete"
    assert manifest["fetched_runs"] == []
    assert not (data_root / "bronze").exists()


# --------------------------------------------------------------------------
# Wenn die Ablage nicht antwortet
# --------------------------------------------------------------------------
# Am 17.9.2026 wurde s3.datenwerft.ch auf dem Netzweg blockiert (TLS-Reset je
# nach SNI). Der Lauf meldete korrekt "Laeufe nicht geholt ... Nichts gebaut"
# - und druckte danach sechzig Zeilen botocore-Stapel, weil das Aufnehmen des
# Bestands fuer das Manifest erneut nach S3 griff. Das README sagt an dieser
# Stelle "ein Satz statt eines boto3-Tracebacks" zu.


class ToterClient(FakeS3Client):
    """Ein S3, das auf jeden Zugriff mit einem StorageError antwortet."""

    def _tot(self, *_a, **_k):
        from storage import StorageError
        raise StorageError("SeaweedFS: ConnectionClosedError bei LIST")

    head = get = put = list = _tot


def tote_ablage(tmp_path, monkeypatch) -> Path:
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    set_storage(Storage(Config(backend="hybrid", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), ToterClient()))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)
    return data_root


def test_ohne_ablage_gibt_es_kein_traceback_sondern_ein_manifest(tmp_path, monkeypatch):
    data_root = tote_ablage(tmp_path, monkeypatch)
    manifest = ra.lauf(data_root, tmp_path)

    assert manifest["status"] == "failed"
    assert "ConnectionClosedError" in manifest["fetch_error"]
    assert manifest["stages"] == [], "ohne Ablage laeuft keine Stufe"
    assert (data_root / ra.LAUF_MANIFEST).is_file(), (
        "das Protokoll muss trotzdem geschrieben sein - es nennt den Grund"
    )


def test_faellt_die_ablage_erst_beim_bestand_aus_haelt_der_lauf_das_aus(tmp_path, monkeypatch):
    """Der Weg, der den Stapel gedruckt hat: Holen ging, das Inventar nicht."""
    data_root = tmp_path / "data"
    bronze(data_root, "city=chicago", "run_A")
    fake = FakeS3Client()
    set_storage(Storage(Config(backend="hybrid", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    stufen = [falsche_stufe(tmp_path, "eins", 0)]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(ra, "auswahl", lambda *_a, **_k: stufen)

    from storage import StorageError

    def stirbt(*_a, **_k):
        raise StorageError("SeaweedFS: ConnectionClosedError bei LIST bronze/")

    monkeypatch.setattr(ra, "bronze_laeufe", stirbt)
    manifest = ra.lauf(data_root, tmp_path, release=False)

    assert manifest["status"] == "failed"
    assert "ConnectionClosedError" in manifest["inventory_error"]
    assert manifest["input_bronze_runs"] == {} and manifest["source_freshness"] == {}
    assert (data_root / ra.LAUF_MANIFEST).is_file()


def test_die_meldung_nennt_den_ausweg(tmp_path, monkeypatch, capsys):
    """Ein Satz, und er sagt, was man tun kann."""
    tote_ablage(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["run_all", "--data-root", str(tmp_path / "data")])
    assert ra.main() == 1
    ausgabe = capsys.readouterr().out
    assert "Die Ablage antwortet nicht" in ausgabe
    assert "python -m storage" in ausgabe and "STORAGE_BACKEND=local" in ausgabe
    assert "Traceback" not in ausgabe


# --------------------------------------------------------------------------
# Jahrgaenge und Vintages (FR-34)
# --------------------------------------------------------------------------


def test_bis_2024_ist_jedes_jahr_sein_eigener_nenner():
    assert [ra.vintage_fuer(j) for j in (2021, 2022, 2023, 2024)] == \
        [2021, 2022, 2023, 2024]


def test_ab_2025_bleibt_es_beim_2024er_vintage():
    """Am 3.10.2026 an der Census-API gemessen: 2025 und 2026 gibt es nicht.

    Keine Hochrechnung, sondern eine geliehene Bevoelkerung - und sie muss
    ueberall dabeistehen (FR-36).
    """
    assert ra.vintage_fuer(2025) == 2024
    assert ra.vintage_fuer(2026) == 2024


def test_sechs_jahrgaenge_brauchen_vier_vintages():
    assert ra.vintages_fuer(range(2021, 2027)) == (2021, 2022, 2023, 2024)


@pytest.mark.parametrize("text, erwartet", [
    ("2024", (2024,)),
    ("2021-2026", (2021, 2022, 2023, 2024, 2025, 2026)),
    ("2021,2023", (2021, 2023)),
    ("2023, 2021", (2021, 2023)),
    ("2024,2024", (2024,)),
    ("2021-2023,2026", (2021, 2022, 2023, 2026)),
])
def test_jahresangaben_werden_gelesen(text, erwartet):
    assert ra.jahre_aus_text(text) == erwartet


@pytest.mark.parametrize("text, grund", [
    ("1999", "ausserhalb"),
    ("2021-2019", "rueckwaerts"),
    ("zwanzig", "kein Jahr"),
    ("2021-zwei", "kein Jahresbereich"),
    ("", "kein Jahr angegeben"),
])
def test_unbrauchbare_jahresangaben_scheitern_mit_grund(text, grund):
    with pytest.raises(ValueError, match=grund):
        ra.jahre_aus_text(text)


def test_argparse_behaelt_die_begruendung():
    """``type=`` schluckt ValueError und ersetzt die Meldung.

    Dann erfuehre der Benutzer, dass 1999 falsch ist, aber nicht warum - und
    das Warum ist der ganze Sinn der Pruefung.
    """
    import argparse
    with pytest.raises(argparse.ArgumentTypeError, match="ausserhalb"):
        ra.jahre_argument("1999")


def test_ein_einzelner_jahrgang_aendert_nichts_an_der_strecke():
    """Die Vorgabe muss genau das tun, was sie vor FR-34 tat.

    ``STUFEN`` beschreibt die Form der Strecke - Architekturbild und
    Referenz-Startseite zaehlen daraus vierzehn. Die Entfaltung ist bei einem
    Jahrgang die Identitaet.
    """
    stufen = ra.auswahl(ohne_ingestion=False, bis=None)
    assert len(stufen) == len(ra.STUFEN)
    befehle = {" ".join(s.befehl()[1:]) for s in stufen}
    assert "-m chicago_pipeline.download_chicago --year 2024" in befehle
    assert "-m detroit_pipeline.extract_detroit --mode delta --years 2024" in befehle
    assert "-m census_pipeline.download_acs --vintage 2024" in befehle


def test_sechs_jahrgaenge_entfalten_die_quellen_aber_nicht_das_wetter():
    """Die Kriminalquellen je Jahr, Census je Vintage, NOAA einmal.

    NOAA laedt je Station einen Vollschnappschuss - ein Jahresfilter gibt es
    dort nicht, und sechs Aufrufe luden sechsmal dasselbe.
    """
    stufen = ra.auswahl(ohne_ingestion=False, bis=None, jahre=range(2021, 2027))
    wie_oft = {}
    for s in stufen:
        wurzel = s.name.rsplit("_", 1)[0] if s.je else s.name
        wie_oft[wurzel] = wie_oft.get(wurzel, 0) + 1
    assert wie_oft["chicago"] == 6 and wie_oft["detroit"] == 6
    assert wie_oft["tiger_tract"] == 4 and wie_oft["acs"] == 4
    assert wie_oft["tract"] == 4 and wie_oft["place"] == 4
    assert wie_oft["noaa"] == 1 and wie_oft["weather_day"] == 1
    assert wie_oft["crime_offense"] == 1 and wie_oft["gold"] == 1


def test_die_entfalteten_stufen_behalten_ihre_quelle():
    """Sonst faende die Aktualitaetspruefung sechs Quellen statt zwei."""
    stufen = ra.auswahl(ohne_ingestion=False, bis=None, jahre=(2023, 2024))
    chicago = [s for s in stufen if s.name.startswith("chicago")]
    assert len(chicago) == 2
    assert {s.quelle for s in chicago} == {"city=chicago"}
    assert sorted(ra.ERWARTETE_QUELLEN) == sorted(set(ra.ERWARTETE_QUELLEN))


def test_die_reihenfolge_haelt_auch_entfaltet():
    """Jedes tract-Vintage vor crime_offense, jedes Jahr vor Gold."""
    stufen = ra.auswahl(ohne_ingestion=False, bis=None, jahre=(2023, 2024))
    gruppen = [ra.GRUPPEN.index(s.gruppe) for s in stufen]
    assert gruppen == sorted(gruppen)
    namen = [s.name for s in stufen]
    assert max(namen.index(n) for n in namen if n.startswith("tract_")) < \
        namen.index("crime_offense")


# --------------------------------------------------------------------------
# Gold bekommt alle Vintages auf einmal
# --------------------------------------------------------------------------


def test_gold_laeuft_einmal_und_bekommt_alle_vintages():
    """Bis zum 3.10.2026 stand hier ein Riegel.

    ``build_gold`` nahm ein einzelnes ``--vintage`` und verband alles damit;
    bei vier Vintages haette jede Tat von 2021 den Nenner von 2024 bekommen.
    Der Gesamtlauf lehnte solche Laeufe deshalb vorher ab. Seit Vertrag 6 legt
    Gold ``dim_tract_acs`` je Vintage an - der Riegel ist weg, und statt
    seiner steht diese Zusage.
    """
    stufen = ra.auswahl(ohne_ingestion=False, bis=None, jahre=range(2021, 2027))
    gold = [s for s in stufen if s.gruppe == "gold"]
    assert len(gold) == 1, "Gold laeuft einmal, nicht je Vintage"
    assert gold[0].befehl()[-2:] == ["--acs-vintages", "2021,2022,2023,2024"]


def test_mit_einem_jahrgang_bekommt_gold_genau_dieses_vintage():
    gold = [s for s in ra.auswahl(ohne_ingestion=False, bis=None)
            if s.gruppe == "gold"]
    assert gold[0].befehl()[-2:] == ["--acs-vintages", "2024"]


def test_2025_und_2026_leihen_sich_das_2024er_vintage():
    """Zwei Jahrgaenge, ein Vintage - Gold bekommt es einmal."""
    gold = [s for s in ra.auswahl(ohne_ingestion=False, bis=None,
                                  jahre=(2025, 2026))
            if s.gruppe == "gold"]
    assert gold[0].befehl()[-2:] == ["--acs-vintages", "2024"]


def test_mehrere_vintages_laufen_jetzt_durch(tmp_path, monkeypatch):
    """Der Lauf wird nicht mehr vorab abgelehnt."""
    befehle: list[list[str]] = []

    class Fertig:
        returncode = 0

    monkeypatch.setattr(ra.subprocess, "run",
                        lambda cmd, cwd=None, **_: (befehle.append(cmd), Fertig())[1])
    manifest = ra.lauf(tmp_path / "data", tmp_path, jahre=range(2021, 2027))
    assert len(befehle) == 41
    assert manifest["years"] == list(range(2021, 2027))
    assert manifest["vintages"] == [2021, 2022, 2023, 2024]


def test_das_manifest_nennt_jahre_und_vintages(tmp_path, monkeypatch):
    class Fertig:
        returncode = 0

    monkeypatch.setattr(ra.subprocess, "run",
                        lambda cmd, cwd=None, **_: Fertig())
    manifest = ra.lauf(tmp_path / "data", tmp_path, jahre=(2025, 2026))
    assert manifest["years"] == [2025, 2026]
    assert manifest["vintages"] == [2024]


# --------------------------------------------------------------------------
# Die Projektwurzel (FR-4) und der Eingabe-Fingerabdruck (FR-8)
# --------------------------------------------------------------------------


def test_die_wurzel_kommt_aus_der_umgebung(tmp_path, monkeypatch):
    """Sie ist das Arbeitsverzeichnis **jedes** Unterprozesses.

    Geprueft wird am Ergebnis und nicht am Weg: ``lauf`` bekommt genau die
    Wurzel, die die Umgebung nennt.
    """
    import manifeste as mf

    wurzel = tmp_path / "projekt"
    wurzel.mkdir()
    for zeichen in mf.WURZELZEICHEN:
        ziel = wurzel / zeichen
        ziel.write_text("", encoding="utf-8") if ziel.suffix else ziel.mkdir()
    monkeypatch.setenv(mf.WURZEL_VARIABLE, str(wurzel))

    gesehen = {}

    def merke(data_root, projekt_root, **rest):
        gesehen["wurzel"] = projekt_root
        return {"status": "complete", "stages": [], "input_fingerprint": "x" * 64}

    monkeypatch.setattr(ra, "lauf", merke)
    monkeypatch.setattr(sys, "argv", ["run_all", "--data-root", str(tmp_path / "data")])
    assert ra.main() == 0
    assert gesehen["wurzel"] == wurzel.resolve()


def test_ohne_ableitbare_wurzel_bricht_es_mit_einem_satz_ab(tmp_path, monkeypatch):
    """Nicht raten, nicht im falschen Verzeichnis bauen - abbrechen und sagen, was fehlt.

    Ein Lauf im falschen Arbeitsverzeichnis scheitert nicht: Er findet
    ``config/`` nicht und baut ein Gold ohne Crosswalks. Deshalb hier und
    nicht spaeter.
    """
    import manifeste as mf

    monkeypatch.setattr(ra, "projektwurzel", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["run_all", "--trocken"])
    with pytest.raises(SystemExit) as abbruch:
        ra.main()
    meldung = str(abbruch.value)
    assert mf.WURZEL_VARIABLE in meldung, "die Meldung sagt nicht, was zu setzen ist"
    for zeichen in mf.WURZELZEICHEN:
        assert zeichen in meldung
    assert "pip install -e ." in meldung


def test_derselbe_bestand_traegt_denselben_fingerabdruck(tmp_path):
    """FR-8, soweit es ohne Container pruefbar ist.

    Der Fingerabdruck geht ueber die **Lauf-Kennungen** je Quelle, nicht ueber
    Pfade: Derselbe Bronze-Stand unter ``/app/data`` und unter
    ``/Users/.../data`` muss denselben Abdruck ergeben, sonst traegt ein Lauf
    im Container eine andere Zahl als derselbe Lauf auf dem Host - und die
    Zusage "derselbe Stand, derselbe Abdruck" ist wertlos.

    Gleichzeitig der Nachweis, dass die Reihenfolge des Findens nichts
    aendert: Die zweite Wurzel bekommt ihre Laeufe in umgekehrter Folge.
    """
    hier, dort = tmp_path / "host", tmp_path / "app"
    for quelle, lauf_ in (("city=chicago", "run_A"), ("city=detroit", "run_B")):
        bronze(hier, quelle, lauf_)
    for quelle, lauf_ in (("city=detroit", "run_B"), ("city=chicago", "run_A")):
        bronze(dort, quelle, lauf_)

    assert ra.bronze_laeufe(hier) == ra.bronze_laeufe(dort)
    assert ra.fingerabdruck(ra.bronze_laeufe(hier)) == \
        ra.fingerabdruck(ra.bronze_laeufe(dort))
    # Und ein anderer Stand ergibt einen anderen Abdruck - sonst waere die
    # Gleichheit oben nur die Gleichheit zweier leerer Mengen.
    bronze(dort, "dataset=noaa_ghcnd", "run_C")
    assert ra.fingerabdruck(ra.bronze_laeufe(hier)) != \
        ra.fingerabdruck(ra.bronze_laeufe(dort))


def test_die_historisierung_laeuft_im_gesamtlauf_und_vor_gold():
    """Eine Historisierung, an die jemand denken muss, ist keine.

    Bis zum 16.10.2026 stand ``build_source_change`` in keinem Bauplan, in
    keinem Skript und in keinem Zeitplan. Zwei Folgen: Der Unterschied
    zweier Schnappschuesse wurde nie herausgezogen, und
    ``orchestration.aufraeumen`` hielt nach seiner Regel 4 jeden
    Vollschnappschuss fest. Auf ``srv01`` lagen deshalb 141 Bronze-Laeufe,
    an denen der Silver-Bau erstickte - der Rohstoff staute sich, weil
    niemand ihn verarbeitete.

    **Nach ``crime_offense`` und vor Gold.** Beide lesen dieselben
    Schnappschuesse; und was aufgeraeumt werden darf, steht erst fest,
    wenn der Unterschied gezogen ist.
    """
    namen = [s.name for s in ra.STUFEN]
    assert "source_change" in namen, (
        "build_source_change steht in keinem Bauplan - dann laeuft die "
        "Historisierung nur, wenn jemand daran denkt")
    gruppen = [s.gruppe for s in ra.STUFEN]
    i = namen.index("source_change")
    assert gruppen[i] == "silver"
    assert i > namen.index("crime_offense"), "muss nach crime_offense laufen"
    assert i < gruppen.index("gold"), "muss vor Gold laufen"


# --------------------------------------------------------------------------
# Die lokale Arbeitskopie und das Release
# --------------------------------------------------------------------------
# Am 16.10.2026 war die Strecke auf ``srv01`` gruen und das Release
# gescheitert: sieben Gold-Tabellen fehlten, alle lagen oben. Jede Stufe hatte
# ihre lokale Kopie beim Publizieren entfernt, und ``storage.release.sammle``
# liest das Dateisystem.


def test_die_abgeleiteten_stufen_behalten_ihre_kopie_wenn_ein_release_folgt(monkeypatch):
    """Geprueft wird die **Umgebung der Unterprozesse**, nicht eine Config.

    Jede Stufe ist ein eigener Prozess. Was im Elternprozess an einer
    ``Config`` gesetzt wuerde, saehe keine von ihnen - das ist der Grund,
    warum der Schalter eine Umgebungsvariable ist und kein Argument.
    """
    gesehen = []

    class Fertig:
        returncode = 0

    def falsches_run(befehl, cwd=None, env=None):
        gesehen.append((env or {}).get("STORAGE_KEEP_LOCAL"))
        return Fertig()

    monkeypatch.setattr(ra.subprocess, "run", falsches_run)
    stufe = ra.Stufe("gold", "gold", "gold_pipeline.build_gold")

    ra.fahre([stufe], Path("."), None, behalte_lokal=True)
    assert gesehen == ["1"], \
        "ohne die Variable im Unterprozess entfernt die Stufe ihre Kopie"

    gesehen.clear()
    ra.fahre([stufe], Path("."), None, behalte_lokal=False)
    assert gesehen == [None], \
        "ohne folgendes Release darf der Schalter nicht gesetzt sein"


def test_der_schalter_haengt_am_release_und_am_modus():
    """Nicht geraten: Im ``local``-Modus gibt es kein Oben und nichts zu
    behalten, und ohne Release braucht niemand die Kopie.

    Gelesen wird der Quelltext, weil die Bedingung in ``lauf`` steckt und ein
    echter Lauf hier Netz, Schluessel und Daten braeuchte. Was der Test
    verlangt, ist, dass **beide** Teile der Bedingung dastehen - faellt einer
    weg, haelt ein ``local``-Lauf Kopien oder ein ``s3``-Lauf verliert sie.
    """
    quelle = Path(ra.__file__).read_text(encoding="utf-8")
    assert "behalte_lokal = folgt_release and ablage.backend == \"s3\"" in quelle, (
        "die Bedingung fuer den Schalter hat sich geaendert - sie muss das "
        "folgende Release **und** den s3-Modus verlangen")
    nach = quelle[quelle.index("if behalte_lokal:"):]
    assert "arbeitskopien_entfernen()" in nach, (
        "der Schalter wird gesetzt, aber nachher nicht geraeumt - dann haelt "
        "ein Modus, der 'ohne lokalen Bestand' heisst, nach jedem Lauf einen")


def test_geraeumt_wird_nach_dem_release_nicht_davor():
    """Die Reihenfolge ist die ganze Aenderung.

    Stuende das Raeumen vor dem Release, waere nichts gewonnen - genau das
    war der Zustand, der auf ``srv01`` gescheitert ist.
    """
    quelle = Path(ra.__file__).read_text(encoding="utf-8")
    release = quelle.index("bilde_und_publiziere")
    raeumen = quelle.index("arbeitskopien_entfernen()")
    assert release < raeumen, (
        "geraeumt wird vor dem Release - dann findet sammle() wieder nichts")


def test_nach_einem_gescheiterten_release_bleiben_die_kopien():
    """Der 17.10.2026, zweiter Teil.

    Hier stand das Gegenteil, mit der Begruendung *"oben liegt er
    vollstaendig"*. Dann brach ein ``InternalError`` von SeaweedFS den Upload
    beim 26. von 28 Objekten ab - und danach waren die lokalen Kopien weg,
    obwohl genau sie fuer den zweiten Versuch gebraucht wurden. Ein Lauf von
    zwoelf Minuten, nur um wiederherzustellen, was dalag. Die Begruendung
    stimmte nicht: Ist der Upload gescheitert, liegt oben *nicht* alles.

    Gelesen wird der Quelltext, weil die Bedingung in ``lauf`` steckt und ein
    echter Lauf hier Netz, Schluessel und Daten braeuchte.
    """
    quelle = Path(ra.__file__).read_text(encoding="utf-8")
    assert 'gescheitert = (freigabe or {}).get("status") == "failed"' in quelle, (
        "der Lauf unterscheidet nicht mehr, ob das Release gescheitert ist")
    assert "if behalte_lokal and not gescheitert:" in quelle, (
        "geraeumt wird wieder unbedingt - dann kostet ein Serverfehler beim "
        "Upload einen ganzen neuen Bau")
    raeumen = quelle.index("if behalte_lokal and not gescheitert:")
    bleiben = quelle.index("if behalte_lokal and gescheitert:")
    assert bleiben < raeumen, "der Fall 'gescheitert' gehoert zuerst gelesen"
