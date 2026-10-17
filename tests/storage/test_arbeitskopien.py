"""Der Aufschub des lokalen Aufraeumens - und seine zwei Grenzen.

Am 16.10.2026 war die Strecke auf ``srv01`` **gruen** und das Release
gescheitert: *"es fehlt: gold/dataset=fact_offense, ..."*, sieben Tabellen.
Alle lagen oben, keine unten. ``publish_table`` entfernt im Modus ``s3`` die
lokale Arbeitskopie sofort, ``storage.release.sammle`` liest aber das
Dateisystem - und die Modus-Tabelle in ``docs/storage-architektur.md`` sagt
fuer ``s3`` ausdruecklich *"lokal gebildet, hochgebracht, lokale Kopie
**danach** entfernt"*. Die Reihenfolge war beschrieben, nur nicht umgesetzt.

Kein Test hier braucht SeaweedFS - S3 ist ``FakeS3Client``, ein dict.
"""

from __future__ import annotations

import json
from pathlib import Path

from storage import Config, FakeS3Client, Storage


def ablage(tmp_path: Path, backend: str, *,
           keep_local: bool = False) -> tuple[Storage, FakeS3Client]:
    fake = FakeS3Client()
    config = Config(backend=backend, local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s",
                    keep_local=keep_local)
    return Storage(config, fake), fake


def lege_tabelle(storage: Storage, rel: str, *, zeilen: int = 3) -> Path:
    verzeichnis = storage.local_path(rel)
    verzeichnis.mkdir(parents=True, exist_ok=True)
    (verzeichnis / "part-0001.parquet").write_bytes(b"x" * zeilen)
    (verzeichnis / "manifest.json").write_text(
        json.dumps({"status": "complete", "row_count": zeilen}), encoding="utf-8")
    return verzeichnis


GOLD = "gold/dataset=fact_offense"


# --------------------------------------------------------------------------
# Der Aufschub
# --------------------------------------------------------------------------


def test_ohne_schalter_geht_die_kopie_wie_bisher_sofort_weg(tmp_path):
    storage, _ = ablage(tmp_path, "s3")
    verzeichnis = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)
    assert not verzeichnis.exists(), \
        "ohne Schalter bleibt das Verhalten, wie es war"


def test_mit_schalter_bleibt_die_kopie_liegen(tmp_path):
    """Genau das, was dem Release gefehlt hat."""
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    verzeichnis = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)
    assert (verzeichnis / "part-0001.parquet").is_file(), \
        "mit Schalter muss die Kopie bleiben - sonst findet sammle() nichts"


def test_der_schalter_haelt_keinen_lauf_lokal(tmp_path):
    """Die erste Grenze: nur Tabellen, nie Laeufe.

    Ein Lauf ist unveraenderlich und jederzeit wieder zu holen. Ihn lokal zu
    behalten haeuft nur an - 141 Bronze-Laeufe waren der Grund, warum der
    Silver-Bau erstickte. Auch ein global gesetzter Schalter darf das nicht
    koennen.
    """
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    rel = "bronze/city=chicago/ingest_date=2026-10-16/run_A"
    verzeichnis = storage.local_path(rel)
    verzeichnis.mkdir(parents=True)
    (verzeichnis / "part-0001.parquet").write_bytes(b"x")
    (verzeichnis / "manifest.json").write_text('{"status": "complete"}',
                                               encoding="utf-8")
    storage.publish_run(rel)
    assert not verzeichnis.exists(), (
        "ein Lauf darf den Schalter nicht sehen - sonst haeuft sich Bronze "
        "lokal an, und genau daran ist der Silver-Bau erstickt")


# --------------------------------------------------------------------------
# Das Nachraeumen
# --------------------------------------------------------------------------


def test_nach_dem_release_gehen_die_aufgeschobenen_kopien_weg(tmp_path):
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    gold = lege_tabelle(storage, GOLD)
    silber = lege_tabelle(storage, "silver/dataset=crime_offense")
    storage.publish_table(GOLD)
    storage.publish_table("silver/dataset=crime_offense")

    weg = storage.arbeitskopien_entfernen()

    assert sorted(weg) == ["gold/dataset=fact_offense",
                           "silver/dataset=crime_offense"]
    assert not gold.exists() and not silber.exists()


def test_was_oben_fehlt_bleibt_liegen(tmp_path):
    """Die zweite Grenze, und die wichtigere.

    Eine Tabelle, deren Upload scheiterte, liegt nur lokal. Sie hier zu
    entfernen hiesse, sie zu verlieren - der Unterschied zwischen Aufraeumen
    und Datenverlust. Er kostet eine Abfrage je Tabelle.
    """
    storage, fake = ablage(tmp_path, "s3", keep_local=True)
    gold = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)
    # Der Upload sei misslungen: Oben liegt nichts.
    for schluessel in list(fake.objekte):
        if schluessel.startswith(GOLD):
            del fake.objekte[schluessel]

    weg = storage.arbeitskopien_entfernen()

    assert weg == [], "was oben fehlt, darf hier nicht verschwinden"
    assert (gold / "part-0001.parquet").is_file()


def test_ausserhalb_von_s3_raeumt_es_nichts_weg(tmp_path):
    """In ``local`` gibt es kein Oben, in ``hybrid`` ist die Kopie der Bestand."""
    for backend in ("local", "hybrid"):
        storage, _ = ablage(tmp_path / backend, backend, keep_local=True)
        verzeichnis = lege_tabelle(storage, GOLD)
        if backend == "hybrid":
            storage.publish_table(GOLD)
        assert storage.arbeitskopien_entfernen() == []
        assert verzeichnis.exists(), f"{backend}: die Kopie ist der Bestand"
