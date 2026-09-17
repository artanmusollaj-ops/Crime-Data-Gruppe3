"""Holen: Laeufe von SeaweedFS in die lokale Wurzel - geprueft und unteilbar.

Kein Test hier braucht SeaweedFS - S3 ist ``FakeS3Client``, ein dict.

Bis zum 17.9.2026 galt "kein automatisches Herunterladen". Fuer Silver und
Gold gilt das weiter; fuer Raw und Bronze nicht mehr: Laeufe sind
unveraenderlich, eine Kopie kann nicht veralten, und jeder Rechner soll den
ganzen Bestand haben. Was hier steht, ist die Zusage dazu: Manifest zuletzt,
Pruefsumme gegen das ETag, nichts Halbes auf der Platte.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from storage import Config, FakeS3Client, PublishError, Storage, StorageError


def ablage(tmp_path: Path, backend: str) -> tuple[Storage, FakeS3Client]:
    fake = FakeS3Client()
    config = Config(backend=backend, local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s")
    return Storage(config, fake), fake


def oben_lauf(fake: FakeS3Client, rel_dir: str, *, dateien: int = 2) -> None:
    for i in range(1, dateien + 1):
        fake.put(f"{rel_dir}/page-{i:04d}.json.gz", f"seite {i}".encode())
    fake.put(f"{rel_dir}/manifest.json",
             json.dumps({"status": "complete", "run_id": rel_dir.rsplit("/", 1)[-1]}).encode())


RAW = "raw/city=chicago/ingest_date=2026-09-06/run_A"
BRONZE = "bronze/city=chicago/ingest_date=2026-09-06/run_A"


# --------------------------------------------------------------------------
# Ein Objekt
# --------------------------------------------------------------------------


def test_ein_objekt_kommt_geprueft_herunter(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    fake.put(f"{RAW}/page-0001.json.gz", b"seite 1")
    ziel = storage.hole(f"{RAW}/page-0001.json.gz")
    assert ziel == tmp_path / "data" / RAW / "page-0001.json.gz"
    assert ziel.read_bytes() == b"seite 1"
    assert not list(ziel.parent.glob(".*")), "kein .part bleibt liegen"


def test_lokal_identisch_wird_nicht_erneut_geladen(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    fake.put(f"{RAW}/page-0001.json.gz", b"seite 1")
    storage.hole(f"{RAW}/page-0001.json.gz")
    geholt = []
    echt = fake.get
    fake.get = lambda key: geholt.append(key) or echt(key)
    storage.hole(f"{RAW}/page-0001.json.gz")
    assert geholt == [], "ein identisches Objekt wird nicht noch einmal geholt"


def test_lokal_anders_wird_ersetzt(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    fake.put(f"{RAW}/page-0001.json.gz", b"seite 1")
    lokal = tmp_path / "data" / RAW / "page-0001.json.gz"
    lokal.parent.mkdir(parents=True)
    lokal.write_bytes(b"seite X")   # gleiche Laenge, anderer Inhalt
    storage.hole(f"{RAW}/page-0001.json.gz")
    assert lokal.read_bytes() == b"seite 1"


def test_was_oben_fehlt_ist_ein_klarer_fehler(tmp_path):
    storage, _ = ablage(tmp_path, "hybrid")
    with pytest.raises(StorageError, match="nicht auf SeaweedFS"):
        storage.hole(f"{RAW}/gibt-es-nicht")


def test_local_kennt_kein_holen(tmp_path):
    storage, _ = ablage(tmp_path, "local")
    with pytest.raises(PublishError, match="kennt kein S3"):
        storage.hole(f"{RAW}/page-0001.json.gz")
    assert storage.fehlende_laeufe() == []


def test_eine_falsche_pruefsumme_laesst_nichts_auf_der_platte(tmp_path):
    """Das ETag sagt MD5 x, der Inhalt ist y - dann ist der Download kaputt."""
    storage, fake = ablage(tmp_path, "hybrid")
    fake.put(f"{RAW}/page-0001.json.gz", b"seite 1")
    echt = fake.head

    def luegt(key):
        o = echt(key)
        return o._replace(etag='"' + hashlib.md5(b"etwas anderes").hexdigest() + '"') if o else o

    fake.head = luegt
    with pytest.raises(StorageError, match="Pruefsumme"):
        storage.hole(f"{RAW}/page-0001.json.gz")
    assert not (tmp_path / "data" / RAW).exists()


# --------------------------------------------------------------------------
# Ein Lauf
# --------------------------------------------------------------------------


def test_ein_lauf_kommt_ganz_und_manifest_zuletzt(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    oben_lauf(fake, RAW, dateien=3)
    reihenfolge = []
    echt = fake.get
    fake.get = lambda key: reihenfolge.append(key) or echt(key)
    dateien = storage.hole_lauf(RAW)
    assert len(dateien) == 4
    assert reihenfolge[-1].endswith("/manifest.json")
    assert (tmp_path / "data" / RAW / "manifest.json").is_file()


def test_bricht_der_download_ab_gilt_der_lauf_nicht(tmp_path):
    """Ohne Manifest ist ein Verzeichnis kein Lauf - so wie beim Publizieren."""
    storage, fake = ablage(tmp_path, "hybrid")
    oben_lauf(fake, RAW, dateien=2)
    echt = fake.get

    def zweite_seite_kaputt(key):
        if key.endswith("page-0002.json.gz"):
            raise OSError("Verbindung weg")
        return echt(key)

    fake.get = zweite_seite_kaputt
    with pytest.raises(StorageError, match="Download fehlgeschlagen"):
        storage.hole_lauf(RAW)
    assert not (tmp_path / "data" / RAW / "manifest.json").exists()
    assert RAW in storage.fehlende_laeufe(("raw",)), "er zaehlt weiterhin als fehlend"


def test_versteckte_objekte_zaehlen_nicht(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    oben_lauf(fake, RAW)
    fake.put(f"{RAW}/.page-0009.json.gz.part", b"halb")
    storage.hole_lauf(RAW)
    assert not (tmp_path / "data" / RAW / ".page-0009.json.gz.part").exists()


# --------------------------------------------------------------------------
# Was fehlt
# --------------------------------------------------------------------------


def test_fehlende_laeufe_sind_die_ohne_lokales_manifest(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    oben_lauf(fake, RAW)
    oben_lauf(fake, BRONZE)
    oben_lauf(fake, "bronze/city=detroit/full/run_B")
    (tmp_path / "data" / BRONZE).mkdir(parents=True)
    (tmp_path / "data" / BRONZE / "manifest.json").write_text("{}")
    assert storage.fehlende_laeufe() == [RAW, "bronze/city=detroit/full/run_B"]
    assert storage.fehlende_laeufe(("bronze",)) == ["bronze/city=detroit/full/run_B"]


def test_hole_fehlende_laeufe_holt_raw_vor_bronze(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    oben_lauf(fake, BRONZE)
    oben_lauf(fake, RAW)
    geholt = storage.hole_fehlende_laeufe()
    assert geholt == [RAW, BRONZE]
    assert storage.fehlende_laeufe() == []
    assert storage.hole_fehlende_laeufe() == [], "ein zweites Mal gibt es nichts zu tun"


def test_s3_modus_holt_ebenso(tmp_path):
    """Im s3-Modus ist die lokale Kopie Arbeitsverzeichnis - holen geht trotzdem."""
    storage, fake = ablage(tmp_path, "s3")
    oben_lauf(fake, RAW)
    assert storage.hole_fehlende_laeufe(("raw",)) == [RAW]
    assert (tmp_path / "data" / RAW / "manifest.json").is_file()
