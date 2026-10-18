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
    # uuid-01 war bis zum 1.10.2026 entbehrlich. Seit Regel 2a haelt ihn die
    # Aenderungstabelle: Er ist der aeltere Partner des Paars 01/02, und
    # dessen Unterschied ist hier nicht gezogen. Woran dieser Test haengt,
    # bleibt davon unberuehrt - uuid-02 ist BASIS, nicht UNGEZOGEN.
    assert gruende(tmp_path, "city=detroit") == {
        "uuid-04": au.JUENGSTER, "uuid-03": au.VORHERIGER,
        "uuid-02": au.BASIS, "uuid-01": au.UNGEZOGEN,
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


def test_ein_lauf_ohne_gezogenen_unterschied_bleibt():
    """Regel 2a: Ein Vollschnappschuss traegt mehr als seinen Inhalt.

    Gegen seinen Vorgaenger gehalten sagt er, *was die Quelle geaendert hat*.
    Bis das herausgezogen ist, ist er unersetzlich - danach genuegt die
    schmale Aenderungstabelle.
    """
    laeufe = [au.Bestand("city=detroit", f"run_0{i}", f"2026-09-0{i}T10:00:00",
                         False, (), (), 10, Path("data"))
              for i in (4, 3, 2, 1)]
    ohne = {e.bestand.run_id: e.grund for e in au.entscheide(laeufe, set())}
    assert ohne["run_01"] is None, "ohne die Regel waere er entbehrlich"

    mit = {e.bestand.run_id: e.grund
           for e in au.entscheide(laeufe, set(), None, {"run_01"})}
    assert mit["run_01"] == au.UNGEZOGEN


def test_die_neue_regel_ueberschreibt_keinen_staerkeren_grund():
    """Sie haelt zusaetzlich, sie verdraengt nicht."""
    laeufe = [au.Bestand("city=detroit", f"run_0{i}", f"2026-09-0{i}T10:00:00",
                         False, (), (), 10, Path("data"))
              for i in (2, 1)]
    gruende = {e.bestand.run_id: e.grund for e in au.entscheide(
        laeufe, set(), {"run_01": "LN1"}, {"run_01", "run_02"})}
    assert gruende["run_01"] == au.GEPINNT
    assert gruende["run_02"] == au.JUENGSTER


def test_eine_unlesbare_aenderungstabelle_gibt_nichts_frei(tmp_path, monkeypatch):
    """Die Auskunft darf nur zusaetzlich halten, nie zusaetzlich loeschen.

    Faellt sie aus, ist die Antwort *keine Freigabe* - also eine leere Menge,
    und die uebrigen Regeln entscheiden wie bisher.
    """
    def kaputt(_wurzel):
        raise RuntimeError("Tabelle unlesbar")

    monkeypatch.setattr(
        "silver_pipeline.build_source_change.ungezogene_laeufe", kaputt)
    assert au.ungezogen_laut_tabelle(tmp_path) == set()


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


# --------------------------------------------------------------------------
# Releases: gepinnt plus die letzten acht (seit 4.10.2026)
#
# Die zweite Regel, eine Schicht hoeher. Sie ist gefaehrlicher als die fuer
# Laeufe: Releases liegen auf SeaweedFS als der gemeinsame Stand, und ein
# Loeschen dort betrifft jede Maschine, die vom Bucket liest. Deshalb steht
# hier jede Zeile der Entscheidungsmatrix als eigener Test - und zuerst die
# beiden Zusagen, die ueber allen stehen: **ohne ``--loeschen`` passiert
# nichts, und ohne ``--auch-fern`` passiert oben nichts.**
# --------------------------------------------------------------------------

from storage import Config, FakeS3Client, Storage, set_storage   # noqa: E402

RELEASE_DATEIEN = ("gold/dataset=fact_offense/part-0001.parquet",
                   "serving/analyse.duckdb")


def release_manifest(kennung: str, *, bytes_: int) -> str:
    return json.dumps({
        "release_id": kennung,
        "created_at_utc": kennung.replace("T", "T").replace("-", "-"),
        "bytes": bytes_,
        "status": "complete",
    })


def release_lokal(data_root: Path, kennung: str, *, bytes_: int = 1_000_000) -> Path:
    ordner = data_root / "releases" / f"release={kennung}"
    for name in RELEASE_DATEIEN:
        pfad = ordner / name
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(b"x" * 100)
    (ordner / "release.json").write_text(release_manifest(kennung, bytes_=bytes_),
                                         encoding="utf-8")
    return ordner


def release_oben(fake: FakeS3Client, kennung: str, *, bytes_: int = 1_000_000) -> str:
    praefix = f"releases/release={kennung}"
    for name in RELEASE_DATEIEN:
        fake.put(f"{praefix}/{name}", b"x" * 100)
    fake.put(f"{praefix}/release.json",
             release_manifest(kennung, bytes_=bytes_).encode("utf-8"))
    return praefix


def zeiger(data_root: Path, kennung: str) -> None:
    ordner = data_root / "releases"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "AKTUELL.json").write_text(json.dumps({
        "release_id": kennung,
        "created_at_utc": kennung,
        "path": f"releases/release={kennung}",
    }), encoding="utf-8")


def ablage(data_root: Path) -> tuple[Storage, FakeS3Client]:
    """Hybrid: lokal **und** oben, wie der Rechner, auf dem geraeumt wird."""
    fake = FakeS3Client()
    hier = Storage(Config(backend="hybrid", local_root=data_root,
                          s3_access_key="k", s3_secret_key="s"), fake)
    set_storage(hier)
    return hier, fake


def kennungen(n: int, *, ab: int = 1) -> list[str]:
    """``n`` Release-Kennungen, aelteste zuerst - die Kennung sortiert selbst."""
    return [f"2026-09-{tag:02d}T12-00-00Z" for tag in range(ab, ab + n)]


def rel_gruende(storage, config_root=None) -> dict[str, str | None]:
    entscheide, _ = au.release_bericht(storage, config_root)
    return {e.release_.release_id: e.grund for e in entscheide}


# -- Zeile 1: Trockenlauf ---------------------------------------------------


def test_der_trockenlauf_nennt_je_release_einen_grund_und_loescht_nichts(
        tmp_path, monkeypatch, capsys):
    """Die Zusage ueber allen anderen - auch fuer Releases."""
    _, fake = ablage(tmp_path)
    alle = kennungen(12)
    for k in alle:
        release_oben(fake, k)
    for k in alle[-8:]:
        release_lokal(tmp_path, k)
    zeiger(tmp_path, alle[-1])

    vorher_lokal = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    vorher_oben = sorted(fake.objekte)
    monkeypatch.setattr(sys, "argv", ["aufraeumen"])
    assert au.main() == 0

    assert sorted(p for p in tmp_path.rglob("*") if p.is_file()) == vorher_lokal
    assert sorted(fake.objekte) == vorher_oben and fake.geloescht == []
    out = capsys.readouterr().out
    assert "12 Releases, 4 entbehrlich" in out
    assert "MB frei" in out and "ENTBEHRLICH" in out
    assert "Nichts geloescht" in out
    # Je Release eine Zeile, und ``wo`` steht dabei.
    for k in alle:
        assert k in out
    assert "lokal" in out and "beide" in out and "oben" in out


# -- Zeile 2: Gepinnt bleibt ------------------------------------------------


def test_ein_gepinntes_release_bleibt_auch_als_aeltestes(tmp_path):
    storage, fake = ablage(tmp_path)
    alle = kennungen(12)
    for k in alle:
        release_oben(fake, k)
    zeiger(tmp_path, alle[-1])
    config = tmp_path / "config"
    register(config, alle[0], grund="referenzstand")

    gruende_ = rel_gruende(storage, config)
    assert gruende_[alle[0]] == au.GEPINNT
    assert gruende_[alle[1]] is None, "nur das gepinnte, nicht seine Nachbarn"


def test_auch_der_verzeichnisname_zaehlt_als_pin(tmp_path):
    """``release=<Kennung>`` steht im Register genauso gut wie die Kennung.

    Dasselbe Zugestaendnis, das ``ist_gepinnt`` fuer Laeufe schon macht:
    Chicago schreibt ``run_<Zeit>``, Detroit die nackte UUID - und ein Release
    heisst in den Pfaden ``release=<Kennung>``.
    """
    storage, fake = ablage(tmp_path)
    alle = kennungen(12)
    for k in alle:
        release_oben(fake, k)
    config = tmp_path / "config"
    register(config, f"release={alle[0]}", grund="referenzstand")
    assert rel_gruende(storage, config)[alle[0]] == au.GEPINNT


# -- Zeile 3: Der aktuelle Zeiger ------------------------------------------


def test_das_release_des_zeigers_bleibt_auch_ausserhalb_der_letzten_acht(tmp_path):
    """Fuenf Verbraucher loesen ueber ``AKTUELL.json`` auf, keiner sortiert."""
    storage, fake = ablage(tmp_path)
    alle = kennungen(12)
    for k in alle:
        release_oben(fake, k)
    zeiger(tmp_path, alle[0])          # der aelteste ist der aktuelle

    gruende_ = rel_gruende(storage)
    assert gruende_[alle[0]] == au.AKTUELL
    assert gruende_[alle[-1]] == au.JUENGSTE_N
    bleiben = [k for k, g in gruende_.items() if g is not None]
    assert len(bleiben) == au.RELEASES_N + 1


def test_das_entbehrliche_release_des_zeigers_wird_nicht_geloescht(tmp_path, monkeypatch):
    _, fake = ablage(tmp_path)
    alle = kennungen(12)
    for k in alle:
        release_oben(fake, k)
        release_lokal(tmp_path, k)
    zeiger(tmp_path, alle[0])
    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--loeschen", "--auch-fern"])
    assert au.main() == 0
    assert (tmp_path / "releases" / f"release={alle[0]}").is_dir()
    assert f"releases/release={alle[0]}/release.json" in fake.objekte


# -- Zeile 4: Nur lokal -----------------------------------------------------


def test_loeschen_ohne_auch_fern_raeumt_lokal_und_laesst_seaweedfs(
        tmp_path, monkeypatch, capsys):
    _, fake = ablage(tmp_path)
    alle = kennungen(10)
    for k in alle:
        release_oben(fake, k)
        release_lokal(tmp_path, k)
    zeiger(tmp_path, alle[-1])
    oben_vorher = sorted(fake.objekte)

    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--loeschen"])
    assert au.main() == 0

    assert not (tmp_path / "releases" / f"release={alle[0]}").exists()
    assert not (tmp_path / "releases" / f"release={alle[1]}").exists()
    for k in alle[2:]:
        assert (tmp_path / "releases" / f"release={k}").is_dir()
    assert sorted(fake.objekte) == oben_vorher, "oben darf nichts fehlen"
    assert fake.geloescht == []
    out = capsys.readouterr().out
    assert "2 Release(s) lokal geloescht, 2.0 MB frei." in out
    assert "Auf SeaweedFS unveraendert: 2 entbehrliche Release(s), 2.0 MB" in out
    assert "dafuer braucht es --auch-fern" in out


def test_ein_release_das_nur_oben_liegt_wird_nicht_als_frei_gemeldet(
        tmp_path, monkeypatch, capsys):
    """Ohne lokales Verzeichnis laeuft kein ``rmtree`` - also ist nichts frei.

    Die erste Fassung las die Summe aus der Entscheidungsliste statt aus dem,
    was wirklich wegging, und meldete die vollen MB als frei, waehrend der
    Hinweis darunter das Gegenteil sagte.
    """
    _, fake = ablage(tmp_path)
    alle = kennungen(10)
    for k in alle:
        release_oben(fake, k)          # nur oben, nichts lokal
    zeiger(tmp_path, alle[-1])

    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--loeschen"])
    assert au.main() == 0
    out = capsys.readouterr().out
    assert "0 Release(s) lokal geloescht, 0.0 MB frei." in out
    assert "Auf SeaweedFS unveraendert: 2 entbehrliche Release(s), 2.0 MB" in out
    assert fake.geloescht == []


def test_auch_fern_wird_ohne_s3_abgelehnt_bevor_etwas_weg_ist(
        tmp_path, monkeypatch, capsys):
    """STORAGE_BACKEND=local ist die Vorgabe - ein Satz, kein Traceback.

    Geprueft wird **vor** dem ersten Loeschen: ``loesche_releases`` nimmt das
    lokale Verzeichnis weg, bevor es nach oben greift, und ``storage.client``
    wirft unter ``local``. Die Reihenfolge entschied darueber, ob ein
    abgelehnter Lauf folgenlos ist.
    """
    set_storage(Storage(Config(backend="local", local_root=tmp_path)))
    alle = kennungen(10)
    for k in alle:
        release_lokal(tmp_path, k)
    zeiger(tmp_path, alle[-1])
    vorher = sorted(p for p in tmp_path.rglob("*") if p.is_file())

    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--loeschen", "--auch-fern"])
    assert au.main() == 2
    assert sorted(p for p in tmp_path.rglob("*") if p.is_file()) == vorher
    out = capsys.readouterr().out
    assert "--auch-fern braucht eine Ablage mit S3" in out
    assert "Nichts geloescht" in out


# -- Zeile 5: Fern ----------------------------------------------------------


def test_loeschen_mit_auch_fern_raeumt_beide_orte_ganz(tmp_path, monkeypatch, capsys):
    _, fake = ablage(tmp_path)
    alle = kennungen(10)
    for k in alle:
        release_oben(fake, k)
        release_lokal(tmp_path, k)
    zeiger(tmp_path, alle[-1])

    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--loeschen", "--auch-fern"])
    assert au.main() == 0

    for k in alle[:2]:
        assert not (tmp_path / "releases" / f"release={k}").exists()
        assert not [s for s in fake.objekte if f"release={k}/" in s], \
            "je Release alle Objekte, nicht nur das Manifest"
    for k in alle[2:]:
        assert (tmp_path / "releases" / f"release={k}").is_dir()
        assert len([s for s in fake.objekte if f"release={k}/" in s]) == 3
    out = capsys.readouterr().out
    assert "2 Release(s) lokal geloescht, 2.0 MB frei." in out
    assert "2 Release(s) auf SeaweedFS geloescht (6 Objekte), 2.0 MB frei." in out


def test_der_zeiger_selbst_wird_nie_angefasst(tmp_path, monkeypatch):
    """``releases/AKTUELL.json`` liegt ausserhalb jedes Release-Praefixes."""
    _, fake = ablage(tmp_path)
    alle = kennungen(10)
    for k in alle:
        release_oben(fake, k)
        release_lokal(tmp_path, k)
    zeiger(tmp_path, alle[-1])
    fake.put("releases/AKTUELL.json", b"{}")

    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--loeschen", "--auch-fern"])
    assert au.main() == 0
    assert (tmp_path / "releases" / "AKTUELL.json").is_file()
    assert "releases/AKTUELL.json" in fake.objekte


def test_ein_fehlgeschlagenes_delete_bricht_ab_und_laesst_den_rest(tmp_path):
    """Ein halb geleertes Praefix ist sichtbar; ein zweiter Lauf bringt es zu Ende."""
    class Zickig(FakeS3Client):
        def delete(self, key: str) -> None:
            if key.endswith("analyse.duckdb"):
                raise RuntimeError("SeaweedFS lehnt ab")
            super().delete(key)

    fake = Zickig()
    storage = Storage(Config(backend="hybrid", local_root=tmp_path,
                             s3_access_key="k", s3_secret_key="s"), fake)
    alle = kennungen(10)
    for k in alle:
        release_oben(fake, k)
    entscheide, _ = au.release_bericht(storage)
    with pytest.raises(RuntimeError):
        au.loesche_releases(entscheide, storage, auch_fern=True)
    # Geraeumt wird juengstes zuerst, entbehrlich sind die beiden aeltesten -
    # also bricht es im Praefix von ``alle[1]`` ab. Was dort vor der
    # ``analyse.duckdb`` lag, ist weg; ``release.json`` geht **zuletzt** und
    # steht deshalb noch, damit ``release.liste`` das Release weiter findet.
    praefix = f"releases/release={alle[1]}"
    assert f"{praefix}/gold/dataset=fact_offense/part-0001.parquet" not in fake.objekte
    assert f"{praefix}/serving/analyse.duckdb" in fake.objekte
    assert f"{praefix}/release.json" in fake.objekte, (
        "ohne das Manifest waere das halb geleerte Release unsichtbar"
    )
    assert au.releases(storage)[-1].release_id == alle[0]
    assert alle[1] in [r.release_id for r in au.releases(storage)]
    assert len([s for s in fake.objekte if f"release={alle[0]}/" in s]) == 3


# -- Zeile 6: --auch-fern allein -------------------------------------------


def test_auch_fern_ohne_loeschen_bleibt_ein_trockenlauf(tmp_path, monkeypatch, capsys):
    _, fake = ablage(tmp_path)
    alle = kennungen(10)
    for k in alle:
        release_oben(fake, k)
        release_lokal(tmp_path, k)
    zeiger(tmp_path, alle[-1])
    oben_vorher = sorted(fake.objekte)
    lokal_vorher = sorted(p for p in tmp_path.rglob("*") if p.is_file())

    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--auch-fern"])
    assert au.main() == 0

    assert sorted(fake.objekte) == oben_vorher and fake.geloescht == []
    assert sorted(p for p in tmp_path.rglob("*") if p.is_file()) == lokal_vorher
    out = capsys.readouterr().out
    assert "--auch-fern wirkt nur mit --loeschen" in out
    assert "Nichts geloescht" in out


# -- Zeile 7: Zeiger fehlt --------------------------------------------------


def test_ohne_aktuell_json_laeuft_die_regel_und_nennt_den_fehlenden_zeiger(
        tmp_path, monkeypatch, capsys):
    storage, fake = ablage(tmp_path)
    alle = kennungen(10)
    for k in alle:
        release_oben(fake, k)

    monkeypatch.setattr(sys, "argv", ["aufraeumen"])
    assert au.main() == 0
    out = capsys.readouterr().out
    assert "AKTUELL.json" in out and "Zeiger fehlt" in out
    assert "10 Releases, 2 entbehrlich" in out
    gruende_ = rel_gruende(storage)
    assert not any(g == au.AKTUELL for g in gruende_.values())


# -- Zeile 8: Weniger als n -----------------------------------------------


def test_weniger_releases_als_n_bleiben_alle(tmp_path):
    storage, fake = ablage(tmp_path)
    alle = kennungen(3)
    for k in alle:
        release_oben(fake, k)
    zeiger(tmp_path, alle[-1])
    entscheide, _ = au.release_bericht(storage)
    assert all(e.bleibt for e in entscheide)
    assert len(entscheide) == 3


def test_ohne_releases_meldet_der_bericht_null(tmp_path, monkeypatch, capsys):
    ablage(tmp_path)
    monkeypatch.setattr(sys, "argv", ["aufraeumen"])
    assert au.main() == 0
    assert "0 Releases, 0 entbehrlich" in capsys.readouterr().out


# -- Die Regel selbst, ohne Ablage ----------------------------------------


def test_die_achte_bleibt_und_die_neunte_geht():
    """``RELEASES_N`` ist die Grenze, und sie steht an einer Stelle."""
    stand = [au.ReleaseStand(f"r{i:02d}", "", 1000, "oben")
             for i in range(20, 0, -1)]
    gruende_ = {e.release_.release_id: e.grund
                for e in au.entscheide_releases(stand)}
    assert gruende_["r20"] == au.JUENGSTE_N
    assert gruende_[f"r{21 - au.RELEASES_N:02d}"] == au.JUENGSTE_N
    assert gruende_[f"r{20 - au.RELEASES_N:02d}"] is None
    assert au.RELEASES_N == 8, "datenhistorie.md 5.5: zwei Monate woechentlich"


def test_ein_gepinntes_release_belegt_einen_der_acht_plaetze():
    """Wie bei Laeufen: gezaehlt wird ueber die Reihenfolge.

    Das haelt weniger als *acht plus die gepinnten* - und damit nie mehr, als
    die Rechnung in ``datenhistorie.md`` 5.5 veranschlagt.
    """
    stand = [au.ReleaseStand(f"r{i:02d}", "", 1000, "oben")
             for i in range(20, 0, -1)]
    entscheide = au.entscheide_releases(stand, {"r18": "referenzstand"})
    assert sum(1 for e in entscheide if e.bleibt) == au.RELEASES_N
    assert entscheide[2].grund == au.GEPINNT


def test_das_inventar_steht_juengstes_zuerst(tmp_path):
    storage, fake = ablage(tmp_path)
    for k in kennungen(5):
        release_oben(fake, k)
    assert [r.release_id for r in au.releases(storage)] == \
        sorted(kennungen(5), reverse=True)


# --------------------------------------------------------------------------
# Dieselbe Zahl steht an vier Stellen - sie darf nur einmal veralten
#
# ``datenhistorie.md`` 5.5 entscheidet die Acht, und README wie
# storage-architektur.md sagen Bedienern, was bleibt. Ohne diesen Waechter
# veraltet das unbewachte Dokument genauso - einmal waren es acht ueberholte
# Aussagen auf einmal.
#
# **Nicht dabei: das PRD zum LN2** (E6, NFR-7). Es liegt unter
# ``_bmad-output/``, und das ist nach ``.gitignore`` ungetrackt - ein Waechter
# darueber waere in jedem frischen Klon und in CI ein ``FileNotFoundError``.
# Nachgezogen gehoert es trotzdem, nur eben von Hand.
# --------------------------------------------------------------------------

import re   # noqa: E402

PROJEKT = Path(__file__).resolve().parents[2]
ZAHLWORT = {3: "drei", 4: "vier", 5: "fünf", 6: "sechs", 7: "sieben",
            8: "acht", 9: "neun", 10: "zehn", 12: "zwölf"}
DOKUMENTE = (
    "README.md",
    "docs/storage-architektur.md",
    "docs/intern/datenhistorie.md",
)


def fliesstext(name: str) -> str:
    """Der Text mit zusammengezogenem Leerraum - Umbrueche zaehlen nicht."""
    return re.sub(r"\s+", " ", (PROJEKT / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", DOKUMENTE)
def test_jedes_dokument_nennt_die_entschiedene_zahl(name):
    text = fliesstext(name)
    assert f"die letzten {ZAHLWORT[au.RELEASES_N]}" in text, (
        f"{name} nennt nicht 'die letzten {ZAHLWORT[au.RELEASES_N]}' - "
        f"RELEASES_N ist {au.RELEASES_N}, das Dokument sagt etwas anderes"
    )


@pytest.mark.parametrize("name", DOKUMENTE)
def test_kein_dokument_nennt_mehr_eine_andere_zahl(name):
    """Die Zahl stand vorher als fuenf im PRD. Zwei Zahlen sind eine zu viel.

    Die Zahlwoerter selbst bleiben mit Umlaut - sie sind das, was in den
    Markdown-Dokumenten steht, und werden dort gesucht.
    """
    text = fliesstext(name)
    ueberholt = [w for n, w in ZAHLWORT.items()
                 if n != au.RELEASES_N and f"die letzten {w} Releases" in text]
    assert not ueberholt, f"{name} nennt noch: die letzten {ueberholt}"


@pytest.mark.parametrize("name", DOKUMENTE)
def test_jedes_dokument_nennt_den_zweiten_schalter(name):
    """``--auch-fern`` ist die Zusage, dass ein Lauf den Bucket nicht nebenbei raeumt."""
    assert "--auch-fern" in fliesstext(name), f"{name} nennt --auch-fern nicht"


def test_der_zweite_schalter_gibt_es_wirklich(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["aufraeumen", "--help"])
    with pytest.raises(SystemExit):
        au.arguments()
    hilfe = re.sub(r"\s+", " ", capsys.readouterr().out)
    assert "--auch-fern" in hilfe
    assert "nur zusammen mit --loeschen" in hilfe
    assert "Releases" in hilfe, "die Beschreibung nennt die Releases nicht"


# --------------------------------------------------------------------------
# Die Byte-Summe kommt seit dem 4.10.2026 aus storage
# --------------------------------------------------------------------------


def test_die_entscheidung_haengt_an_keiner_byte_summe(tmp_path):
    """Der Umbau auf ``Storage.bytes_unter`` darf nichts entscheiden.

    ``entscheide`` kennt Reihenfolge, Register und Manifeste - und sonst
    nichts. Hier steht das als Zusage da: Ein Lauf mit 0 Bytes bekommt
    denselben Grund wie einer mit vielen.
    """
    lauf(tmp_path, "city=chicago", "run_01", wann="2026-09-01T10:00:00")
    lauf(tmp_path, "city=chicago", "run_02", wann="2026-09-02T10:00:00")
    lauf(tmp_path, "city=chicago", "run_03", wann="2026-09-03T10:00:00")
    vorher = {e.bestand.run_id: e.grund for e in au.bericht(tmp_path)}

    for pfad in (tmp_path / "bronze" / "city=chicago").rglob("*.parquet"):
        pfad.write_bytes(b"")
    nachher = {e.bestand.run_id: e.grund for e in au.bericht(tmp_path)}
    assert vorher == nachher


def test_bytes_zaehlt_bronze_und_raw_zusammen(tmp_path):
    lauf(tmp_path, "city=chicago", "run_01", wann="2026-09-01T10:00:00")
    bestand = au.bestaende(tmp_path)["city=chicago"][0]
    manifest = (tmp_path / "bronze" / "city=chicago" / "run_01" / "manifest.json")
    erwartet = 2 * (1000 + manifest.stat().st_size)
    assert bestand.bytes == erwartet, "Bronze und sein Raw-Gegenstueck zusammen"


def test_bytes_laesst_ein_part_verzeichnis_weg(tmp_path):
    """Vorher zaehlte ``rglob('*')`` es mit - ein ``.part`` ist kein Lauf."""
    lauf(tmp_path, "city=chicago", "run_01", wann="2026-09-01T10:00:00")
    bestand = au.bestaende(tmp_path)["city=chicago"][0]
    schlank = bestand.bytes
    teil = tmp_path / "bronze" / "city=chicago" / "run_01" / ".part" / "x.parquet"
    teil.parent.mkdir(parents=True)
    teil.write_bytes(b"x" * 99_999)
    assert au.bestaende(tmp_path)["city=chicago"][0].bytes == schlank


def test_die_wurzel_ist_pflicht_und_eine_falsche_scheitert(tmp_path):
    """Eine fehlende oder falsche Wurzel darf keine kleine Zahl ergeben.

    ``data_root`` hat keinen Vorgabewert: Mit ``None`` meldete ``bytes`` 0,
    statt zu sagen, dass es nichts messen konnte. Das ist die Falle "ein
    fehlender Schluessel zeigt sich als falsches Ergebnis, nicht als Fehler".

    **Der Grund hat sich am 16.10.2026 geaendert, die Zusage nicht.** Seit
    ``Bestand`` Ablagepfade traegt statt lokaler Pfade, kann kein Lauf mehr
    "ausserhalb der Wurzel" liegen - ein relativer Pfad ist immer drin. Die
    Frage lautet jetzt, ob die Ablage ihn ueberhaupt kennt; eine falsche
    Wurzel beantwortet sie mit nein. Haette dieser Test nur auf das Wort
    "Ablagewurzel" gelauscht, waere er beim Umbau gruen geblieben und die
    Zusage still verschwunden - er fiel, und das war richtig.
    """
    with pytest.raises(TypeError):
        au.Bestand("city=detroit", "run_01", "2026-09-01T10:00:00",
                   False, (), (), 10)

    lauf(tmp_path, "city=chicago", "run_01", wann="2026-09-01T10:00:00")
    echt = au.bestaende(tmp_path)["city=chicago"][0]
    assert echt.bytes > 0

    daneben = echt._replace(data_root=tmp_path / "woanders")
    with pytest.raises(ValueError, match="liegt nichts"):
        daneben.bytes


# --------------------------------------------------------------------------
# Laeufe, die nur oben liegen (gefunden am 16.10.2026 auf srv01)
# --------------------------------------------------------------------------


def oben(fake, rel: str, *, wann: str, zeilen: int = 10) -> None:
    """Legt einen fertigen Bronze- und Raw-Lauf **nur** auf S3 ab."""
    manifest = json.dumps({"status": "complete", "run_id": rel.rsplit("/", 1)[-1],
                           "completed_at_utc": wann, "row_count": zeilen})
    for schicht in ("bronze", "raw"):
        fake.put(f"{schicht}/{rel}/part-0001.parquet", b"x" * 1000)
        fake.put(f"{schicht}/{rel}/manifest.json", manifest.encode("utf-8"))


@pytest.fixture
def nur_oben(tmp_path):
    """Eine Ablage im ``s3``-Modus: lokal liegt nichts, alles liegt oben.

    Genau der Zustand auf ``srv01``. Bis zum 16.10.2026 sah das Werkzeug
    darin **keinen einzigen** Lauf und meldete, es sei nichts aufzuraeumen,
    waehrend dort 141 lagen und der Silver-Bau an ihnen erstickte.
    """
    from storage import Config, FakeS3Client, Storage, set_storage

    fake = FakeS3Client()
    data_root = tmp_path / "data"
    set_storage(Storage(Config(backend="s3", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    return data_root, fake


def test_laeufe_die_nur_oben_liegen_werden_gesehen(nur_oben):
    data_root, fake = nur_oben
    for n in (1, 2, 3):
        oben(fake, f"city=detroit/run_0{n}", wann=f"2026-09-0{n}T10:00:00")

    gefunden = au.bestaende(data_root)["city=detroit"]
    assert [b.run_id for b in gefunden] == ["run_03", "run_02", "run_01"]
    # Und die Belegung zaehlt dort, wo die Laeufe wirklich liegen.
    assert gefunden[0].bytes > 0


def test_ohne_auch_fern_bleibt_oben_alles_stehen(nur_oben):
    """Dieselbe Trennung wie bei den Releases: Was oben liegt, sieht auch
    jemand anders - dafuer braucht es eine ausdrueckliche Ansage."""
    data_root, fake = nur_oben
    for n in (1, 2, 3):
        oben(fake, f"city=detroit/run_0{n}", wann=f"2026-09-0{n}T10:00:00")
    alle = au.bericht(data_root)
    entbehrlich = [e for e in alle if not e.bleibt]
    assert entbehrlich, "run_01 muesste entbehrlich sein"

    assert au.loesche(alle, data_root) == []
    assert fake.head("bronze/city=detroit/run_01/manifest.json") is not None


def test_mit_auch_fern_verschwinden_sie_oben(nur_oben):
    data_root, fake = nur_oben
    for n in (1, 2, 3):
        oben(fake, f"city=detroit/run_0{n}", wann=f"2026-09-0{n}T10:00:00")
    alle = au.bericht(data_root)

    geloescht = au.loesche(alle, data_root, auch_fern=True)
    assert "bronze/city=detroit/run_01" in geloescht
    assert "raw/city=detroit/run_01" in geloescht
    # Der juengste und der davor bleiben - Regel 1.
    assert fake.head("bronze/city=detroit/run_03/manifest.json") is not None
    assert fake.head("bronze/city=detroit/run_02/manifest.json") is not None
    assert fake.head("bronze/city=detroit/run_01/manifest.json") is None
    assert fake.head("bronze/city=detroit/run_01/part-0001.parquet") is None


def test_ein_gepinnter_lauf_ueberlebt_auch_oben(nur_oben, tmp_path):
    """Regel 0 gilt in beiden Modi - sonst waere das Register nur lokal wahr."""
    data_root, fake = nur_oben
    for n in (1, 2, 3):
        oben(fake, f"city=detroit/run_0{n}", wann=f"2026-09-0{n}T10:00:00")
    config_root = tmp_path / "config"
    register(config_root, "run_01")

    alle = au.bericht(data_root, config_root)
    au.loesche(alle, data_root, auch_fern=True)
    assert fake.head("bronze/city=detroit/run_01/manifest.json") is not None


def test_regel_zwei_sieht_auch_silver_das_nur_oben_liegt(nur_oben):
    """Sonst gaebe sie Laeufe frei, auf denen das aktuelle Silver ruht.

    Bis zum 16.10.2026 las ``genannt_in_silver`` ueber das Dateisystem. Im
    ``s3``-Modus liegt dort keine Silver-Tabelle - die Regel haette
    **nichts** geschuetzt, und das waere beim Loeschen aufgefallen, nicht
    davor.
    """
    data_root, fake = nur_oben
    for n in (1, 2, 3, 4):
        oben(fake, f"city=detroit/run_0{n}", wann=f"2026-09-0{n}T10:00:00")
    # Ein Silver, das sich ausdruecklich auf den aeltesten stuetzt.
    fake.put("silver/dataset=crime_offense/manifest.json", json.dumps({
        "status": "complete", "derived_from": {"detroit": ["run_01"]},
    }).encode("utf-8"))

    assert "run_01" in au.genannt_in_silver(data_root)
    gruende = {e.bestand.run_id: e.grund for e in au.bericht(data_root)}
    assert gruende["run_01"] == "von Silver genannt", gruende


def test_regel_vier_liest_ihre_tabelle_auch_oben(nur_oben):
    """Eine Auskunft, die immer dasselbe sagt, ist keine.

    ``bereits_gezogen`` las die Parquet-Datei lokal. Im ``s3``-Modus gab es
    sie dort nie, die Antwort war **immer** "noch nichts gezogen", und
    Regel 4 hielt jeden Schnappschuss fest - das Aufraeumen war wirkungslos.
    """
    from silver_pipeline.build_source_change import bereits_gezogen, tabellenverzeichnis

    data_root, _ = nur_oben
    # Ohne Tabelle: nichts gezogen - das ist richtig und bleibt so.
    assert bereits_gezogen(tabellenverzeichnis(data_root), data_root) == set()

    # **Und sie fragt die Ablage, nicht das Dateisystem.** Ein echter
    # Fernlesetest braeuchte ein echtes S3 - DuckDB liest keinen
    # FakeS3Client. Pruefbar ist dafuer, *wen* sie fragt: Mit der alten
    # Fassung (``(verzeichnis / PARQUET_FILE).is_file()``) kaeme hier nie
    # jemand an. Genau diese Mutation blieb am 16.10.2026 gruen, bis dieser
    # Teil dazukam.
    from storage import get_storage

    ablage = get_storage()
    gefragt: list[tuple] = []
    echt = ablage.exists

    def mitschreiben(*teile):
        gefragt.append(teile)
        return echt(*teile)

    ablage.exists = mitschreiben          # type: ignore[method-assign]
    try:
        bereits_gezogen(tabellenverzeichnis(data_root), data_root)
    finally:
        ablage.exists = echt              # type: ignore[method-assign]

    assert any("dataset=source_change" in str(t[0]) for t in gefragt), (
        f"die Ablage wurde nicht nach der Tabelle gefragt: {gefragt}")


# --------------------------------------------------------------------------
# Halbe Releases
# --------------------------------------------------------------------------
# Am 17.10.2026 scheiterte ein Upload am 26. von 28 Objekten - SeaweedFS
# antwortete mit ``InternalError`` - und liess 182,3 MB unter
# ``releases/release=2026-10-17T09-28-52Z/`` liegen. Der Lauf meldete das
# Release korrekt als gescheitert, der Zeiger blieb auf dem alten, und nichts
# davon war falsch. Die 182 MB blieben trotzdem, und **kein Werkzeug sah sie**:
# ``storage.release.liste`` findet Releases an ihrem ``release.json``, und
# genau das fehlte.


def halbes_release_oben(fake: FakeS3Client, kennung: str, *,
                        dateien: int = 3) -> str:
    """Ein Praefix mit Dateien, aber ohne ``release.json``."""
    praefix = f"releases/release={kennung}"
    for i in range(dateien):
        fake.put(f"{praefix}/gold/dataset=t{i}/part-0001.parquet", b"x" * 100)
    return praefix


def halbes_release_lokal(data_root: Path, kennung: str, *,
                         dateien: int = 3) -> Path:
    ordner = data_root / "releases" / f"release={kennung}"
    for i in range(dateien):
        pfad = ordner / f"gold/dataset=t{i}/part-0001.parquet"
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(b"x" * 100)
    return ordner


def test_ein_halbes_release_wird_gefunden(tmp_path):
    hier, fake = ablage(tmp_path)
    release_oben(fake, "2026-10-01T00-00-00Z")
    halbes_release_oben(fake, "2026-10-17T09-28-52Z")

    halbe = au.halbe_releases(hier)

    assert [h.kennung for h in halbe] == ["2026-10-17T09-28-52Z"], (
        "ohne release.json findet storage.release.liste nichts - dieses "
        "Werkzeug muss es trotzdem sehen")
    assert halbe[0].dateien == 3
    assert halbe[0].bytes == 300
    assert "oben" in halbe[0].wo


def test_ein_vollstaendiges_release_ist_nicht_halb(tmp_path):
    """Die Gegenprobe - sonst meldete jeder Lauf alles als halb."""
    hier, fake = ablage(tmp_path)
    release_oben(fake, "2026-10-01T00-00-00Z")
    release_lokal(tmp_path, "2026-10-02T00-00-00Z")
    assert au.halbe_releases(hier) == []


def test_lokal_und_oben_werden_zusammengezaehlt(tmp_path):
    hier, fake = ablage(tmp_path)
    kennung = "2026-10-17T09-28-52Z"
    halbes_release_lokal(tmp_path, kennung, dateien=2)
    halbes_release_oben(fake, kennung, dateien=3)

    halbe = au.halbe_releases(hier)

    assert len(halbe) == 1
    assert halbe[0].dateien == 5, "lokal 2 plus oben 3"
    assert halbe[0].wo == "lokal+oben"


def test_halbe_releases_gehen_lokal_weg_und_oben_erst_mit_auch_fern(tmp_path):
    hier, fake = ablage(tmp_path)
    kennung = "2026-10-17T09-28-52Z"
    ordner = halbes_release_lokal(tmp_path, kennung)
    halbes_release_oben(fake, kennung)

    au.loesche_halbe(au.halbe_releases(hier), hier)
    assert not ordner.exists(), "lokal muss es weg sein"
    assert any(kennung in s for s in fake.objekte), \
        "ohne --auch-fern bleibt oben alles liegen"

    au.loesche_halbe(au.halbe_releases(hier), hier, auch_fern=True)
    assert not any(kennung in s for s in fake.objekte)


def test_ein_vollstaendiges_release_wird_dabei_nicht_angefasst(tmp_path):
    """Der Praefix eines halben darf nicht in ein ganzes hineinreichen.

    ``releases/release=2026-10-03`` traefe als Praefix auch
    ``releases/release=2026-10-03T19-53-12Z/...`` - deshalb schliesst
    ``entferne_oben`` mit ``/`` ab. Dieser Test haelt das von hier aus fest.
    """
    hier, fake = ablage(tmp_path)
    ganz = release_oben(fake, "2026-10-17T09-28-52ZZZ")
    halbes_release_oben(fake, "2026-10-17T09-28-52Z")

    au.loesche_halbe(au.halbe_releases(hier), hier, auch_fern=True)

    assert f"{ganz}/release.json" in fake.objekte, \
        "das vollstaendige Release wurde mitgeloescht"


# --------------------------------------------------------------------------
# Alte Fassungen (gefunden am 18.10.2026 auf srv01)
# --------------------------------------------------------------------------


def test_ein_loeschen_gibt_in_einem_versionierten_eimer_keinen_platz_frei(tmp_path):
    """Die Tatsache, auf der alles andere hier beruht.

    Der Eimer ``urban-crime`` hat Versionierung eingeschaltet. ``delete``
    setzt dort eine Markierung; die Fassung darunter bleibt und belegt
    weiter Platz. Sichtbar war das in nichts: ``list`` nennt nur die
    aktuelle Fassung, also meldete jedes Werkzeug von uns den Platz als
    frei, und die naechtliche Sicherung nach Backblaze trug ihn weiter.
    Erst 3,91 GiB und ein vollgelaufenes Backup haben es gezeigt.
    """
    _, fake = ablage(tmp_path / "data")
    fake.put("silver/dataset=x/part.parquet", b"0123456789")
    fake.delete("silver/dataset=x/part.parquet")

    assert fake.list("silver/") == [], "fuer list ist es weg"
    uebrig = fake.fassungen("")
    assert len(uebrig) == 2, f"erwartet Fassung + Markierung, da sind {uebrig}"
    assert sum(f.size for f in uebrig) == 10, "die Bytes liegen noch da"
    assert [f.markierung for f in uebrig] == [False, True]


def test_der_bericht_nennt_die_alten_fassungen_je_schicht(tmp_path):
    hier, fake = ablage(tmp_path / "data")
    for i in range(3):
        fake.put("gold/dataset=fact/part.parquet", bytes(100 * (i + 1)))
    fake.put("silver/dataset=y/part.parquet", b"x" * 50)
    fake.delete("silver/dataset=y/part.parquet")

    stand = {s.schicht: s for s in au.alte_fassungen(hier)}
    assert set(stand) == {"gold", "silver"}
    # gold: zwei ueberschriebene Fassungen (100 und 200 Byte), die dritte ist
    # aktuell und zaehlt nicht.
    assert (stand["gold"].objekte, stand["gold"].bytes) == (2, 300)
    assert stand["gold"].markierungen == 0
    # silver: eine Fassung unter einer Markierung.
    assert (stand["silver"].objekte, stand["silver"].bytes) == (1, 50)
    assert stand["silver"].markierungen == 1


def test_der_bericht_laeuft_auch_ohne_loeschen(tmp_path, capsys):
    """Zeigen ist der Sinn des Moduls, und genau das fehlte.

    Dieses Modul **behauptet**, zu zeigen, was Platz belegt. Fuer 60 % des
    Eimers tat es das nicht. Ein Bericht, der erst auf einen Schalter hin
    hinsieht, haette denselben Fehler in neuer Form.
    """
    hier, fake = ablage(tmp_path / "data")
    fake.put("bronze/city=chicago/a.parquet", b"y" * 2048)
    fake.put("bronze/city=chicago/a.parquet", b"z" * 2048)

    au.zeige_fassungen(au.alte_fassungen(hier))
    ausgabe = capsys.readouterr().out
    assert "alte Fassungen" in ausgabe
    assert "bronze" in ausgabe
    assert "Markierung" in ausgabe


def test_geloescht_wird_nur_mit_auch_fern_und_nie_die_aktuelle_fassung(tmp_path):
    """Zwei Zusagen in einem Test, weil sie zusammen die Regel sind."""
    hier, fake = ablage(tmp_path / "data")
    fake.put("gold/dataset=fact/part.parquet", b"alt")
    fake.put("gold/dataset=fact/part.parquet", b"neu")

    assert au.loesche_fassungen(hier, auch_fern=False) == (0, 0), \
        "ohne --auch-fern wird oben nichts angefasst"
    assert len(fake.fassungen("")) == 2

    anzahl, frei = au.loesche_fassungen(hier, auch_fern=True)
    assert (anzahl, frei) == (1, 3), f"erwartet eine Fassung mit 3 Byte, war {(anzahl, frei)}"
    uebrig = fake.fassungen("")
    assert len(uebrig) == 1 and uebrig[0].aktuell
    assert fake.get("gold/dataset=fact/part.parquet") == b"neu", \
        "die aktuelle Fassung muss unberuehrt bleiben"


def test_ohne_s3_sagt_der_bericht_nichts_statt_zu_scheitern(tmp_path):
    """``STORAGE_BACKEND=local`` ist die Vorgabe und die Lage jedes Tests.

    ``storage.client`` wirft dort. Ein Bericht, der deshalb abbricht, haette
    ``aufraeumen`` im lokalen Modus unbenutzbar gemacht - und das ist der
    Modus, in dem es am haeufigsten laeuft.
    """
    lokal = Storage(Config(backend="local", local_root=tmp_path / "data"))
    set_storage(lokal)
    assert au.alte_fassungen(lokal) == []
    assert au.loesche_fassungen(lokal, auch_fern=True) == (0, 0)
