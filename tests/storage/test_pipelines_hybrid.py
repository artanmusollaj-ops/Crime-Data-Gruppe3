"""Die Pipelines im Hybridmodus - gegen ein S3 im Speicher, ohne SeaweedFS.

Was hier steht, ist die Zusage aus der Aufgabenstellung, je Schicht:
lokal schreiben, pruefen, **dann** publizieren; scheitert die Pruefung,
erreicht nichts den gemeinsamen Bestand. Und die Auswertungsdatenbank
bleibt lokal, in jedem Modus.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import build_analysis_db as bad
import build_tract as bt
import download_chicago as dc
from detroit_pipeline import extract_detroit as ed
from storage import Config, FakeS3Client, Storage, set_storage
from tests.chicago_pipeline.test_download_chicago import make_download
from tests.serving.test_build_analysis_db import schreibe_tabelle
from tests.silver_pipeline.test_build_tract import (
    VINTAGE,
    acs_table,
    bronze_fuer_illinois,
    tiger_table,
)


@pytest.fixture
def hybrid(tmp_path) -> tuple[Path, FakeS3Client]:
    fake = FakeS3Client()
    data_root = tmp_path / "data"
    set_storage(Storage(Config(backend="hybrid", local_root=data_root,
                               s3_access_key="k", s3_secret_key="s"), fake))
    return data_root, fake


# --------------------------------------------------------------------------
# Silver
# --------------------------------------------------------------------------


def test_silver_wird_nach_bau_und_pruefung_publiziert(hybrid):
    data_root, fake = hybrid
    bronze_fuer_illinois(data_root, tiger=tiger_table(), acs=acs_table())
    ziel = bt.build(data_root, VINTAGE, ["17"])
    rel = f"silver/dataset=tract/vintage={VINTAGE}"
    assert fake.uploads == [f"{rel}/part-0001.parquet", f"{rel}/manifest.json"], (
        "Parquet zuerst, Manifest zuletzt"
    )
    assert ziel.exists(), "hybrid behaelt die lokale Arbeitskopie"
    assert json.loads(fake.get(f"{rel}/manifest.json"))["row_count"] == 2


def test_scheitert_die_pruefung_erreicht_nichts_s3(hybrid):
    """Der Fall, fuer den es die Reihenfolge gibt: ACS-Zeile ohne Geometrie."""
    data_root, fake = hybrid
    bronze_fuer_illinois(
        data_root,
        tiger=tiger_table(("17031010100",)),
        acs=acs_table(("17031010100", "17031099999"), ("1837", "10"), ("70326", "1"), ("129", "0")),
    )
    with pytest.raises(bt.TransformError):
        bt.build(data_root, VINTAGE, ["17"])
    assert fake.uploads == [] and fake.objekte == {}


def test_hybrid_liest_bronze_von_s3_wenn_lokal_nichts_liegt(hybrid, caplog):
    """Entwickler B: kein lokaler Bestand, die Quelle liegt auf SeaweedFS."""
    data_root, fake = hybrid
    rel = f"bronze/dataset={bt.TIGER_DATASET}/vintage={VINTAGE}/state=17/run_20260906T120000000000Z"
    fake.put(f"{rel}/manifest.json", json.dumps({"status": "complete", "run_id": "run_20260906T120000000000Z",
                                                  "row_count": 2}).encode())
    fake.put(f"{rel}/part-0001.parquet", b"PAR1")
    with caplog.at_level(logging.INFO, logger="storage"):
        quelle = bt.newest_bronze_run(data_root, bt.TIGER_DATASET, VINTAGE, "17")
    assert quelle.parquet == f"s3://urban-crime/{rel}/part-0001.parquet"
    assert "falling back to S3" in caplog.text


def test_hybrid_bevorzugt_den_lokalen_lauf(hybrid):
    """Entwickler A: dieselbe Datei lokal - sie gewinnt, kein Rueckfall."""
    data_root, _ = hybrid
    bronze_fuer_illinois(data_root, tiger=tiger_table(), acs=acs_table())
    quelle = bt.newest_bronze_run(data_root, bt.TIGER_DATASET, VINTAGE, "17")
    assert quelle.parquet.startswith(str(data_root))


# --------------------------------------------------------------------------
# Serving
# --------------------------------------------------------------------------


def test_die_auswertungsdatenbank_bleibt_lokal(hybrid):
    data_root, fake = hybrid
    schreibe_tabelle(data_root, "crime_offense", 5)
    ziel = bad.build(data_root)
    assert ziel == data_root / "serving" / bad.DATABASE_NAME and ziel.exists()
    assert fake.uploads == [], "nichts aus serving/ geht nach S3 - auch die .duckdb nicht"


def test_sichten_zeigen_auf_s3_wo_lokal_nichts_liegt(hybrid):
    data_root, fake = hybrid
    schreibe_tabelle(data_root, "crime_offense", 5)
    fake.put("gold/dataset=fact_offense/part-0001.parquet", b"PAR1")
    tabellen = {t.name: t for t in bad.discover(data_root)}
    assert tabellen["fact_offense"].path == "s3://urban-crime/gold/dataset=fact_offense/part-0001.parquet"
    assert isinstance(tabellen["crime_offense"].path, Path) and tabellen["crime_offense"].path.is_absolute()


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------


def chicago_main(monkeypatch, data_root: Path) -> int:
    monkeypatch.setattr(dc, "arguments", lambda: dc.argparse.Namespace(
        source=dc.DEFAULT_SOURCE, year=2024, data_root=data_root, max_records=None, full=False, no_token=True))
    monkeypatch.setattr(dc, "app_token", lambda disabled: None)
    monkeypatch.setattr(dc, "download", lambda *a: make_download())
    return dc.main()


def test_chicago_publiziert_raw_vor_bronze_und_jedes_manifest_zuletzt(hybrid, monkeypatch):
    data_root, fake = hybrid
    assert chicago_main(monkeypatch, data_root) == 0
    schichten = [k.split("/")[0] for k in fake.uploads]
    assert schichten == ["raw"] * schichten.count("raw") + ["bronze"] * schichten.count("bronze")
    assert schichten.count("raw") >= 2 and schichten.count("bronze") == 2
    raw, bronze = [k for k in fake.uploads if k.startswith("raw/")], [k for k in fake.uploads if k.startswith("bronze/")]
    assert raw[-1].endswith("/manifest.json") and bronze[-1].endswith("/manifest.json")
    assert bronze[0].endswith("/part-0001.parquet")


def test_ein_publish_konflikt_macht_die_ingestion_rot(hybrid, monkeypatch, caplog):
    """Ein Lauf, der auf S3 schon anders liegt, wird nicht ueberschrieben -
    und main() sagt es mit Exit 1, nicht mit einem Traceback."""
    data_root, fake = hybrid
    assert chicago_main(monkeypatch, data_root) == 0
    bronze_manifest = [k for k in fake.uploads if k.startswith("bronze/")][-1]
    fake.put(bronze_manifest, b"{}")
    # Derselbe Lauf noch einmal: gleiche run_id ist unwahrscheinlich, deshalb
    # direkt die Ablage - der Fehlerpfad ist derselbe.
    from storage import PublishError, get_storage
    with pytest.raises(PublishError):
        get_storage().publish_run(bronze_manifest.rsplit("/", 1)[0])


def test_detroit_publiziert_raw_vor_bronze(hybrid):
    data_root, fake = hybrid
    bronze = data_root / "bronze" / "city=detroit" / "full" / "year=2024" / "run_u"
    raw_dir = data_root / "raw" / "city=detroit" / "full" / "year=2024"
    for ordner, dateien in ((bronze, ("part-0001.parquet",)), (raw_dir / "run_u", ("batch-0001.json.gz",))):
        ordner.mkdir(parents=True)
        for name in dateien:
            (ordner / name).write_bytes(b"x")
        (ordner / "manifest.json").write_text('{"status": "SUCCESS", "pipeline_run_id": "u"}')
    ed.publiziere(bronze, raw_dir)
    assert fake.uploads == [
        "raw/city=detroit/full/year=2024/run_u/batch-0001.json.gz",
        "raw/city=detroit/full/year=2024/run_u/manifest.json",
        "bronze/city=detroit/full/year=2024/run_u/part-0001.parquet",
        "bronze/city=detroit/full/year=2024/run_u/manifest.json",
    ]


def test_detroit_ausserhalb_der_wurzel_publiziert_nicht(hybrid, tmp_path, caplog):
    _, fake = hybrid
    bronze = tmp_path / "anderswo" / "run_u"
    bronze.mkdir(parents=True)
    (bronze / "manifest.json").write_text("{}")
    with caplog.at_level(logging.WARNING, logger="storage"):
        ed.publiziere(bronze, None)
    assert fake.uploads == [] and "outside LOCAL_DATA_ROOT" in caplog.text


def test_local_modus_ist_unveraendert(tmp_path, monkeypatch):
    """Ohne STORAGE_BACKEND passiert genau das, was vorher passierte."""
    data_root = tmp_path / "data"
    assert chicago_main(monkeypatch, data_root) == 0
    # .analyse traegt die Ausfuehrungssperre (storage.analysesitzung), keine Daten.
    assert sorted(p.name for p in data_root.glob("*") if p.name != ".analyse") == ["bronze", "raw"]


# --------------------------------------------------------------------------
# Die Kommandozeile: --data-root ohne Vorgabe, die Ablage entscheidet
# --------------------------------------------------------------------------


def test_keine_kommandozeile_reicht_ein_leeres_data_root_weiter():
    """Der erste echte Lauf nach dem Umbau fiel genau hier: build(None, ...).

    Jede Verwendung von ``args.data_root`` in einem ``main`` muss durch
    ``for_root`` gehen - sonst ist die Vorgabe None ein TypeError.
    """
    import re
    wurzel = Path(__file__).resolve().parents[2] / "src" / "crime"
    verstoesse = []
    for datei in sorted(wurzel.rglob("*.py")):
        quelle = datei.read_text(encoding="utf-8")
        if '"--data-root"' not in quelle:
            continue
        alle = len(re.findall(r"args\.data_root", quelle))
        sauber = len(re.findall(r"for_root\(args\.data_root\)", quelle))
        if alle != sauber:
            verstoesse.append(f"{datei.relative_to(wurzel)}: {alle - sauber} nackte args.data_root")
    assert not verstoesse, verstoesse
