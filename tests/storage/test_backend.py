"""Die Ablage: Pfade, Lesen mit Rueckfall, gezieltes Publizieren.

Kein Test hier braucht SeaweedFS - S3 ist ``FakeS3Client``, ein dict.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from storage import Config, FakeS3Client, PublishError, Storage, paths


def ablage(tmp_path: Path, backend: str, **extra) -> tuple[Storage, FakeS3Client]:
    fake = FakeS3Client()
    config = Config(backend=backend, local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s", **extra)
    return Storage(config, fake), fake


def lokal_schreiben(storage: Storage, rel: str, inhalt: bytes = b"x") -> Path:
    pfad = storage.local_path(rel)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(inhalt)
    return pfad


def lauf_schreiben(storage: Storage, rel_dir: str, *, status: str = "complete") -> None:
    lokal_schreiben(storage, f"{rel_dir}/part-0001.parquet", b"PAR1")
    lokal_schreiben(storage, f"{rel_dir}/manifest.json",
                    json.dumps({"status": status, "run_id": rel_dir.rsplit("/", 1)[-1]}).encode())


SILVER = "silver/dataset=crime_offense/part-0001.parquet"


# --------------------------------------------------------------------------
# Pfade
# --------------------------------------------------------------------------


def test_relative_pfade_sind_posix_und_ohne_punkt_punkt():
    assert paths.relativ("silver", "dataset=x", "part-0001.parquet") == SILVER.replace("crime_offense", "x")
    assert paths.relativ("bronze\\city=chicago", "run_1") == "bronze/city=chicago/run_1"
    assert paths.relativ("./bronze/", "") == "bronze"
    with pytest.raises(paths.PfadFehler):
        paths.relativ("bronze/../silver")
    with pytest.raises(paths.PfadFehler):
        paths.relativ("/etc/passwd")


def test_local_path_resolution(tmp_path):
    storage, _ = ablage(tmp_path, "local")
    assert storage.resolve_read_path("silver", "dataset=crime_offense", "part-0001.parquet") \
        == str(tmp_path / "data" / "silver" / "dataset=crime_offense" / "part-0001.parquet")
    assert storage.local_path(SILVER) == tmp_path / "data" / SILVER


def test_s3_path_resolution(tmp_path):
    storage, _ = ablage(tmp_path, "s3")
    assert storage.resolve_read_path(SILVER) == "s3://urban-crime/" + SILVER
    assert storage.s3_path("bronze", "city=chicago") == "s3://urban-crime/bronze/city=chicago"


def test_hybrid_liest_lokal_wenn_vorhanden(tmp_path):
    storage, _ = ablage(tmp_path, "hybrid")
    lokal_schreiben(storage, SILVER)
    assert storage.resolve_read_path(SILVER) == str(tmp_path / "data" / SILVER)


def test_hybrid_faellt_auf_s3_zurueck_wenn_lokal_fehlt(tmp_path, caplog):
    storage, _ = ablage(tmp_path, "hybrid")
    with caplog.at_level("INFO", logger="storage"):
        assert storage.resolve_read_path(SILVER) == "s3://urban-crime/" + SILVER
    assert "falling back to S3" in caplog.text


def test_exists_und_read_text_folgen_derselben_regel(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    fake.put("silver/dataset=x/manifest.json", b'{"status": "complete"}')
    assert storage.exists("silver/dataset=x/manifest.json")
    assert not storage.exists("silver/dataset=y/manifest.json")
    assert json.loads(storage.read_text("silver/dataset=x/manifest.json"))["status"] == "complete"
    lokal_schreiben(storage, "silver/dataset=x/manifest.json", b'{"status": "lokal"}')
    assert json.loads(storage.read_text("silver/dataset=x/manifest.json"))["status"] == "lokal"


def test_local_kennt_kein_s3(tmp_path):
    storage = Storage(Config(backend="local", local_root=tmp_path))
    assert not storage.exists(SILVER)
    with pytest.raises(PublishError):
        storage.client  # noqa: B018 - der Zugriff selbst ist die Pruefung


# --------------------------------------------------------------------------
# Suchen: Laeufe und Dateien, lokal und auf S3 vereint
# --------------------------------------------------------------------------


def test_laeufe_vereinen_lokal_und_s3_lokal_gewinnt(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    lauf_schreiben(storage, "bronze/city=chicago/ingest_date=2026-09-01/run_a")
    fake.put("bronze/city=chicago/ingest_date=2026-09-02/run_b/manifest.json",
             b'{"status": "complete", "run_id": "run_b"}')
    fake.put("bronze/city=chicago/ingest_date=2026-09-02/run_b/part-0001.parquet", b"PAR1")
    # Derselbe Lauf lokal und auf S3: einmal, mit dem lokalen Manifest.
    fake.put("bronze/city=chicago/ingest_date=2026-09-01/run_a/manifest.json",
             b'{"status": "complete", "run_id": "s3-kopie"}')
    laeufe = storage.laeufe("bronze/city=chicago")
    assert [lf.relativ for lf in laeufe] == [
        "bronze/city=chicago/ingest_date=2026-09-01/run_a",
        "bronze/city=chicago/ingest_date=2026-09-02/run_b",
    ]
    assert laeufe[0].run_id == "run_a" and laeufe[0].verzeichnis.exists()
    assert laeufe[1].run_id == "run_b" and not laeufe[1].verzeichnis.exists()


def test_ein_unfertiger_lokaler_lauf_verdeckt_keinen_fertigen_auf_s3(tmp_path):
    """Die Manifest-Logik entscheidet, nicht die Naehe."""
    storage, fake = ablage(tmp_path, "hybrid")
    lauf_schreiben(storage, "bronze/city=detroit/full/year=2024/run_x", status="failed")
    fake.put("bronze/city=detroit/full/year=2024/run_x/manifest.json",
             b'{"status": "SUCCESS", "pipeline_run_id": "x"}')
    (lauf,) = storage.laeufe("bronze/city=detroit")
    assert lauf.manifest["status"] == "SUCCESS"


def test_laeufe_im_s3_modus_sehen_nichts_lokales(tmp_path):
    storage, fake = ablage(tmp_path, "s3")
    lauf_schreiben(storage, "bronze/dataset=noaa_ghcnd/station=A/run_lokal")
    fake.put("bronze/dataset=noaa_ghcnd/station=A/run_s3/manifest.json", b'{"status": "complete"}')
    assert [lf.relativ for lf in storage.laeufe("bronze/dataset=noaa_ghcnd", "run_*/manifest.json")] == []
    assert [lf.relativ for lf in storage.laeufe("bronze/dataset=noaa_ghcnd/station=A", "run_*/manifest.json")] \
        == ["bronze/dataset=noaa_ghcnd/station=A/run_s3"]


def test_list_files_mit_glob_semantik(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    lokal_schreiben(storage, "silver/dataset=tract/vintage=2023/part-0001.parquet")
    fake.put("silver/dataset=tract/vintage=2024/part-0001.parquet", b"PAR1")
    fake.put("silver/dataset=tract/vintage=2024/.x.part/part-0001.parquet", b"PAR1")
    assert storage.list_files("silver/dataset=tract", "**/part-0001.parquet") == [
        "silver/dataset=tract/vintage=2023/part-0001.parquet",
        "silver/dataset=tract/vintage=2024/part-0001.parquet",
    ]


def test_tabellen_lokal_und_auf_s3(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    lokal_schreiben(storage, "silver/dataset=tract/vintage=2024/manifest.json", b'{"row_count": 3}')
    fake.put("gold/dataset=fact_offense/manifest.json", b'{"row_count": 9}')
    assert [(t.schicht, t.name, t.zeilen, t.relativ) for t in storage.tabellen()] == [
        ("gold", "fact_offense", 9, "gold/dataset=fact_offense"),
        ("silver", "tract", 3, "silver/dataset=tract/vintage=2024"),
    ]


# --------------------------------------------------------------------------
# Publizieren
# --------------------------------------------------------------------------


def test_publish_run_laedt_alles_und_das_manifest_zuletzt(tmp_path, caplog):
    storage, fake = ablage(tmp_path, "hybrid")
    rel = "bronze/city=chicago/ingest_date=2026-09-13/run_abc"
    lauf_schreiben(storage, rel)
    with caplog.at_level("INFO", logger="storage"):
        oben = storage.publish_run(rel)
    assert fake.uploads == [f"{rel}/part-0001.parquet", f"{rel}/manifest.json"]
    assert oben == fake.uploads
    assert "Published: " + rel + "/manifest.json" in caplog.text
    assert storage.local_path(rel).exists(), "hybrid behaelt die lokale Kopie"


def test_publish_run_nimmt_auch_einen_lokalen_pfad(tmp_path):
    storage, _ = ablage(tmp_path, "hybrid")
    rel = "raw/city=detroit/full/year=2024/run_u"
    lauf_schreiben(storage, rel)
    assert storage.publish_run(storage.local_path(rel)) == [
        f"{rel}/part-0001.parquet", f"{rel}/manifest.json"]


def test_ausserhalb_der_wurzel_wird_nicht_publiziert(tmp_path, caplog):
    storage, fake = ablage(tmp_path, "hybrid")
    fremd = tmp_path / "anderswo" / "run_z"
    fremd.mkdir(parents=True)
    (fremd / "manifest.json").write_text("{}")
    with caplog.at_level("WARNING", logger="storage"):
        assert storage.publish_run(fremd) == []
    assert "outside LOCAL_DATA_ROOT" in caplog.text and fake.uploads == []


def test_local_publiziert_nichts(tmp_path):
    storage = Storage(Config(backend="local", local_root=tmp_path / "data"))
    lauf_schreiben(storage, "bronze/x/run_1")
    assert storage.publish_run("bronze/x/run_1") == []


def test_hybrid_ohne_publish_after_write_publiziert_nichts(tmp_path, caplog):
    storage, fake = ablage(tmp_path, "hybrid", hybrid_publish_after_write=False)
    lauf_schreiben(storage, "bronze/x/run_1")
    with caplog.at_level("INFO", logger="storage"):
        assert storage.publish_run("bronze/x/run_1") == []
    assert fake.uploads == [] and "Not published" in caplog.text


def test_identisches_objekt_wird_idempotent_akzeptiert(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    lauf_schreiben(storage, "bronze/x/run_1")
    storage.publish_run("bronze/x/run_1")
    erste = list(fake.uploads)
    assert storage.publish_run("bronze/x/run_1") == erste
    assert fake.uploads == erste, "nichts wurde ein zweites Mal hochgeladen"


def test_abweichendes_objekt_eines_laufs_ist_ein_fehler(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    lauf_schreiben(storage, "bronze/x/run_1")
    fake.put("bronze/x/run_1/part-0001.parquet", b"ETWAS ANDERES")
    with pytest.raises(PublishError, match="existiert bereits mit anderem Inhalt"):
        storage.publish_run("bronze/x/run_1")
    assert "bronze/x/run_1/manifest.json" not in fake.objekte, "das Manifest kam nie oben an"


def test_eine_tabelle_wird_ueberschrieben(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    rel = "silver/dataset=crime_offense"
    lauf_schreiben(storage, rel)
    fake.put(f"{rel}/part-0001.parquet", b"ALTER STAND")
    storage.publish_table(rel)
    assert fake.objekte[f"{rel}/part-0001.parquet"] == b"PAR1"


def test_ein_bestaetigter_upload_braucht_die_richtige_groesse(tmp_path):
    storage, _ = ablage(tmp_path, "hybrid")
    lauf_schreiben(storage, "bronze/x/run_1")

    class Verstuemmelt(FakeS3Client):
        def put(self, key, daten):
            super().put(key, daten[:-1])

    storage._client = kaputt = Verstuemmelt()
    with pytest.raises(PublishError, match="Upload nicht bestaetigt"):
        storage.publish_run("bronze/x/run_1")
    assert "bronze/x/run_1/manifest.json" not in kaputt.objekte


def test_ein_upload_fehler_wird_zum_publish_fehler(tmp_path):
    storage, _ = ablage(tmp_path, "hybrid")
    lauf_schreiben(storage, "bronze/x/run_1")

    class Tot(FakeS3Client):
        def put(self, key, daten):
            raise ConnectionError("SeaweedFS antwortet nicht")

    storage._client = Tot()
    with pytest.raises(PublishError, match="Upload fehlgeschlagen"):
        storage.publish_run("bronze/x/run_1")


def test_im_s3_modus_verschwindet_die_lokale_kopie_nach_dem_publish(tmp_path):
    storage, fake = ablage(tmp_path, "s3")
    lauf_schreiben(storage, "bronze/x/run_1")
    storage.publish_run("bronze/x/run_1")
    assert not storage.local_path("bronze/x/run_1").exists()
    assert set(fake.objekte) == {"bronze/x/run_1/part-0001.parquet", "bronze/x/run_1/manifest.json"}


def test_publish_to_shared_storage_unterscheidet_lauf_und_tabelle(tmp_path):
    import storage as st

    ablage_, fake = ablage(tmp_path, "hybrid")
    st.set_storage(ablage_)
    lauf_schreiben(ablage_, "bronze/x/run_1")
    lauf_schreiben(ablage_, "gold/dataset=fact_offense")
    fake.put("bronze/x/run_1/part-0001.parquet", b"ANDERS")
    fake.put("gold/dataset=fact_offense/part-0001.parquet", b"ANDERS")
    st.publish_to_shared_storage("gold", "dataset=fact_offense")  # Tabelle: ueberschreiben
    with pytest.raises(PublishError):
        st.publish_to_shared_storage("bronze/x/run_1")           # Lauf: Fehler


def test_for_root_haelt_backend_und_client(tmp_path):
    import storage as st

    ablage_, fake = ablage(tmp_path, "hybrid")
    st.set_storage(ablage_)
    andere = st.for_root(tmp_path / "anderswo")
    assert andere.backend == "hybrid" and andere.local_root == tmp_path / "anderswo"
    assert andere.client is fake
    assert st.for_root(None) is ablage_
    assert st.for_root(tmp_path / "data") is ablage_


@pytest.mark.parametrize("rel, muster, erwartet", [
    ("run_a/manifest.json", "**/run_*/manifest.json", True),
    ("x/y/run_a/manifest.json", "**/run_*/manifest.json", True),
    ("dataset=f/part-0001.parquet", "dataset=*/**/part-0001.parquet", True),
    ("dataset=f/vintage=2024/part-0001.parquet", "dataset=*/**/part-0001.parquet", True),
    ("other/dataset=f/part-0001.parquet", "dataset=*/**/part-0001.parquet", False),
    ("station=A/run_1/manifest.json", "station=*/run_*/manifest.json", True),
    ("station=A/x/run_1/manifest.json", "station=*/run_*/manifest.json", False),
    ("a/b", "**/*", True),
])
def test_glob_semantik_wie_pathlib(rel, muster, erwartet):
    from storage.backend import passt
    assert passt(rel, muster) is erwartet



# --------------------------------------------------------------------------
# Wenn SeaweedFS nicht antwortet: ein Satz, kein Traceback
# --------------------------------------------------------------------------


def test_ein_unerreichbarer_endpoint_wird_zu_einem_satz(monkeypatch):
    """Der erste Versuch gegen s3.datenwerft.ch: der Hostname loeste nicht auf,
    und die Pipeline fiel mit einem boto3-Traceback. Jetzt ein Satz mit Endpoint."""
    from botocore.exceptions import EndpointConnectionError

    from storage import StorageError, backend
    from storage.backend import Boto3Client

    monkeypatch.setattr(backend.time, "sleep", lambda s: None)
    client = Boto3Client(Config(backend="s3", s3_access_key="k", s3_secret_key="s",
                                s3_endpoint="s3.beispiel.invalid"))

    class Tot:
        def get_paginator(self, name):
            raise EndpointConnectionError(endpoint_url="https://s3.beispiel.invalid/x")

    client._client = Tot()
    with pytest.raises(StorageError, match="nicht erreichbar: https://s3.beispiel.invalid"):
        client.list("silver/")


def test_eine_abgelehnte_anfrage_nennt_den_code():
    from botocore.exceptions import ClientError

    from storage import StorageError
    from storage.backend import Boto3Client

    client = Boto3Client(Config(backend="s3", s3_access_key="k", s3_secret_key="s"))

    class Abgelehnt:
        def head_object(self, **kw):
            raise ClientError({"Error": {"Code": "InvalidAccessKeyId"}}, "HeadObject")

    client._client = Abgelehnt()
    with pytest.raises(StorageError, match="InvalidAccessKeyId"):
        client.head("silver/x")


def test_publish_error_ist_ein_storage_error():
    from storage import StorageError
    assert issubclass(PublishError, StorageError)



def test_ein_voruebergehender_403_wird_wiederholt(monkeypatch):
    """Beim ersten Nachpublizieren: HEAD 403, Sekunden spaeter 404 auf denselben
    Schluessel. Ein Aussetzer darf keinen Lauf abbrechen."""
    from botocore.exceptions import ClientError

    from storage import backend
    from storage.backend import Boto3Client

    monkeypatch.setattr(backend.time, "sleep", lambda s: None)
    client = Boto3Client(Config(backend="s3", s3_access_key="k", s3_secret_key="s"))
    antworten = [ClientError({"Error": {"Code": "403"}}, "HeadObject"),
                 ClientError({"Error": {"Code": "404"}}, "HeadObject")]

    class Launisch:
        def head_object(self, **kw):
            raise antworten.pop(0)

    client._client = Launisch()
    assert client.head("raw/x") is None, "nach dem 403 kam das ehrliche 404"
    assert antworten == []


def test_ein_dauerhafter_fehler_wird_nach_den_versuchen_zum_satz(monkeypatch):
    from botocore.exceptions import ClientError

    from storage import StorageError, backend
    from storage.backend import Boto3Client

    pausen = []
    monkeypatch.setattr(backend.time, "sleep", pausen.append)
    client = Boto3Client(Config(backend="s3", s3_access_key="k", s3_secret_key="s"))

    class Stur:
        def put_object(self, **kw):
            raise ClientError({"Error": {"Code": "503"}}, "PutObject")

    client._client = Stur()
    with pytest.raises(StorageError, match="503"):
        client.put("bronze/x", b"x")
    assert len(pausen) == backend.VERSUCHE - 1


def test_ein_endgueltiger_fehler_wird_nicht_wiederholt(monkeypatch):
    from botocore.exceptions import ClientError

    from storage import StorageError, backend
    from storage.backend import Boto3Client

    pausen = []
    monkeypatch.setattr(backend.time, "sleep", pausen.append)
    client = Boto3Client(Config(backend="s3", s3_access_key="k", s3_secret_key="s"))

    class Falsch:
        def put_object(self, **kw):
            raise ClientError({"Error": {"Code": "InvalidAccessKeyId"}}, "PutObject")

    client._client = Falsch()
    with pytest.raises(StorageError, match="InvalidAccessKeyId"):
        client.put("bronze/x", b"x")
    assert pausen == []
