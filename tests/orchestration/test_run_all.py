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
