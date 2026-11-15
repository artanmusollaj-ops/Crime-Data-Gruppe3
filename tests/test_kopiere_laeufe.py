"""Tests fuer ``tools/kopiere_laeufe.py`` (FR-47, der Kopierschritt).

Zwei Eimer als ``FakeS3Client``. Im Quelleimer ein Release, dessen Herkunft
die Laeufe so nennt wie die echten Manifeste: Listen unter
``chicago_bronze_runs`` / ``detroit_bronze_runs`` (Detroit nur mit UUID) und
Eintraege mit ``layer`` und ``run_id`` (Census), verschachtelt in
``derived_from``. Daneben liegen Laeufe, die das Release **nicht** nennt -
genau sie duerfen nicht mitkommen.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from storage import Config, FakeS3Client, Storage

PROJEKT = Path(__file__).resolve().parents[1]
WERKZEUG = PROJEKT / "tools" / "kopiere_laeufe.py"
RELEASE = "2026-11-14T09-09-47Z"


def werkzeug():
    spec = importlib.util.spec_from_file_location("kopiere_laeufe", WERKZEUG)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


kl = werkzeug()

CHICAGO = "bronze/city=chicago/ingest_date=2026-11-10/run_20261110T125951603079Z"
DETROIT = "bronze/city=detroit/full/year=2021/run_bca68e85-bcce-4949-b6a8-2d15df81d192"
TRACT = "bronze/dataset=tiger_tract/vintage=2024/state=17/run_20260906T121504814962Z"
WETTER = "bronze/dataset=noaa_ghcnd/station=USW00094846/run_20261101T000000000000Z"
FREMD = "bronze/city=chicago/ingest_date=2026-11-03/run_20261103T000000000000Z"
ROH = "raw/city=chicago/ingest_date=2026-11-10/run_20261110T125951603079Z"

HERKUNFT_FAKT = [{
    "layer": "silver", "table": "crime_offense",
    "derived_from": {
        "chicago_bronze_runs": ["run_20261110T125951603079Z"],
        "detroit_bronze_runs": ["bca68e85-bcce-4949-b6a8-2d15df81d192"],
        "silver_tract": {"derived_from": [
            {"layer": "bronze", "dataset": "tiger_tract", "state_fips": "17",
             "run_id": "run_20260906T121504814962Z"}]},
    },
}]
HERKUNFT_WETTER = [{"layer": "silver", "table": "weather_day", "derived_from": [
    {"layer": "bronze", "dataset": "noaa_ghcnd", "run_id": "run_20261101T000000000000Z"}]}]


class Protokoll(FakeS3Client):
    """Merkt sich die Reihenfolge der Schreibzugriffe und jedes Loeschen."""

    def __init__(self) -> None:
        super().__init__()
        self.geschrieben: list[str] = []
        self.geloescht: list[str] = []

    def put(self, key: str, daten: bytes) -> None:
        self.geschrieben.append(key)
        super().put(key, daten)

    def delete(self, key: str) -> None:
        self.geloescht.append(key)
        super().delete(key)


def ablage(client: FakeS3Client, bucket: str, endpoint: str) -> Storage:
    return Storage(Config(backend="s3", local_root=Path("unbenutzt"), s3_endpoint=endpoint,
                          s3_bucket=bucket, s3_access_key="k", s3_secret_key="g"), client)


def quelle(*, herkunft_wetter=HERKUNFT_WETTER, ohne=()) -> Storage:
    client = FakeS3Client()
    rel = f"releases/release={RELEASE}"
    client.put(f"{rel}/gold/dataset=fact_offense/manifest.json",
               json.dumps({"derived_from": HERKUNFT_FAKT}).encode())
    client.put(f"{rel}/gold/dataset=dim_city_day/manifest.json",
               json.dumps({"derived_from": herkunft_wetter}).encode())
    client.put(f"{rel}/release.json", json.dumps({
        "release_id": RELEASE, "derived_from": HERKUNFT_FAKT,
        "files": {"gold/dataset=fact_offense/manifest.json": {"sha256": "x"},
                  "gold/dataset=fact_offense/part-0001.parquet": {"sha256": "y"},
                  "gold/dataset=dim_city_day/manifest.json": {"sha256": "z"}}}).encode())
    client.put("releases/AKTUELL.json", json.dumps({"release_id": RELEASE}).encode())
    for lauf in (CHICAGO, DETROIT, TRACT, WETTER, FREMD, ROH):
        if lauf in ohne:
            continue
        client.put(f"{lauf}/part-0001.parquet", f"daten {lauf}".encode())
        client.put(f"{lauf}/manifest.json", f"manifest {lauf}".encode())
    return ablage(client, "urban-crime", "s3.example.org")


def ziel() -> Storage:
    return ablage(Protokoll(), "urbancrime-probe-1", "storage.googleapis.com")


def lauf(capsys, von, nach, *argv):
    code = kl.main(["--release", RELEASE, *argv], von=von, nach=nach)
    ausgabe = capsys.readouterr()
    return code, ausgabe.out, ausgabe.err


def oben(storage: Storage) -> set[str]:
    return {o.key for o in storage.client.list("")}


def test_genau_die_genannten_laeufe_kommen_hinueber(capsys):
    von, nach = quelle(), ziel()
    code, aus, _ = lauf(capsys, von, nach)
    assert code == 0, aus
    erwartet = {f"{v}/{d}" for v in (CHICAGO, DETROIT, TRACT, WETTER)
                for d in ("part-0001.parquet", "manifest.json")}
    assert oben(nach) == erwartet
    assert "4 Laeufe genannt, 4 Laufverzeichnisse gefunden" in aus


def test_das_manifest_kommt_je_lauf_zuletzt(capsys):
    von, nach = quelle(), ziel()
    lauf(capsys, von, nach)
    geschrieben = nach.client.geschrieben
    for verz in (CHICAGO, DETROIT, TRACT, WETTER):
        assert (geschrieben.index(f"{verz}/part-0001.parquet")
                < geschrieben.index(f"{verz}/manifest.json"))


def test_ein_zweiter_lauf_ueberspringt_alles(capsys):
    von, nach = quelle(), ziel()
    lauf(capsys, von, nach)
    vorher = list(nach.client.geschrieben)
    code, aus, _ = lauf(capsys, von, nach)
    assert code == 0
    assert nach.client.geschrieben == vorher
    assert "0 Objekte kopiert, 8 schon gleich." in aus


def test_andere_bytes_im_ziel_werden_nie_ueberschrieben(capsys):
    von, nach = quelle(), ziel()
    nach.client.put(f"{CHICAGO}/part-0001.parquet", b"anders")
    code, _, err = lauf(capsys, von, nach)
    assert code == 1 and "anderen Bytes" in err
    assert nach.client.get(f"{CHICAGO}/part-0001.parquet") == b"anders"


def test_geloescht_wird_nie(capsys):
    von, nach = quelle(), ziel()
    nach.client.put("bronze/city=detroit/full/year=2022/run_alt/manifest.json", b"alt")
    lauf(capsys, von, nach)
    assert nach.client.geloescht == []
    assert "bronze/city=detroit/full/year=2022/run_alt/manifest.json" in oben(nach)


def test_raw_nur_wenn_die_herkunft_es_nennt(capsys):
    von, nach = quelle(herkunft_wetter=[*HERKUNFT_WETTER, {
        "layer": "raw", "run_id": "run_20261110T125951603079Z"}]), ziel()
    code, _, _ = lauf(capsys, von, nach)
    assert code == 0
    assert f"{ROH}/manifest.json" in oben(nach)
    von, nach = quelle(), ziel()
    lauf(capsys, von, nach)
    assert not [k for k in oben(nach) if k.startswith("raw/")]


def test_ein_fehlender_lauf_ist_exit_1(capsys):
    von, nach = quelle(ohne=(DETROIT,)), ziel()
    code, aus, _ = lauf(capsys, von, nach)
    assert code == 1
    assert "bronze/run_bca68e85-bcce-4949-b6a8-2d15df81d192" in aus


def test_ein_lauf_ohne_manifest_ist_kein_fertiger(capsys):
    von, nach = quelle(), ziel()
    von.client.delete(f"{TRACT}/manifest.json")
    code, aus, _ = lauf(capsys, von, nach)
    assert code == 1 and "kein fertiger Lauf" in aus
    assert not [k for k in oben(nach) if k.startswith(TRACT)]


def test_trocken_schreibt_nichts(capsys):
    von, nach = quelle(), ziel()
    code, aus, _ = lauf(capsys, von, nach, "--trocken")
    assert code == 0 and "8 Objekte zu kopieren" in aus
    assert nach.client.geschrieben == []


def test_derselbe_eimer_wird_abgelehnt(capsys):
    von = quelle()
    code, _, err = lauf(capsys, von, von)
    assert code == 1 and "derselbe Eimer" in err


def test_die_laeufe_werden_aus_allen_formen_gelesen():
    gefunden = kl.laeufe_in({"derived_from": HERKUNFT_FAKT + HERKUNFT_WETTER})
    assert gefunden == {
        ("bronze", "run_20261110T125951603079Z"),
        ("bronze", "run_bca68e85-bcce-4949-b6a8-2d15df81d192"),
        ("bronze", "run_20260906T121504814962Z"),
        ("bronze", "run_20261101T000000000000Z"),
    }


def test_die_vorgaben_zeigen_ins_schluesselverzeichnis():
    """Entscheid vom 15.11.2026: nie ins Repository-Verzeichnis."""
    for pfad in (kl.VORGABE_VON, kl.VORGABE_NACH):
        assert pfad.parent == Path.home() / ".config" / "urbancrime-probe"
