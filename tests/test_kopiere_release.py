"""Tests fuer ``tools/kopiere_release.py`` (Kibana in Google Cloud, Entscheid vom 15.11.2026).

Zwei Eimer als ``FakeS3Client``. Im Quelleimer ein Release mit echten
SHA-256 in ``release.json`` und ``AKTUELL.json`` darauf; daneben ein
zweites, das nicht das aktuelle ist. Geprueft wird, was der Plan verlangt:
kopieren und den Zeiger umlegen, identische Dateien ueberspringen,
abweichende ablehnen, denselben Eimer ablehnen, ``--trocken`` schreibt nichts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from storage import Config, FakeS3Client, Storage

PROJEKT = Path(__file__).resolve().parents[1]
WERKZEUG = PROJEKT / "tools" / "kopiere_release.py"
AKTUELL = "2026-11-14T09-09-47Z"
ALT = "2026-11-07T03-30-00Z"


def werkzeug():
    spec = importlib.util.spec_from_file_location("kopiere_release", WERKZEUG)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


kr = werkzeug()


def ablage(client: FakeS3Client, bucket: str, endpoint: str) -> Storage:
    return Storage(Config(backend="s3", local_root=Path("unbenutzt"), s3_endpoint=endpoint,
                          s3_bucket=bucket, s3_access_key="k", s3_secret_key="g"), client)


def dateien(kennung: str) -> dict[str, bytes]:
    return {
        "gold/dataset=fact_offense/part-0001.parquet": f"fakt {kennung}".encode(),
        "gold/dataset=fact_offense/manifest.json": f"manifest {kennung}".encode(),
        "serving/analyse.duckdb": f"datenbank {kennung}".encode(),
    }


def release_json(kennung: str) -> bytes:
    return json.dumps({
        "release_id": kennung, "created_at_utc": "2026-11-14T09:09:47Z", "bytes": 42,
        "files": {pfad: {"sha256": hashlib.sha256(daten).hexdigest(), "bytes": len(daten)}
                  for pfad, daten in dateien(kennung).items()},
    }).encode()


def quelle() -> Storage:
    client = FakeS3Client()
    for kennung in (AKTUELL, ALT):
        rel = f"releases/release={kennung}"
        for pfad, daten in dateien(kennung).items():
            client.put(f"{rel}/{pfad}", daten)
        client.put(f"{rel}/release.json", release_json(kennung))
    client.put("releases/AKTUELL.json", json.dumps({"release_id": AKTUELL}).encode())
    return ablage(client, "urban-crime", "s3.example.org")


class Lesezaehler(FakeS3Client):
    """Merkt sich jeden gelesenen Schluessel."""

    def __init__(self) -> None:
        super().__init__()
        self.gelesen: list[str] = []

    def get(self, key: str) -> bytes:
        self.gelesen.append(key)
        return super().get(key)


def ziel() -> Storage:
    return ablage(Lesezaehler(), "urbancrime-probe-1", "storage.googleapis.com")


def oben(storage: Storage) -> set[str]:
    return {o.key for o in storage.client.list("")}


def lauf(capsys, von, nach, *argv, release="aktuell"):
    code = kr.main(["--release", release, *argv], von=von, nach=nach)
    ausgabe = capsys.readouterr()
    return code, ausgabe.out, ausgabe.err


def zeiger(storage: Storage) -> str:
    return json.loads(storage.client.get("releases/AKTUELL.json"))["release_id"]


def test_das_aktuelle_release_kommt_hinueber_und_wird_dort_aktuell(capsys):
    von, nach = quelle(), ziel()
    code, _, err = lauf(capsys, von, nach)
    assert code == 0, err
    rel = f"releases/release={AKTUELL}"
    erwartet = {f"{rel}/{p}" for p in dateien(AKTUELL)} | {f"{rel}/release.json",
                                                         "releases/AKTUELL.json"}
    assert oben(nach) == erwartet, "nur das aktuelle Release, nicht das alte"
    assert zeiger(nach) == AKTUELL
    for pfad, daten in dateien(AKTUELL).items():
        assert nach.client.get(f"{rel}/{pfad}") == daten
    assert nach.client.get(f"{rel}/release.json") == von.client.get(f"{rel}/release.json")


def test_ein_genanntes_release_statt_des_aktuellen(capsys):
    von, nach = quelle(), ziel()
    code, _, err = lauf(capsys, von, nach, release=ALT)
    assert code == 0, err
    assert zeiger(nach) == ALT


def test_ein_zweiter_lauf_tut_nichts(capsys):
    von, nach = quelle(), ziel()
    assert lauf(capsys, von, nach)[0] == 0
    vorher = len(nach.client.uploads)
    code, aus, _ = lauf(capsys, von, nach)
    assert code == 0
    assert "Nichts zu tun" in aus
    assert len(nach.client.uploads) == vorher, "ein zweiter Lauf hat geschrieben"


def test_ein_vorhandenes_release_wird_nicht_geladen(capsys):
    """Ein zweites ``--nur-kibana`` mit demselben Release liest im Ziel nur
    ``release.json`` und ``AKTUELL.json`` - keine Datendatei."""
    von, nach = quelle(), ziel()
    assert lauf(capsys, von, nach)[0] == 0
    nach.client.gelesen.clear()
    code, aus, _ = lauf(capsys, von, nach)
    assert code == 0 and "Nichts zu tun" in aus
    erlaubt = {f"releases/release={AKTUELL}/release.json", "releases/AKTUELL.json"}
    assert set(nach.client.gelesen) <= erlaubt, nach.client.gelesen


def test_gleiche_groesse_aber_andere_bytes_faellt_ohne_release_json_auf(capsys):
    von, nach = quelle(), ziel()
    rel = f"releases/release={AKTUELL}"
    teil = "gold/dataset=fact_offense/part-0001.parquet"
    original = dateien(AKTUELL)[teil]
    nach.client.put(f"{rel}/{teil}", bytes(reversed(original)))
    code, _, err = lauf(capsys, von, nach)
    assert code == 1 and "anderen Bytes" in err


def test_identische_dateien_werden_uebersprungen(capsys):
    """Ein halb kopiertes Release (ohne release.json) wird ergaenzt."""
    von, nach = quelle(), ziel()
    rel = f"releases/release={AKTUELL}"
    teil = "gold/dataset=fact_offense/part-0001.parquet"
    nach.client.put(f"{rel}/{teil}", dateien(AKTUELL)[teil])
    vorher = list(nach.client.uploads)
    code, aus, err = lauf(capsys, von, nach)
    assert code == 0, err
    assert "1 schon gleich" in aus
    neu = nach.client.uploads[len(vorher):]
    assert f"{rel}/{teil}" not in neu, "eine identische Datei wurde erneut geschrieben"
    assert zeiger(nach) == AKTUELL


def test_eine_abweichende_datei_wird_abgelehnt_und_nichts_geschrieben(capsys):
    von, nach = quelle(), ziel()
    rel = f"releases/release={AKTUELL}"
    nach.client.put(f"{rel}/serving/analyse.duckdb", b"andere Bytes")
    vorher = set(oben(nach))
    code, _, err = lauf(capsys, von, nach)
    assert code == 1
    assert "anderen Bytes" in err and "unveraenderlich" in err
    assert oben(nach) == vorher
    assert nach.client.get(f"{rel}/serving/analyse.duckdb") == b"andere Bytes"


def test_derselbe_eimer_wird_abgelehnt(capsys):
    von = quelle()
    code, _, err = lauf(capsys, von, von)
    assert code == 1 and "derselbe Eimer" in err


def test_ohne_aktuell_json_bricht_es_mit_hinweis_ab(capsys):
    """I/O-Matrix "Release fehlt": kein Zeiger im Quelleimer."""
    von, nach = quelle(), ziel()
    von.client.delete("releases/AKTUELL.json")
    code, _, err = lauf(capsys, von, nach)
    assert code == 1 and "AKTUELL.json" in err
    assert not oben(nach)


def test_trocken_schreibt_nichts(capsys):
    von, nach = quelle(), ziel()
    code, aus, err = lauf(capsys, von, nach, "--trocken")
    assert code == 0, err
    assert "[trocken]" in aus and "4 Datei(en) fehlen" in aus
    assert not oben(nach)


def test_trocken_meldet_eine_abweichung_auch(capsys):
    von, nach = quelle(), ziel()
    nach.client.put(f"releases/release={AKTUELL}/release.json", b"{}")
    code, _, err = lauf(capsys, von, nach, "--trocken")
    assert code == 1 and "anders als" in err


def test_die_vorgaben_sind_die_beiden_env_dateien_der_probe():
    hilfe = kr.__doc__
    assert kr.VORGABE_VON.name == "quelle.env" and kr.VORGABE_NACH.name == "hmac.env"
    assert "urbancrime-probe" in str(kr.VORGABE_VON) and "--nur-kibana" in hilfe
