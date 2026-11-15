"""Tests fuer ``tools/vergleiche_releases.py`` (FR-47).

Zwei Eimer als ``FakeS3Client``, je mit einem ``release.json``, wie
``storage.release.release_manifest`` es schreibt: ``tables`` mit dem
Eingabe-Abdruck je Tabelle, ``files`` mit der SHA-256 je Datei. Gelesen wird
nichts anderes - der echte Vergleich gegen srv01 und Cloud Storage steht im
Beleg in ``docs/intern/AENDERUNGEN.md``, sobald er gelaufen ist. Hier geht es
um die Zeile "Vergleich" der I/O-Matrix im Plan: Abdruck gleich,
Pruefsumme gleich oder ungleich mit Grund, Exit 1 bei Abdruckabweichung.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from storage import Config, FakeS3Client, Storage

PROJEKT = Path(__file__).resolve().parents[1]
WERKZEUG = PROJEKT / "tools" / "vergleiche_releases.py"
RELEASE = "2026-11-14T09-09-47Z"


def werkzeug():
    spec = importlib.util.spec_from_file_location("vergleiche_releases", WERKZEUG)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


vr = werkzeug()


def manifest(**aenderungen) -> dict:
    """Ein Release mit zwei Gold-, einer Serving-Tabelle und der Karte."""
    inhalt = {
        "status": "complete", "release_id": RELEASE, "years": [2021, 2022],
        "code_version": {"git_commit": "a" * 40, "git_dirty": False},
        "gate": 99.1,
        "tables": {
            "gold/fact_offense": {"rows": 10, "contract_version": 3, "input_fingerprint": "f" * 64},
            "gold/dim_tract": {"rows": 5, "contract_version": 2, "input_fingerprint": "d" * 64},
            "serving/comparison_month": {"rows": 7, "contract_version": 1,
                                         "input_fingerprint": "c" * 64},
        },
        "files": {
            "gold/dataset=fact_offense/part-0001.parquet": {"sha256": "1" * 64, "bytes": 1},
            "gold/dataset=fact_offense/manifest.json": {"sha256": "m1" * 32, "bytes": 1},
            "gold/dataset=dim_tract/part-0001.parquet": {"sha256": "2" * 64, "bytes": 1},
            "gold/dataset=dim_tract/manifest.json": {"sha256": "m2" * 32, "bytes": 1},
            "serving/dataset=comparison_month/part-0001.parquet": {"sha256": "3" * 64, "bytes": 1},
            "serving/dataset=comparison_month/manifest.json": {"sha256": "m3" * 32, "bytes": 1},
            "serving/tracts.geojson": {"sha256": "4" * 64, "bytes": 1},
        },
    }
    for pfad, wert in aenderungen.items():
        ziel = inhalt
        teile = pfad.split("|")
        for teil in teile[:-1]:
            ziel = ziel[teil]
        ziel[teile[-1]] = wert
    return inhalt


def eimer(inhalt: dict, *, bucket: str, endpoint: str, aktuell: bool = True) -> Storage:
    client = FakeS3Client()
    client.put(f"releases/release={inhalt['release_id']}/release.json",
               json.dumps(inhalt).encode())
    if aktuell:
        client.put("releases/AKTUELL.json",
                   json.dumps({"release_id": inhalt["release_id"]}).encode())
    return Storage(Config(backend="s3", local_root=Path("unbenutzt"), s3_endpoint=endpoint,
                          s3_bucket=bucket, s3_access_key="k", s3_secret_key="g"), client)


def srv01(inhalt: dict | None = None, **kw) -> Storage:
    return eimer(inhalt or manifest(), bucket="urban-crime", endpoint="s3.example.org", **kw)


def gcp(inhalt: dict | None = None, **kw) -> Storage:
    return eimer(inhalt or manifest(), bucket="urbancrime-probe-1", endpoint="storage.googleapis.com", **kw)


def lauf(capsys, links, rechts, *argv):
    code = vr.main([*argv], links=links, rechts=rechts)
    ausgabe = capsys.readouterr()
    return code, ausgabe.out, ausgabe.err


def zeile(ausgabe: str, tabelle: str) -> str:
    return next(z for z in ausgabe.splitlines() if z.startswith(tabelle + " "))


# --------------------------------------------------------------------------
# Die Matrix
# --------------------------------------------------------------------------


def test_gleiche_releases_sind_gleich(capsys):
    code, aus, _ = lauf(capsys, srv01(), gcp())
    assert code == 0, aus
    assert "3 von 3 Tabellen mit gleichem Abdruck, 3 mit gleicher Pruefsumme." in aus
    for tabelle in ("gold/fact_offense", "gold/dim_tract", "serving/comparison_month"):
        assert zeile(aus, tabelle).split()[-2:] == ["gleich", "gleich"]


def test_das_manifest_der_tabelle_zaehlt_nicht_mit():
    """Es traegt Bauzeit und Herkunftspfade und ist nie gleich."""
    rechts = manifest(**{"files|gold/dataset=fact_offense/manifest.json": {"sha256": "x" * 64}})
    zeilen = {z["tabelle"]: z for z in vr.vergleiche(manifest(), rechts)}
    assert zeilen["gold/fact_offense"]["pruefsumme"] == "gleich"


def test_gleicher_abdruck_andere_bytes_ist_ein_befund_kein_fehler(capsys):
    rechts = manifest(**{"files|gold/dataset=dim_tract/part-0001.parquet": {"sha256": "9" * 64}})
    code, aus, _ = lauf(capsys, srv01(), gcp(rechts))
    assert code == 0, aus
    assert zeile(aus, "gold/dim_tract").split()[-2:] == ["gleich", "ungleich"]
    assert "gold/dim_tract: nicht erklaert" in aus
    assert "3 von 3 Tabellen mit gleichem Abdruck, 2 mit gleicher Pruefsumme." in aus


def test_der_grund_steht_daneben_wenn_er_ablesbar_ist():
    rechts = manifest(**{"code_version|git_commit": "b" * 40,
                         "tables|gold/dim_tract|rows": 6,
                         "files|gold/dataset=dim_tract/part-0001.parquet": {"sha256": "9" * 64}})
    zeilen = {z["tabelle"]: z for z in vr.vergleiche(manifest(), rechts)}
    gruende = zeilen["gold/dim_tract"]["gruende"]
    assert "Zeilen 5 gegen 6" in gruende
    assert any(g.startswith("Code-Stand aaaa") for g in gruende)


def test_ein_abweichender_abdruck_ist_exit_1(capsys):
    rechts = manifest(**{"tables|gold/fact_offense|input_fingerprint": "e" * 64})
    code, aus, _ = lauf(capsys, srv01(), gcp(rechts))
    assert code == 1
    assert zeile(aus, "gold/fact_offense").split()[-2] == "ungleich"


def test_eine_fehlende_tabelle_ist_exit_1(capsys):
    rechts = copy.deepcopy(manifest())
    del rechts["tables"]["serving/comparison_month"]
    code, aus, _ = lauf(capsys, srv01(), gcp(rechts))
    assert code == 1
    assert "fehlt rechts" in zeile(aus, "serving/comparison_month")


def test_kein_abdruck_auf_beiden_seiten_ist_nicht_gleich(capsys):
    ohne = manifest(**{"tables|gold/dim_tract|input_fingerprint": None})
    code, aus, _ = lauf(capsys, srv01(ohne), gcp(copy.deepcopy(ohne)))
    assert code == 1
    assert "ungleich (kein Abdruck)" in zeile(aus, "gold/dim_tract")


def test_dateien_ausserhalb_der_tabellen_stehen_zur_kenntnis_da(capsys):
    rechts = manifest(**{"files|serving/tracts.geojson": {"sha256": "8" * 64}})
    code, aus, _ = lauf(capsys, srv01(), gcp(rechts))
    assert code == 0
    assert any("serving/tracts.geojson" in z and z.rstrip().endswith("ungleich")
               for z in aus.splitlines())


def test_verschiedene_jahrgaenge_werden_genannt(capsys):
    _, aus, _ = lauf(capsys, srv01(), gcp(manifest(years=[2021])))
    assert "Jahrgaenge verschieden" in aus


def test_eine_kennung_statt_aktuell(capsys):
    rechts = gcp(aktuell=False)
    code, aus, _ = lauf(capsys, srv01(), rechts, "--rechts-release", RELEASE)
    assert code == 0, aus
    code, _, err = lauf(capsys, srv01(), gcp(aktuell=False))
    assert code == 1 and "noch kein Release" in err


def test_ein_eimer_gegen_sich_selbst_beweist_nichts(capsys):
    code, _, err = lauf(capsys, srv01(), srv01())
    assert code == 1 and "gegen sich selbst" in err


def test_das_ergebnis_als_json(capsys, tmp_path):
    ziel = tmp_path / "vergleich.json"
    code, _, _ = lauf(capsys, srv01(), gcp(), "--json", str(ziel))
    assert code == 0
    inhalt = json.loads(ziel.read_text(encoding="utf-8"))
    assert inhalt["rechts"]["ort"] == "storage.googleapis.com/urbancrime-probe-1"
    assert [z["tabelle"] for z in inhalt["tabellen"]] == [
        "gold/dim_tract", "gold/fact_offense", "serving/comparison_month"]


# --------------------------------------------------------------------------
# Die beiden .env-Dateien
# --------------------------------------------------------------------------


def test_jede_seite_kommt_nur_aus_ihrer_datei(tmp_path, monkeypatch):
    """Die Umgebung des Aufrufs gilt nicht - sonst meinten beide Seiten still
    denselben Eimer."""
    monkeypatch.setenv("S3_BUCKET", "aus-der-umgebung")
    datei = tmp_path / ".env.gcp"
    datei.write_text("STORAGE_BACKEND=s3\nS3_ENDPOINT=storage.googleapis.com\n"
                     "S3_BUCKET=urbancrime-probe-1\nS3_ACCESS_KEY=k\nS3_SECRET_KEY=g\n",
                     encoding="utf-8")
    ablage = vr.ablage(vr.lies_env(datei), "rechts")
    assert vr.ort(ablage) == "storage.googleapis.com/urbancrime-probe-1"


@pytest.mark.parametrize("inhalt,meldung", [
    ("STORAGE_BACKEND=local\n", "STORAGE_BACKEND=local"),
    ("STORAGE_BACKEND=s3\nS3_ACCESS_KEY=k\nS3_SECRET_KEY=g\n", "S3_ENDPOINT"),
])
def test_eine_unbrauchbare_env_nennt_die_seite(tmp_path, capsys, inhalt, meldung):
    datei = tmp_path / ".env.x"
    datei.write_text(inhalt, encoding="utf-8")
    code = vr.main(["--links", str(datei), "--rechts", str(datei)])
    err = capsys.readouterr().err
    assert code == 1 and "links" in err and meldung in err


def test_eine_fehlende_env_ist_ein_fehler_und_kein_traceback(tmp_path, capsys):
    code = vr.main(["--links", str(tmp_path / "gibt-es-nicht"), "--rechts", str(tmp_path / "x")])
    assert code == 1 and "keine Datei" in capsys.readouterr().err
