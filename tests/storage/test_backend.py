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
    lokal_schreiben(storage, "silver/dataset=tract/vintage=2024/manifest.json",
                    b'{"status": "complete", "row_count": 3}')
    fake.put("gold/dataset=fact_offense/manifest.json",
             b'{"status": "complete", "row_count": 9}')
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


# --------------------------------------------------------------------------
# Integritaet und konsistenter Stand (externe Pruefung vom 15.9.2026)
# --------------------------------------------------------------------------


class EtagOhneMD5(FakeS3Client):
    """Ein Speicher, dessen ETag keine Pruefsumme ist.

    So verhaelt sich S3 nach einem mehrteiligen Upload: Das ETag ist ein Hash
    ueber die Teil-Hashes, mit angehaengter Teilezahl. SeaweedFS kann sich
    ebenso verhalten.
    """

    def head(self, key: str):
        objekt = super().head(key)
        if objekt is None:
            return None
        return objekt._replace(etag='"d41d8cd98f00b204e9800998ecf8427e-2"')


def tabelle_schreiben(storage: Storage, rel_dir: str, inhalt: bytes,
                      *, gebaut: str = "2026-09-15T10:00:00Z") -> None:
    lokal_schreiben(storage, f"{rel_dir}/part-0001.parquet", inhalt)
    lokal_schreiben(storage, f"{rel_dir}/manifest.json", json.dumps(
        {"status": "complete", "built_at_utc": gebaut}).encode())


def test_gleiche_groesse_ist_kein_beweis_fuer_gleichen_inhalt(tmp_path):
    """Der Befund der externen Pruefung: drei Bytes NEU galten als drei Bytes ALT.

    Liess sich das ETag nicht als MD5 lesen, genuegte die Byteanzahl fuer
    "identisch" - der Upload unterblieb, und oben blieb der alte Inhalt unter
    einem Manifest, das den neuen behauptete.
    """
    fake = EtagOhneMD5()
    config = Config(backend="s3", local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s")
    storage = Storage(config, fake)
    rel = "gold/dataset=fact_offense"
    tabelle_schreiben(storage, rel, b"NEU")
    fake.objekte[f"{rel}/part-0001.parquet"] = b"ALT"
    fake.objekte[f"{rel}/manifest.json"] = b'{"status": "complete"}'

    storage.publish_table(tmp_path / "data" / rel, erzwingen=True)
    assert fake.objekte[f"{rel}/part-0001.parquet"] == b"NEU", (
        "gleiche Groesse wurde wieder als gleicher Inhalt genommen"
    )


def test_gleicher_inhalt_ohne_pruefsumme_wird_nicht_erneut_geladen(tmp_path):
    """Die Gegenprobe: Der Download darf nur pruefen, nicht Arbeit erzeugen."""
    fake = EtagOhneMD5()
    config = Config(backend="s3", local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s")
    storage = Storage(config, fake)
    rel = "bronze/city=chicago/ingest_date=2026-09-15/run_x"
    lauf_schreiben(storage, rel)
    fake.objekte[f"{rel}/part-0001.parquet"] = b"PAR1"
    fake.objekte[f"{rel}/manifest.json"] = storage.local_path(f"{rel}/manifest.json").read_bytes()

    fake.uploads.clear()
    storage.publish_run(tmp_path / "data" / rel)
    assert fake.uploads == [], "identischer Inhalt wurde erneut hochgeladen"


def test_ein_abgebrochener_manifest_upload_laesst_keinen_gemischten_stand(tmp_path):
    """Der zweite Befund: neue Daten unter altem Manifest, weiterhin complete.

    ``manifest.json`` zuletzt schuetzt einen neuen Lauf, nicht eine bestehende
    Tabelle. Seit dem 15.9.2026 faellt zuerst der Status - ein Leser sieht
    danach den alten Stand, dann keinen, dann den neuen.
    """
    class ManifestFaelltAus(FakeS3Client):
        def put(self, key: str, daten: bytes) -> None:
            if key.endswith("manifest.json") and b'"publishing"' not in daten:
                raise OSError("Verbindung abgebrochen")
            super().put(key, daten)

    fake = ManifestFaelltAus()
    config = Config(backend="s3", local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s")
    storage = Storage(config, fake)
    rel = "gold/dataset=fact_offense"
    tabelle_schreiben(storage, rel, b"NEUER STAND")
    fake.objekte[f"{rel}/part-0001.parquet"] = b"ALTER STAND"
    fake.objekte[f"{rel}/manifest.json"] = json.dumps(
        {"status": "complete", "built_at_utc": "2026-08-01T10:00:00Z"}).encode()

    with pytest.raises(PublishError):
        storage.publish_table(tmp_path / "data" / rel, erzwingen=True)

    oben = json.loads(fake.objekte[f"{rel}/manifest.json"])
    assert oben["status"] == "publishing", (
        "das Manifest sagt weiterhin complete, obwohl die Daten schon neu sind"
    )
    assert storage.tabellen(("gold",)) == [], (
        "eine Tabelle mitten im Publizieren gilt weiterhin als gebaut"
    )


def test_scheitert_die_entwertung_bleibt_alles_unberuehrt(tmp_path):
    """Faellt schon der erste Schritt, darf keine Datei angefasst sein."""
    class EntwertungFaelltAus(FakeS3Client):
        def put(self, key: str, daten: bytes) -> None:
            if b'"publishing"' in daten:
                raise OSError("Verbindung abgebrochen")
            super().put(key, daten)

    fake = EntwertungFaelltAus()
    config = Config(backend="s3", local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s")
    storage = Storage(config, fake)
    rel = "gold/dataset=fact_offense"
    tabelle_schreiben(storage, rel, b"NEUER STAND")
    fake.objekte[f"{rel}/part-0001.parquet"] = b"ALTER STAND"
    fake.objekte[f"{rel}/manifest.json"] = json.dumps({"status": "complete"}).encode()

    with pytest.raises(PublishError, match="nichts angefasst"):
        storage.publish_table(tmp_path / "data" / rel, erzwingen=True)
    assert fake.objekte[f"{rel}/part-0001.parquet"] == b"ALTER STAND"
    assert json.loads(fake.objekte[f"{rel}/manifest.json"])["status"] == "complete"


def test_eine_neue_tabelle_wird_nicht_entwertet(tmp_path):
    """Oben liegt nichts - dann gibt es auch nichts zu entwerten."""
    storage, fake = ablage(tmp_path, "s3")
    rel = "gold/dataset=dim_date"
    tabelle_schreiben(storage, rel, b"ERSTER STAND")
    storage.publish_table(tmp_path / "data" / rel)
    assert json.loads(fake.objekte[f"{rel}/manifest.json"])["status"] == "complete"
    assert not any(b'"publishing"' in w for w in fake.objekte.values())


def test_eine_unfertige_tabelle_zaehlt_nicht_als_gebaut(tmp_path):
    """Derselbe Massstab wie bei Laeufen: Das Manifest sagt, ob es gilt."""
    storage, fake = ablage(tmp_path, "hybrid")
    lokal_schreiben(storage, "silver/dataset=tract/vintage=2024/manifest.json",
                    b'{"status": "publishing", "row_count": 3}')
    fake.put("gold/dataset=fact_offense/manifest.json",
             b'{"status": "complete", "row_count": 9}')
    assert [t.name for t in storage.tabellen()] == ["fact_offense"]


# --------------------------------------------------------------------------
# Loeschen (seit 4.10.2026)
#
# Das Protokoll kannte bis hierher ``head``, ``get``, ``put`` und ``list``.
# ``delete`` kam dazu, weil ``orchestration.aufraeumen`` seither auch
# Releases raeumt und die oben liegen (``docs/intern/datenhistorie.md`` 5.5).
# Fuer Laeufe und Tabellen gilt es nicht - die bleiben unveraenderlich.
# --------------------------------------------------------------------------


def test_das_protokoll_und_beide_klienten_kennen_delete():
    """Sonst waere eine Ablage ohne ``delete`` noch ein gueltiger S3Client.

    Geprueft wird das Protokoll selbst und beide Umsetzungen. Nicht ueber
    ``__protocol_attrs__`` - das gibt es erst ab Python 3.12, und die Suite
    laeuft auch auf 3.11.
    """
    from storage import S3Client
    from storage.backend import Boto3Client

    for traeger in (S3Client, Boto3Client, FakeS3Client):
        assert callable(getattr(traeger, "delete", None)), traeger.__name__


def test_der_fake_loescht_und_merkt_sich_was(tmp_path):
    _, fake = ablage(tmp_path, "s3")
    fake.put("releases/release=A/release.json", b"{}")
    fake.put("releases/release=B/release.json", b"{}")
    fake.delete("releases/release=A/release.json")
    assert sorted(fake.objekte) == ["releases/release=B/release.json"]
    assert fake.geloescht == ["releases/release=A/release.json"]


def test_der_fake_nimmt_einen_fehlenden_schluessel_hin(tmp_path):
    """Wie S3: DELETE auf einen fehlenden Schluessel ist 204, nicht 404.

    Daran haengt, dass ein abgebrochener Lauf wiederholbar ist.
    """
    _, fake = ablage(tmp_path, "s3")
    fake.delete("releases/release=gibtsnicht/release.json")
    assert fake.objekte == {}


def test_boto3_delete_ruft_delete_object():
    from storage.backend import Boto3Client

    client = Boto3Client(Config(backend="s3", s3_access_key="k", s3_secret_key="s"))
    gesehen = []

    class Mitschrift:
        def delete_object(self, **kw):
            gesehen.append((kw["Bucket"], kw["Key"]))
            return {}

    client._client = Mitschrift()
    client.delete("releases/release=A/release.json")
    assert gesehen == [("urban-crime", "releases/release=A/release.json")]


def test_boto3_delete_wird_bei_einem_aussetzer_wiederholt(monkeypatch):
    from botocore.exceptions import ClientError

    from storage import StorageError, backend
    from storage.backend import Boto3Client

    pausen = []
    monkeypatch.setattr(backend.time, "sleep", pausen.append)
    client = Boto3Client(Config(backend="s3", s3_access_key="k", s3_secret_key="s"))

    class Stur:
        def delete_object(self, **kw):
            raise ClientError({"Error": {"Code": "503"}}, "DeleteObject")

    client._client = Stur()
    with pytest.raises(StorageError, match="503"):
        client.delete("releases/release=A/release.json")
    assert len(pausen) == backend.VERSUCHE - 1


def test_entferne_oben_leert_ein_praefix_vollstaendig(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    for name in ("release.json", "gold/dataset=fact_offense/part-0001.parquet",
                 "serving/analyse.duckdb"):
        fake.put(f"releases/release=A/{name}", b"x")
    fake.put("releases/release=B/release.json", b"{}")
    fake.put("releases/AKTUELL.json", b"{}")

    weg = storage.entferne_oben("releases/release=A")
    assert len(weg) == 3
    assert sorted(fake.objekte) == ["releases/AKTUELL.json",
                                    "releases/release=B/release.json"]


def test_entferne_oben_laesst_lokal_alles_stehen(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    fake.put("releases/release=A/release.json", b"{}")
    lokal = lokal_schreiben(storage, "releases/release=A/release.json", b"{}")
    assert storage.entferne_oben("releases/release=A") == \
        ["releases/release=A/release.json"]
    assert lokal.is_file(), "entferne_oben raeumt nur oben"


def test_entferne_oben_trifft_kein_praefix_das_nur_fast_passt(tmp_path):
    """``release=2026-10-03`` darf ``release=2026-10-03T19-53-12Z`` nicht mitnehmen.

    Ohne den abschliessenden ``/`` waere das ein Praefixtreffer - und ein
    Release zu viel weg, ohne dass es jemand verlangt hat.
    """
    storage, fake = ablage(tmp_path, "hybrid")
    fake.put("releases/release=2026-10-03/release.json", b"{}")
    fake.put("releases/release=2026-10-03T19-53-12Z/release.json", b"{}")
    assert storage.entferne_oben("releases/release=2026-10-03") == \
        ["releases/release=2026-10-03/release.json"]
    assert "releases/release=2026-10-03T19-53-12Z/release.json" in fake.objekte


def test_entferne_oben_lehnt_ein_leeres_praefix_ab(tmp_path):
    """Ohne Praefix waere es der ganze Bucket."""
    storage, fake = ablage(tmp_path, "hybrid")
    fake.put("releases/release=A/release.json", b"{}")
    with pytest.raises(PublishError, match="braucht ein Praefix"):
        storage.entferne_oben("")
    assert fake.objekte


def test_zuletzt_schiebt_das_manifest_ans_ende(tmp_path):
    """Sortiert liegt ``release.json`` mitten drin: gold/ < release.json < serving/."""
    storage, fake = ablage(tmp_path, "hybrid")
    for name in ("gold/part-0001.parquet", "release.json", "serving/analyse.duckdb"):
        fake.put(f"releases/release=A/{name}", b"x")
    assert storage.entferne_oben("releases/release=A", zuletzt="release.json") == [
        "releases/release=A/gold/part-0001.parquet",
        "releases/release=A/serving/analyse.duckdb",
        "releases/release=A/release.json",
    ]


def test_entferne_oben_bricht_beim_ersten_fehler_ab(tmp_path):
    """Was weg ist, bleibt weg; der Rest bleibt stehen - und ist **auffindbar**.

    Entscheidend ist, dass ``release.json`` den Abbruch ueberlebt:
    ``release.liste`` erkennt ein Release nur daran. Ohne das Manifest waere
    das halb geleerte Praefix unsichtbar, und ein zweiter Lauf fuende es nicht
    mehr - die ``analyse.duckdb`` laege fuer immer oben.
    """
    class Zickig(FakeS3Client):
        def delete(self, key: str) -> None:
            if key.endswith("serving/analyse.duckdb"):
                raise RuntimeError("SeaweedFS lehnt ab")
            super().delete(key)

    fake = Zickig()
    storage = Storage(Config(backend="hybrid", local_root=tmp_path / "data",
                             s3_access_key="k", s3_secret_key="s"), fake)
    for name in ("gold/part-0001.parquet", "release.json", "serving/analyse.duckdb"):
        fake.put(f"releases/release=A/{name}", b"x")

    with pytest.raises(RuntimeError):
        storage.entferne_oben("releases/release=A", zuletzt="release.json")
    assert sorted(fake.objekte) == ["releases/release=A/release.json",
                                    "releases/release=A/serving/analyse.duckdb"]


def test_entferne_oben_geht_im_lokalen_modus_nicht(tmp_path):
    storage, _ = ablage(tmp_path, "local")
    storage._client = None          # kein untergeschobener Fake
    with pytest.raises(PublishError, match="kennt kein S3"):
        storage.entferne_oben("releases/release=A")


# --------------------------------------------------------------------------
# Die Byte-Summe ueber ein Praefix
# --------------------------------------------------------------------------
#
# Sie stand bis zum 4.10.2026 dreimal ausgeschrieben im Projekt und war jedes
# Mal nur im local-Modus richtig. Seither gibt es sie einmal, und hier stehen
# die Faelle, in denen die drei alten Fassungen falsch gerechnet haben.


def test_bytes_unter_zaehlt_lokal_ueber_st_size(tmp_path):
    storage, _ = ablage(tmp_path, "local")
    lokal_schreiben(storage, "bronze/city=chicago/run_a/part-0001.parquet", b"x" * 300)
    lokal_schreiben(storage, "bronze/city=chicago/run_a/manifest.json", b"y" * 40)
    assert storage.bytes_unter("bronze") == 340
    assert storage.bytes_unter("bronze/city=chicago/run_a") == 340


def test_bytes_unter_laesst_part_verzeichnisse_weg(tmp_path):
    """Ein abgebrochener Lauf ist nichts Veroeffentlichtes - und belegt nichts.

    Die drei ausgeschriebenen Fassungen nahmen ``rglob("*")`` und zaehlten
    ``.part`` mit.
    """
    storage, _ = ablage(tmp_path, "local")
    lokal_schreiben(storage, "silver/dataset=x/part-0001.parquet", b"x" * 100)
    lokal_schreiben(storage, "silver/.part-dataset=x/part-0001.parquet", b"x" * 9999)
    assert storage.bytes_unter("silver") == 100


def test_bytes_unter_ist_null_wo_nichts_liegt(tmp_path):
    """Eine Schicht, die es noch nicht gibt, belegt nichts - und bricht nicht."""
    storage, _ = ablage(tmp_path, "local")
    assert storage.bytes_unter("serving") == 0
    assert storage.groessen_unter("serving") == {}
    assert not (tmp_path / "data" / "serving").exists(), "messen legt nichts an"


def test_bytes_unter_nimmt_im_s3_modus_die_objektgroesse(tmp_path):
    storage, fake = ablage(tmp_path, "s3")
    fake.put("gold/dataset=fact_offense/part-0001.parquet", b"z" * 4096)
    assert storage.bytes_unter("gold") == 4096


def test_bytes_unter_zaehlt_im_hybridmodus_einmal_und_lokal_gewinnt(tmp_path):
    """Dieselbe Datei lokal und oben ist eine Datei - wie beim Lesen."""
    storage, fake = ablage(tmp_path, "hybrid")
    rel = "gold/dataset=fact_offense/part-0001.parquet"
    lokal_schreiben(storage, rel, b"x" * 100)
    fake.put(rel, b"z" * 4096)
    assert storage.bytes_unter("gold") == 100
    assert storage.groessen_unter("gold") == {rel: 100}


def test_bytes_unter_vereint_im_hybridmodus_beide_seiten(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    lokal_schreiben(storage, "gold/dataset=a/part-0001.parquet", b"x" * 100)
    fake.put("gold/dataset=b/part-0001.parquet", b"z" * 50)
    assert storage.bytes_unter("gold") == 150


def test_bytes_unter_sieht_mit_lokal_wahr_nur_die_platte(tmp_path):
    """Was von hier hochgehen muss, steht nicht oben - und im s3-Modus liest
    die Ablage gar nicht lokal."""
    storage, fake = ablage(tmp_path, "s3")
    lokal_schreiben(storage, "bronze/city=chicago/run_a/part-0001.parquet", b"x" * 70)
    fake.put("bronze/city=detroit/run_b/part-0001.parquet", b"z" * 4096)
    assert storage.bytes_unter("bronze") == 4096, "ohne lokal: der Bestand oben"
    assert storage.bytes_unter("bronze", lokal=True) == 70


def test_bytes_unter_versteht_ein_muster(tmp_path):
    storage, _ = ablage(tmp_path, "local")
    lokal_schreiben(storage, "bronze/city=chicago/run_a/part-0001.parquet", b"x" * 100)
    lokal_schreiben(storage, "bronze/city=chicago/run_a/manifest.json", b"y" * 10)
    assert storage.bytes_unter("bronze", "**/*.parquet") == 100


def test_bytes_unter_und_list_files_waehlen_dasselbe_aus(tmp_path):
    """Ein Unterschied zwischen beiden waere eine Dateizahl ohne ihre Bytes."""
    storage, fake = ablage(tmp_path, "hybrid")
    lokal_schreiben(storage, "silver/dataset=a/part-0001.parquet", b"x" * 100)
    lokal_schreiben(storage, "silver/.part-dataset=b/part-0001.parquet", b"x" * 5)
    fake.put("silver/dataset=c/part-0001.parquet", b"z" * 50)
    assert list(storage.groessen_unter("silver")) == storage.list_files("silver")


def test_die_schichtenliste_steht_kanonisch_in_storage():
    """Drei widersprechende Fassungen waren vorher - jetzt ist es eine.

    Geprueft wird **Gleichheit**, nicht Teilmenge: ``basis_je_jahrgang`` laeuft
    ueber ``LAUFSCHICHTEN``, ``TABELLENSCHICHTEN`` und ``releases`` und deckt
    damit genau dann alles ab, was ``belegung`` messen kann, wenn die drei
    ``SCHICHTEN`` erschoepfen. Eine siebte Schicht wuerde sonst gemessen und
    fiele still aus der Hochrechnung.
    """
    from storage import ABGELEITET, LAUFSCHICHTEN, SCHICHTEN, TABELLENSCHICHTEN
    from storage import release

    assert SCHICHTEN == ("raw", "bronze", "silver", "gold", "serving", "releases")
    assert (set(LAUFSCHICHTEN) | set(TABELLENSCHICHTEN) | {release.RELEASES}
            == set(SCHICHTEN)), (
        "die drei Teile, aus denen platzbedarf.basis_je_jahrgang besteht, "
        "deckten SCHICHTEN nicht mehr ab"
    )
    assert not set(LAUFSCHICHTEN) & set(TABELLENSCHICHTEN)
    assert release.RELEASES not in set(LAUFSCHICHTEN) | set(TABELLENSCHICHTEN)
    assert set(ABGELEITET) < set(TABELLENSCHICHTEN), \
        "ABGELEITET ist die engere Menge - nur dort ist der Standvergleich sinnvoll"


def test_die_drei_ausschnitte_kommen_aus_der_kanonischen_liste():
    """Sonst waeren es wieder drei Listen, die auseinanderlaufen koennen."""
    import storage.__main__ as cli
    from serving import build_analysis_db
    from storage import LAUFSCHICHTEN, TABELLENSCHICHTEN

    assert cli.SCHICHTEN == LAUFSCHICHTEN
    assert build_analysis_db.SCHICHTEN == TABELLENSCHICHTEN
