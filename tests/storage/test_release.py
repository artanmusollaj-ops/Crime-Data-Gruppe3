"""Der Veroeffentlichungsstand: ein Verzeichnis je Release, ein Zeiger darauf.

``storage.release`` legt ab und publiziert; ``orchestration.release.bilde``
reicht ihm den Haken, der die selbstaendige Datenbank baut. Tests, die die
Datenbank brauchen, bilden ueber ``bilde``; die uebrigen ueber ``erstelle``.

Kein Test hier braucht SeaweedFS - S3 ist ``FakeS3Client``, ein dict. Gold und
Serving werden zur Laufzeit als kleine Parquet-Dateien erzeugt.

Was hier steht, ist die Zusage aus ``ausblick.md`` Abschnitt 6, so wie sie am
17.9.2026 gebaut wurde: Geschrieben wird vollstaendig unter einer neuen
Kennung, geprueft, und erst dann wird der Zeiger umgelegt - ``release.json``
zuletzt, ``AKTUELL.json`` danach. Ein Release ist unveraenderlich, und die
Datenbank darin antwortet auf jedem Rechner.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from orchestration.release import bilde
from gold_pipeline import TABELLEN as GOLD_TABELLEN
from serving.build_comparison import TABELLEN as VERGLEICHSTABELLEN
from serving.build_source_movement import TABELLEN as QUELLBEWEGUNG

from storage import Config, FakeS3Client, PublishError, Storage, release


#: Alle Serving-Tabellen eines Release: die Vergleichstabellen und die Quellbewegung.
SERVING_TABELLEN = VERGLEICHSTABELLEN + QUELLBEWEGUNG

JETZT = datetime(2026, 9, 17, 15, 4, 5, tzinfo=timezone.utc)
KENNUNG = "2026-09-17T15-04-05Z"


def ablage(tmp_path: Path, backend: str) -> tuple[Storage, FakeS3Client, Path]:
    fake = FakeS3Client()
    data_root = tmp_path / "data"
    config = Config(backend=backend, local_root=data_root,
                    s3_access_key="k", s3_secret_key="s")
    return Storage(config, fake), fake, data_root


def tabelle(data_root: Path, schicht: str, name: str, zeilen: int, **manifest) -> Path:
    ziel = data_root / schicht / f"dataset={name}"
    ziel.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"wert": list(range(zeilen))}), ziel / "part-0001.parquet")
    (ziel / "manifest.json").write_text(json.dumps({
        "status": "complete", "row_count": zeilen, "contract_version": 1,
        "built_at_utc": "2026-09-17T10:00:00+00:00",
        "input_fingerprint": f"fp-{name}", "derived_from": {}, **manifest,
    }), encoding="utf-8")
    return ziel


def gebaut(data_root: Path) -> None:
    """Ein **vollstaendiger** kleiner Stand - alles, was ein Release verlangt.

    Seit dem 17.9.2026 muss er das sein: ``orchestration.release.bilde``
    besteht auf jeder Gold- und Serving-Tabelle. Ein Teilstand ist genau der
    Fall, den ``test_ohne_serving_entsteht_kein_release`` prueft.
    """
    from gold_pipeline import TABELLEN as GOLD

    SERVING = SERVING_TABELLEN

    tabelle(data_root, "gold", "fact_offense", 5, contract_version=4,
            derived_from={"silver_crime_offense": {"path": "x"}},
            reconciliation={"coverage_percent": {"inside_city": 97.5}})
    for name in GOLD:
        if name != "fact_offense":
            tabelle(data_root, "gold", name, 3, contract_version=4)
    for name in SERVING:
        tabelle(data_root, "serving", name, 2)
    serving = data_root / "serving"
    (serving / "tracts.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    (serving / "tracts.manifest.json").write_text('{"features": 0}')


# --------------------------------------------------------------------------
# Bilden
# --------------------------------------------------------------------------


def test_ein_release_enthaelt_gold_serving_karte_datenbank_und_manifest(tmp_path):
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    ziel = bilde(data_root, jetzt=JETZT)
    assert ziel == data_root / "releases" / f"release={KENNUNG}"
    manifest = release.lies(ziel)
    assert set(manifest["files"]) >= {
        "gold/dataset=fact_offense/part-0001.parquet",
        "gold/dataset=fact_offense/manifest.json",
        "gold/dataset=dim_date/part-0001.parquet",
        "serving/dataset=comparison_day/part-0001.parquet",
        "serving/tracts.geojson",
        "serving/tracts.manifest.json",
        "serving/analyse.duckdb",
    }
    assert "release.json" not in manifest["files"], "das Manifest prueft nicht sich selbst"
    assert manifest["release_id"] == KENNUNG
    assert manifest["contract_versions"]["gold"] == 4
    assert manifest["contract_versions"]["serving/comparison_day"] == 1
    # Die Zahl kommt aus den Registern, damit eine siebte Gold-Tabelle sie
    # nicht lautlos falsch macht.
    assert len(manifest["tables"]) == len(GOLD_TABELLEN) + len(SERVING_TABELLEN), (
        f"{len(GOLD_TABELLEN)} Gold- und {len(SERVING_TABELLEN)} "
        "Serving-Tabellen"
    )
    assert manifest["input_fingerprint"] == "fp-fact_offense"
    assert manifest["gate"] == {"inside_city": 97.5}
    assert manifest["tables"]["gold/fact_offense"]["rows"] == 5
    assert set(manifest["code_version"]) == {"git_commit", "git_dirty"}


def test_ein_neues_manifest_nennt_die_gebauten_jahrgaenge(tmp_path):
    """``years`` - weil es aus dem Release selbst nicht ablesbar ist.

    Gold und Serving liegen an Pfaden ohne ``year=``, die Jahresspalte steckt
    in den Parquet-Dateien, und ``storage`` liest keine Zeilen. Wer wissen
    will, wie viel Mehrjahrigkeit in diesen Bytes steckt - so wie
    ``orchestration.platzbedarf`` -, musste es bis zum 4.10.2026 ueber
    ``pipeline_run.json`` erschliessen und durfte es nur glauben, wenn jenes
    Protokoll genau diesen Stand benannte.
    """
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    ziel = bilde(data_root, jahre=(2024, 2021, 2021, 2022), jetzt=JETZT)
    assert release.lies(ziel)["years"] == [2021, 2022, 2024], \
        "sortiert und entdoppelt, wie jede Jahresliste im Projekt"


def test_ohne_angabe_fehlt_der_schluessel_statt_leer_dazustehen(tmp_path):
    """Leer heisst "nicht gesagt", nicht "keine Jahrgaenge" - geraten wird nichts.

    Ein Manifest von vor dem 4.10.2026 nennt keine Jahre; genauso sieht eines
    aus, dem der Aufrufer keine gab. ``[]`` dagegen waere eine Aussage, und
    zwar eine falsche.
    """
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    manifest = release.lies(bilde(data_root, jetzt=JETZT))
    assert "years" not in manifest
    assert manifest["release_id"] == KENNUNG, "alles andere steht wie vorher da"


def test_jede_datei_traegt_eine_pruefsumme_die_stimmt(tmp_path):
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    ziel = bilde(data_root, jetzt=JETZT)
    for rel, angabe in release.lies(ziel)["files"].items():
        pfad = ziel / rel
        assert pfad.stat().st_size == angabe["bytes"], rel
        assert release.sha256(pfad) == angabe["sha256"], rel


def test_die_datenbank_im_release_ist_selbstaendig(tmp_path):
    """Tabellen statt Sichten - sie antwortet auch, wenn die Parquets weg sind."""
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    ziel = bilde(data_root, jetzt=JETZT)
    anderswo = tmp_path / "anderer_rechner" / "analyse.duckdb"
    anderswo.parent.mkdir()
    (ziel / "serving" / "analyse.duckdb").rename(anderswo)
    con = duckdb.connect(str(anderswo), read_only=True)
    try:
        arten = dict(con.execute(
            "SELECT table_type, count(*) FROM information_schema.tables GROUP BY 1"
        ).fetchall())
        erwartet = len(GOLD_TABELLEN) + len(SERVING_TABELLEN) + 1
        assert "VIEW" not in arten and arten["BASE TABLE"] == erwartet, (
            f"{erwartet - 1} Tabellen plus release_info - und keine Sicht"
        )
        assert con.execute("SELECT count(*) FROM fact_offense").fetchone()[0] == 5
        assert con.execute("SELECT release_id FROM release_info").fetchone()[0] == KENNUNG
    finally:
        con.close()


def test_der_lokale_zeiger_zeigt_auf_das_neueste_release(tmp_path):
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    release.erstelle(data_root, jetzt=JETZT)
    spaeter = datetime(2026, 9, 18, 8, 0, 0, tzinfo=timezone.utc)
    release.erstelle(data_root, jetzt=spaeter)
    zeiger = json.loads((data_root / "releases" / "AKTUELL.json").read_text())
    assert zeiger["release_id"] == "2026-09-18T08-00-00Z"
    assert zeiger["path"] == "releases/release=2026-09-18T08-00-00Z"


def test_ein_kandidat_entsteht_ohne_den_zeiger_zu_bewegen(tmp_path):
    """Die Engineering-Konsole baut Kandidaten, die erst nach dem Review
    gelten. Ein Kandidat ist ein vollstaendiges Release - nur der Zeiger
    bleibt beim bisherigen Stand, sonst lesen Analysen ungepruefte Zahlen."""
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    release.erstelle(data_root, jetzt=JETZT)
    spaeter = datetime(2026, 9, 18, 8, 0, 0, tzinfo=timezone.utc)
    kandidat = release.erstelle(data_root, jetzt=spaeter, aktivieren=False)

    assert (kandidat / release.RELEASE_MANIFEST).is_file()
    zeiger = json.loads((data_root / "releases" / "AKTUELL.json").read_text())
    assert zeiger["release_id"] == KENNUNG, "der Zeiger bleibt beim bisherigen Release"


def test_ein_erster_kandidat_legt_keinen_zeiger_an(tmp_path):
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    release.erstelle(data_root, jetzt=JETZT, aktivieren=False)
    assert not (data_root / "releases" / "AKTUELL.json").exists()


def test_ohne_gold_kein_release(tmp_path):
    _, _, data_root = ablage(tmp_path, "local")
    tabelle(data_root, "serving", "comparison_day", 2)
    with pytest.raises(release.ReleaseFehler, match="gold/dataset=fact_offense"):
        release.erstelle(data_root, jetzt=JETZT)
    assert not (data_root / "releases").exists() or not list((data_root / "releases").glob("*"))


def test_eine_unfertige_tabelle_kommt_nicht_mit(tmp_path):
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    tabelle(data_root, "gold", "dim_weather_extra", 9, status="publishing")
    ziel = release.erstelle(data_root, jetzt=JETZT)
    assert not any(r.startswith("gold/dataset=dim_weather_extra")
                   for r in release.lies(ziel)["files"])


def test_releases_sind_unveraenderlich(tmp_path):
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    release.erstelle(data_root, jetzt=JETZT)
    with pytest.raises(release.ReleaseFehler, match="gibt es schon"):
        release.erstelle(data_root, jetzt=JETZT)


def test_ein_abbruch_laesst_nichts_halbes_zurueck(tmp_path, monkeypatch):
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)

    def kaputt(*args, **kwargs):
        raise RuntimeError("Platte voll")

    monkeypatch.setattr("orchestration.release.build_selbststaendig", kaputt)
    with pytest.raises(RuntimeError):
        bilde(data_root, jetzt=JETZT)
    assert not list((data_root / "releases").glob("*")), "kein .part, kein halbes Release"


# --------------------------------------------------------------------------
# Publizieren
# --------------------------------------------------------------------------


def test_hybrid_publiziert_manifest_zuletzt_und_zeiger_danach(tmp_path):
    storage, fake, data_root = ablage(tmp_path, "hybrid")
    gebaut(data_root)
    ziel = bilde(data_root, jetzt=JETZT)
    oben = release.publiziere(storage, ziel)
    rel = f"releases/release={KENNUNG}"
    assert fake.uploads[-2] == f"{rel}/release.json", "release.json vor dem Zeiger"
    assert fake.uploads[-1] == "releases/AKTUELL.json", "der Zeiger ganz zuletzt"
    assert all(u.startswith(rel + "/") for u in fake.uploads[:-1])
    assert json.loads(fake.get("releases/AKTUELL.json"))["release_id"] == KENNUNG
    assert ziel.exists(), "hybrid behaelt die lokale Kopie"
    assert len(oben) == len(release.lies(ziel)["files"]) + 2


def test_s3_entfernt_die_lokale_kopie_nach_dem_publizieren(tmp_path):
    storage, fake, data_root = ablage(tmp_path, "s3")
    gebaut(data_root)
    ziel = release.erstelle(data_root, jetzt=JETZT)
    release.publiziere(storage, ziel)
    assert not ziel.exists()
    assert fake.head(f"releases/release={KENNUNG}/release.json") is not None


def test_local_publiziert_nichts(tmp_path):
    storage, fake, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    ziel = release.erstelle(data_root, jetzt=JETZT)
    assert release.publiziere(storage, ziel) == []
    assert fake.uploads == []


def test_ein_zweites_publizieren_ist_idempotent(tmp_path):
    storage, fake, data_root = ablage(tmp_path, "hybrid")
    gebaut(data_root)
    ziel = release.erstelle(data_root, jetzt=JETZT)
    release.publiziere(storage, ziel)
    n = len(fake.uploads)
    release.publiziere(storage, ziel)
    assert len(fake.uploads) == n + 1, "nur der Zeiger wird erneut geschrieben"


def test_anderer_inhalt_unter_derselben_kennung_ist_ein_fehler(tmp_path):
    storage, fake, data_root = ablage(tmp_path, "hybrid")
    gebaut(data_root)
    ziel = release.erstelle(data_root, jetzt=JETZT)
    fake.put(f"releases/release={KENNUNG}/gold/dataset=dim_date/part-0001.parquet", b"ANDERS")
    with pytest.raises(PublishError, match="anderem Inhalt"):
        release.publiziere(storage, ziel)
    assert fake.head("releases/AKTUELL.json") is None, "der Zeiger bleibt unberuehrt"


def test_scheitert_der_zeiger_bleibt_das_release_oben_aber_nicht_aktuell(tmp_path, monkeypatch):
    storage, fake, data_root = ablage(tmp_path, "hybrid")
    gebaut(data_root)
    ziel = release.erstelle(data_root, jetzt=JETZT)
    echt = fake.put

    def nur_zeiger_kaputt(key, daten):
        if key.endswith("AKTUELL.json"):
            raise OSError("Verbindung weg")
        echt(key, daten)

    monkeypatch.setattr(fake, "put", nur_zeiger_kaputt)
    with pytest.raises(PublishError, match="Zeiger nicht umgelegt"):
        release.publiziere(storage, ziel)
    assert fake.head(f"releases/release={KENNUNG}/release.json") is not None


# --------------------------------------------------------------------------
# Lesen
# --------------------------------------------------------------------------


def test_aktuell_liest_lokal_zuerst_sonst_oben(tmp_path):
    storage, fake, data_root = ablage(tmp_path, "hybrid")
    assert release.aktuell(storage) is None
    fake.put("releases/AKTUELL.json", json.dumps({"release_id": "oben"}).encode())
    assert release.aktuell(storage)["release_id"] == "oben"
    gebaut(data_root)
    release.erstelle(data_root, jetzt=JETZT)
    assert release.aktuell(storage)["release_id"] == KENNUNG


def test_liste_vereint_lokal_und_oben(tmp_path):
    storage, fake, data_root = ablage(tmp_path, "hybrid")
    gebaut(data_root)
    ziel = release.erstelle(data_root, jetzt=JETZT)
    fake.put("releases/release=2026-09-10T00-00-00Z/release.json",
             json.dumps({"created_at_utc": "2026-09-10T00:00:00Z", "bytes": 7}).encode())
    eintraege = {e["release_id"]: e["wo"] for e in release.liste(storage)}
    assert eintraege == {"2026-09-10T00-00-00Z": "oben", KENNUNG: "lokal"}
    release.publiziere(storage, ziel)
    eintraege = {e["release_id"]: e["wo"] for e in release.liste(storage)}
    assert eintraege[KENNUNG] == "beide"


def test_erstelle_und_publiziere_meldet_was_geschah(tmp_path):
    storage, _, data_root = ablage(tmp_path, "hybrid")
    gebaut(data_root)
    ergebnis = release.erstelle_und_publiziere(data_root, storage)
    assert ergebnis["published"] is True
    assert ergebnis["files"] == len(release.lies(
        release.verzeichnis(data_root, ergebnis["release_id"]))["files"])


# --------------------------------------------------------------------------
# Holen und einsetzen (Etappe 3)
# --------------------------------------------------------------------------


def publiziert(tmp_path: Path) -> tuple[Storage, FakeS3Client, Path, Path]:
    """Ein Release, das ein anderer Rechner publiziert hat: nur oben, nicht hier."""
    storage, fake, data_root = ablage(tmp_path, "hybrid")
    gebaut(data_root)
    ziel = bilde(data_root, jetzt=JETZT)
    release.publiziere(storage, ziel)
    # Der andere Rechner: dieselbe Ablage, leere lokale Wurzel.
    hier = tmp_path / "hier"
    storage2 = Storage(Config(backend="hybrid", local_root=hier,
                              s3_access_key="k", s3_secret_key="s"), fake)
    return storage2, fake, hier, ziel


def test_holen_aktuell_bringt_das_ganze_release_geprueft_herunter(tmp_path):
    storage, _, hier, original = publiziert(tmp_path)
    ziel = release.hole(storage, "aktuell")
    assert ziel == hier / "releases" / f"release={KENNUNG}"
    manifest = release.lies(ziel)
    for rel, angabe in manifest["files"].items():
        assert release.sha256(ziel / rel) == angabe["sha256"], rel
    assert (ziel / "serving" / "analyse.duckdb").read_bytes() == \
        (original / "serving" / "analyse.duckdb").read_bytes()
    assert json.loads((hier / "releases" / "AKTUELL.json").read_text())["release_id"] == KENNUNG


def test_holen_nur_datenbank_holt_genau_eine_datei(tmp_path):
    storage, fake, hier, _ = publiziert(tmp_path)
    geholt = []
    echt = fake.get
    fake.get = lambda key: geholt.append(key) or echt(key)
    ziel = release.hole(storage, KENNUNG, nur_datenbank=True)
    assert sorted(geholt) == sorted([
        f"releases/release={KENNUNG}/release.json",
        f"releases/release={KENNUNG}/serving/analyse.duckdb",
    ])
    assert (ziel / "serving" / "analyse.duckdb").is_file()
    assert not (ziel / "gold").exists()
    assert not (hier / "releases" / "AKTUELL.json").exists(), (
        "nur die Datenbank ist kein ganzer Stand - der Zeiger bleibt aus"
    )


def test_holen_ist_idempotent(tmp_path):
    storage, fake, _, _ = publiziert(tmp_path)
    release.hole(storage, "aktuell")
    geholt = []
    echt = fake.get
    fake.get = lambda key: geholt.append(key) or echt(key)
    release.hole(storage, "aktuell")
    assert geholt == [], (
        "beim zweiten Mal wird nichts geladen - auch release.json liegt identisch da; "
        "verglichen wird ueber head(), nicht ueber get()"
    )


def test_eine_datei_die_nicht_zum_manifest_passt_wird_verworfen(tmp_path):
    storage, fake, hier, _ = publiziert(tmp_path)
    fake.put(f"releases/release={KENNUNG}/gold/dataset=dim_date/part-0001.parquet", b"VERTAUSCHT")
    with pytest.raises(release.ReleaseFehler, match="SHA-256 stimmt nicht"):
        release.hole(storage, "aktuell")
    assert not (hier / "releases" / f"release={KENNUNG}" / "gold" / "dataset=dim_date"
                / "part-0001.parquet").exists()


def test_ohne_zeiger_ein_klarer_fehler(tmp_path):
    storage, _, _ = ablage(tmp_path, "hybrid")
    with pytest.raises(release.ReleaseFehler, match="Kein Zeiger"):
        release.hole(storage, "aktuell")


def test_einsetzen_bringt_die_tabellen_an_ihre_festen_pfade(tmp_path):
    storage, _, hier, _ = publiziert(tmp_path)
    ziel = release.hole(storage, "aktuell")
    eingesetzt = release.einsetzen(hier, ziel)
    assert (hier / "gold" / "dataset=fact_offense" / "manifest.json").is_file()
    assert (hier / "serving" / "dataset=comparison_day" / "part-0001.parquet").is_file()
    assert (hier / "serving" / "tracts.geojson").is_file()
    assert json.loads((hier / "gold" / "dataset=fact_offense" / "manifest.json").read_text())["row_count"] == 5
    assert len(eingesetzt) == len(GOLD_TABELLEN) + len(SERVING_TABELLEN) + 2, (
        f"{len(GOLD_TABELLEN) + len(SERVING_TABELLEN)} Tabellen, GeoJSON "
        "und sein Manifest"
    )
    assert not list((hier / "gold").glob(".*")), "kein .part, kein .superseded"


def test_einsetzen_ersetzt_einen_aelteren_stand_unteilbar(tmp_path):
    storage, _, hier, _ = publiziert(tmp_path)
    alt = tabelle(hier, "gold", "fact_offense", 99)
    ziel = release.hole(storage, "aktuell")
    release.einsetzen(hier, ziel)
    assert json.loads((alt / "manifest.json").read_text())["row_count"] == 5


# --------------------------------------------------------------------------
# Vollstaendigkeit: ein Release ist der ganze Stand oder keiner
# --------------------------------------------------------------------------
# Am 17.9.2026 wurde ``data/serving/`` beiseitegeschoben und ein Release
# gebildet. Es entstand mit 11 statt 21 Dateien - ohne die vier
# Vergleichstabellen, ohne die Karte - und nannte sich ``complete``. Gesucht
# hatte danach niemand; die Frage war, ob der Ordner ueberhaupt noch gebraucht
# wird. Die Antwort ist ja, und das hier haelt sie fest.


def test_ohne_serving_entsteht_kein_release(tmp_path):
    """Der Fall, fuer den es die Pflichtliste gibt."""
    from orchestration.release import VOLLSTAENDIG

    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    assert bilde(data_root, jetzt=JETZT).is_dir()

    shutil.rmtree(data_root / "serving")
    with pytest.raises(release.ReleaseFehler, match="serving/dataset=comparison_day"):
        bilde(data_root, jetzt=datetime(2026, 9, 18, tzinfo=timezone.utc))
    assert len(list((data_root / "releases").glob("release=*"))) == 1, (
        "es darf kein zweites, halbes Release entstanden sein"
    )
    assert "serving/tracts.geojson" in VOLLSTAENDIG


def test_die_pflichtliste_kommt_aus_den_schichten_selbst():
    """Kommt eine Tabelle dazu, steht sie von allein darin - nicht abgeschrieben."""
    from gold_pipeline import TABELLEN as gold
    from orchestration.release import VOLLSTAENDIG
    serving = SERVING_TABELLEN

    for name in gold:
        assert f"gold/dataset={name}" in VOLLSTAENDIG
    for name in serving:
        assert f"serving/dataset={name}" in VOLLSTAENDIG
    assert len(VOLLSTAENDIG) == len(gold) + len(serving) + 1


def test_eine_fehlende_gold_tabelle_faellt_ebenso_auf(tmp_path):
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    shutil.rmtree(data_root / "gold" / "dataset=dim_tract")
    with pytest.raises(release.ReleaseFehler, match="gold/dataset=dim_tract"):
        bilde(data_root, jetzt=JETZT)


def test_der_boden_in_storage_bleibt_minimal(tmp_path):
    """``storage`` kennt nur Dateien - die volle Liste reicht der Aufrufer nach.

    Ohne ``pflicht`` gilt weiterhin nur ``gold/dataset=fact_offense``. Das ist
    Absicht: Ein Fundament darf nicht wissen, welche Schichten es ueber ihm
    gibt (der Waechter ueber den Importgraphen hat genau das schon einmal
    gemeldet).
    """
    _, _, data_root = ablage(tmp_path, "local")
    gebaut(data_root)
    assert release.erstelle(data_root, jetzt=JETZT).is_dir()
    assert release.PFLICHT == ("gold/dataset=fact_offense",)


# --------------------------------------------------------------------------
# Herkunftsnachweis nach dem Einsetzen (E-5)
# --------------------------------------------------------------------------
# Auf srv01 laeuft nach run_all ``release holen aktuell --einsetzen``. Bis zum
# 13.11.2026 entwertete das den Nachweis, den run_all eben geschrieben hatte -
# obwohl es dasselbe Release mit denselben Bytes einsetzte. Seit dem Volllauf
# vom 10.11. starteten die Notebooks 34 und 37 dort nicht mehr.


def bestaetigt_und_publiziert(tmp_path, monkeypatch, *, release_id=KENNUNG):
    """Wie auf srv01: gebaut, publiziert und bestaetigt - in derselben Wurzel."""
    from orchestration import release as release_cli
    from storage.analysesitzung import bestaetige, schreibzugriff

    storage, _, data_root = ablage(tmp_path, "hybrid")
    gebaut(data_root)
    release.publiziere(storage, bilde(data_root, jetzt=JETZT))
    with schreibzugriff(data_root):
        bestaetige(data_root, run_id="build-a", projekt_root=tmp_path, release_id=release_id)
    monkeypatch.delenv("DATA_LOCK_ROOT", raising=False)
    monkeypatch.setattr(release_cli, "for_root", lambda _root: storage)
    return release_cli, data_root


def einsetzen(release_cli, data_root):
    return release_cli.main(["holen", "aktuell", "--einsetzen", "--data-root", str(data_root)])


def stand(data_root):
    pfad = data_root / ".analyse" / "stand.json"
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.is_file() else None


def test_dasselbe_release_auf_dieselben_bytes_behaelt_den_nachweis(tmp_path, monkeypatch, capsys):
    release_cli, data_root = bestaetigt_und_publiziert(tmp_path, monkeypatch)
    vorher = stand(data_root)
    assert einsetzen(release_cli, data_root) == 0
    assert stand(data_root) == vorher, "derselbe Nachweis, nicht ein neu geschriebener"
    assert "Herkunftsnachweis bleibt" in capsys.readouterr().out
    assert not (data_root / ".analyse" / "stand.vorher.json").exists()


def test_eine_andere_release_kennung_entwertet_den_nachweis(tmp_path, monkeypatch, capsys):
    release_cli, data_root = bestaetigt_und_publiziert(tmp_path, monkeypatch,
                                                       release_id="2026-09-16T00-00-00Z")
    assert einsetzen(release_cli, data_root) == 0
    assert stand(data_root) is None
    assert "Herkunftsnachweis entwertet" in capsys.readouterr().out
    assert not (data_root / ".analyse" / "stand.vorher.json").exists()


def test_ein_nachweis_ohne_release_wird_nicht_zurueckgesetzt(tmp_path, monkeypatch):
    # run_all ohne Release schreibt release_id=None; das ist kein Beleg fuer
    # irgendein eingesetztes Release.
    release_cli, data_root = bestaetigt_und_publiziert(tmp_path, monkeypatch, release_id=None)
    assert einsetzen(release_cli, data_root) == 0
    assert stand(data_root) is None


def test_abweichende_pruefsummen_entwerten_den_nachweis(tmp_path, monkeypatch, capsys):
    # Lokal weitergebaut nach dem Bestaetigen: das Release setzt andere Bytes
    # ein, als der Nachweis nennt.
    release_cli, data_root = bestaetigt_und_publiziert(tmp_path, monkeypatch)
    tabelle(data_root, "gold", "fact_offense", 99)
    from storage.analysesitzung import bestaetige, schreibzugriff
    with schreibzugriff(data_root):
        bestaetige(data_root, run_id="build-b", projekt_root=tmp_path, release_id=KENNUNG)
    assert einsetzen(release_cli, data_root) == 0
    assert stand(data_root) is None
    assert "Herkunftsnachweis entwertet" in capsys.readouterr().out


def test_ein_gescheitertes_einsetzen_laesst_den_nachweis_entwertet(tmp_path, monkeypatch):
    release_cli, data_root = bestaetigt_und_publiziert(tmp_path, monkeypatch)

    def bricht(*_args, **_kwargs):
        raise release.ReleaseFehler("halb eingesetzt")

    monkeypatch.setattr(release, "einsetzen", bricht)
    assert einsetzen(release_cli, data_root) == 1
    assert stand(data_root) is None
    assert not (data_root / ".analyse" / "stand.vorher.json").exists()
