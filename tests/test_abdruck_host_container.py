"""Tests fuer ``tools/abdruck_host_container.py`` (FR-8).

Ein Mini-Stern statt echter Daten: fuenf Silber-Staende mit Manifest, ein
Eimer als ``FakeS3Client`` und ein Gold-Bau, der nur die **Manifeste**
schreibt - mit den echten Funktionen ``build_gold.silver_quelle`` und
``herkunft_der_quelle``, also mit derselben Herkunft, die der echte Bau
schreibt. Den echten Bau als Unterprozess fuehrt die Probe gegen den Eimer
(``docs/intern/AENDERUNGEN.md``, 14.11.2026); hier geht es um die fuenf Faelle
der I/O-Matrix im Plan.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

import build_gold as bg
from manifeste import eingabe_abdruck
from storage import Config, FakeS3Client, Storage

PROJEKT = Path(__file__).resolve().parents[1]
WERKZEUG = PROJEKT / "tools" / "abdruck_host_container.py"
RELEASE = "2026-11-14T09-09-47Z"


def werkzeug():
    spec = importlib.util.spec_from_file_location("abdruck_host_container", WERKZEUG)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


ahc = werkzeug()


# --------------------------------------------------------------------------
# Der Mini-Stern
# --------------------------------------------------------------------------


#: (Verzeichnis unter silver/, Abdruck) - was der Container las.
SILBER = {
    "dataset=crime_offense": "f" * 64,
    "dataset=tract/vintage=2023": "1" * 64,
    "dataset=tract/vintage=2024": "2" * 64,
    "dataset=place/vintage=2024": "3" * 64,
    "dataset=weather_day": "4" * 64,
}


def silber(wurzel: Path) -> None:
    for verzeichnis, abdruck in SILBER.items():
        d = wurzel / "silver" / verzeichnis
        d.mkdir(parents=True)
        (d / "part-0001.parquet").write_bytes(b"PAR1 " + verzeichnis.encode())
        (d / "manifest.json").write_text(json.dumps({
            "status": "complete", "built_at_utc": "2026-11-14T09:06:37Z",
            "input_fingerprint": abdruck,
            "derived_from": [{"layer": "bronze", "run_id": f"run_{abdruck[:4]}"}],
        }), encoding="utf-8")


def mini_bau(config_root: Path):
    """Schreibt fuenf Gold-Manifeste - mit der Herkunft, die ``build_gold`` schreibt."""
    def bauen(wurzel: Path, vintage: int, acs: tuple[int, ...]) -> None:
        bauen.aufrufe.append((wurzel, vintage, acs))
        offense = bg.silver_quelle(wurzel, "crime_offense")
        tract = bg.silver_quelle(wurzel, "tract", vintage)
        place = bg.silver_quelle(wurzel, "place", vintage)
        weather = bg.silver_quelle(wurzel, "weather_day")
        bauplan = {
            "fact_offense": [offense],
            "dim_tract": [tract, place],
            "dim_tract_acs": [bg.silver_quelle(wurzel, "tract", v) for v in acs],
            "dim_offense": [bg.Quelle("nibrs_codes.csv", config_root / "nibrs_codes.csv",
                                      layer="config")],
            "dim_city_day": [weather, offense],
        }
        for tabelle, quellen in bauplan.items():
            herkunft = [bg.herkunft_der_quelle(q) for q in quellen]
            d = wurzel / "gold" / f"dataset={tabelle}"
            d.mkdir(parents=True)
            (d / "manifest.json").write_text(json.dumps({
                "status": "complete", "table": tabelle,
                "built_at_utc": "2026-11-14T17:00:00Z",
                "derived_from": herkunft, "input_fingerprint": eingabe_abdruck(herkunft),
            }), encoding="utf-8")
    bauen.aufrufe = []
    return bauen


def im_eimer(wert, wurzel: Path):
    """Pfade, wie der Container sie schreibt: ``s3://urban-crime/...``."""
    if isinstance(wert, dict):
        return {k: (str(v).replace("\\", "/").replace(wurzel.as_posix(), "s3://urban-crime")
                    if k == "path" else im_eimer(v, wurzel)) for k, v in wert.items()}
    if isinstance(wert, list):
        return [im_eimer(v, wurzel) for v in wert]
    return wert


@pytest.fixture
def stern(tmp_path):
    """Ein Release im Eimer, gebaut aus dem Mini-Stern; dazu die Ablage."""
    config = tmp_path / "config"
    config.mkdir()
    (config / "nibrs_codes.csv").write_bytes(b"code\r\n13A\r\n")
    container = tmp_path / "container"
    silber(container)
    mini_bau(config)(container, 2024, (2023, 2024))

    eimer = FakeS3Client()
    for datei in sorted((container / "silver").rglob("*")):
        if datei.is_file():
            eimer.put(datei.relative_to(container).as_posix(), datei.read_bytes())
    tabellen = {}
    for manifest in sorted((container / "gold").glob("dataset=*/manifest.json")):
        inhalt = im_eimer(json.loads(manifest.read_text(encoding="utf-8")), container)
        name = manifest.parent.name.removeprefix("dataset=")
        tabellen[f"gold/{name}"] = {"input_fingerprint": inhalt["input_fingerprint"]}
        eimer.put(f"releases/release={RELEASE}/gold/{manifest.parent.name}/manifest.json",
                  json.dumps(inhalt).encode())
    tabellen["serving/comparison_day"] = {"input_fingerprint": "s" * 64}
    eimer.put(f"releases/release={RELEASE}/release.json", json.dumps({
        "release_id": RELEASE, "code_version": {"git_commit": "0" * 40, "git_dirty": False},
        "tables": tabellen}).encode())
    ablage = Storage(Config(backend="s3", local_root=tmp_path / "unbenutzt",
                            s3_access_key="k", s3_secret_key="g"), eimer)
    return ablage, config


def lauf(capsys, ablage, bauen, *argv):
    code = ahc.main([*argv], storage=ablage, bauen=bauen)
    ausgabe = capsys.readouterr()
    return code, ausgabe.out, ausgabe.err


# --------------------------------------------------------------------------
# Die fuenf Faelle
# --------------------------------------------------------------------------


def test_gleich_nennt_je_tabelle_beide_abdruecke(stern, capsys):
    ablage, config = stern
    bauen = mini_bau(config)
    code, aus, _ = lauf(capsys, ablage, bauen, RELEASE)
    assert code == 0, aus
    assert bauen.aufrufe and bauen.aufrufe[0][1:] == (2024, (2023, 2024))
    for tabelle in ("fact_offense", "dim_tract", "dim_tract_acs", "dim_offense",
                    "dim_city_day"):
        zeile = next(z for z in aus.splitlines() if z.startswith(tabelle + " "))
        abdruecke = [t for t in zeile.split() if len(t) == 64]
        assert len(abdruecke) == 2 and abdruecke[0] == abdruecke[1], zeile
        assert zeile.endswith("gleich")
    assert "5 von 5 Gold-Tabellen gleich" in aus
    assert "serving" not in aus.split("Tabelle", 1)[1]


def test_der_host_bau_liegt_nicht_im_repository(stern, capsys):
    ablage, config = stern
    bauen = mini_bau(config)
    assert lauf(capsys, ablage, bauen, RELEASE)[0] == 0
    wurzel = bauen.aufrufe[0][0].resolve()
    assert PROJEKT not in wurzel.parents
    assert not wurzel.exists(), "die temporaere Wurzel bleibt nach dem Lauf stehen"


def test_weitergezogenes_silber_baut_nicht(stern, capsys):
    ablage, config = stern
    ablage.client.put("silver/dataset=tract/vintage=2024/manifest.json", json.dumps({
        "status": "complete", "input_fingerprint": "9" * 64}).encode())
    bauen = mini_bau(config)
    code, aus, _ = lauf(capsys, ablage, bauen, RELEASE)
    assert code == 1
    assert bauen.aufrufe == []
    assert "Silver ist seit dem Release weitergezogen" in aus
    zeile = next(z for z in aus.splitlines() if "dataset=tract/vintage=2024" in z)
    assert "2" * 64 in zeile and "9" * 64 in zeile


def test_abweichung_nennt_den_ersten_unterschied(stern, capsys, tmp_path, monkeypatch):
    ablage, _ = stern
    anders = tmp_path / "host-config"
    anders.mkdir()
    (anders / "nibrs_codes.csv").write_bytes(b"code\n13A\n")
    monkeypatch.setattr(ahc, "config_unterschiede", lambda *a, **k: ["config/nibrs_codes.csv"])
    code, aus, _ = lauf(capsys, ablage, mini_bau(anders), RELEASE)
    assert code == 1
    assert aus.index("UNTERSCHIEDLICH") < aus.index("Tabelle")
    assert next(z for z in aus.splitlines() if z.startswith("dim_offense ")).endswith("ungleich")
    assert next(z for z in aus.splitlines() if z.startswith("fact_offense ")).endswith(" gleich")
    erklaert = next(z for z in aus.splitlines() if z.strip().startswith("dim_offense:"))
    assert "derived_from[0] (config/nibrs_codes.csv).sha256" in erklaert
    assert "4 von 5 Gold-Tabellen gleich" in aus


@pytest.mark.parametrize("manifest, grund", [
    (None, "oben kein Manifest"),
    ({"status": "running", "input_fingerprint": "2" * 64}, "nicht fertig"),
])
def test_unbelegtes_silber_baut_nicht(stern, capsys, manifest, grund):
    ablage, config = stern
    schluessel = "silver/dataset=tract/vintage=2024/manifest.json"
    if manifest is None:
        ablage.client.delete(schluessel)
    else:
        ablage.client.put(schluessel, json.dumps(manifest).encode())
    bauen = mini_bau(config)
    code, aus, _ = lauf(capsys, ablage, bauen, RELEASE)
    assert code == 1 and bauen.aufrufe == []
    zeile = next(z for z in aus.splitlines() if "dataset=tract/vintage=2024" in z)
    assert grund in zeile


def test_ohne_abdruck_im_release_ist_nichts_bewiesen(stern, capsys):
    """``None == None`` ist kein gleicher Stand."""
    ablage, config = stern
    for schluessel in [k for k in ablage.client.objekte if k.startswith("silver/")
                       and k.endswith("manifest.json")]:
        ablage.client.put(schluessel, json.dumps({"status": "complete"}).encode())
    for schluessel in [k for k in ablage.client.objekte if "/gold/" in k]:
        inhalt = json.loads(ablage.client.objekte[schluessel])
        for quelle in inhalt["derived_from"]:
            quelle.pop("input_fingerprint", None)
        ablage.client.put(schluessel, json.dumps(inhalt).encode())
    bauen = mini_bau(config)
    code, aus, _ = lauf(capsys, ablage, bauen, RELEASE)
    assert code == 1 and bauen.aufrufe == []
    assert "das Release nennt keinen Abdruck" in aus


def test_ein_release_aus_geaendertem_baum_ist_nicht_vergleichbar(stern, capsys):
    ablage, config = stern
    schluessel = f"releases/release={RELEASE}/release.json"
    inhalt = json.loads(ablage.client.objekte[schluessel])
    inhalt["code_version"] = {"git_commit": "0" * 40, "git_dirty": True}
    ablage.client.put(schluessel, json.dumps(inhalt).encode())
    _, aus, _ = lauf(capsys, ablage, mini_bau(config), RELEASE)
    zeile = next(z for z in aus.splitlines() if z.startswith("config/"))
    assert "nicht vergleichbar: Release aus geaendertem Baum gebaut" in zeile
    assert "gleich zwischen" not in aus


def test_unbekanntes_release_nennt_die_kennung(stern, capsys):
    ablage, config = stern
    code, _, fehler = lauf(capsys, ablage, mini_bau(config), "2020-01-01T00-00-00Z")
    assert code == 1
    assert "2020-01-01T00-00-00Z" in fehler and "unbekannt" in fehler


def test_ohne_eimer_bricht_ab(capsys, tmp_path):
    # Mit uebergebener Ablage: ``load()`` laese sonst die echte .env.
    lokal = Storage(Config(backend="local", local_root=tmp_path))
    code = ahc.main([RELEASE], storage=lokal,
                    bauen=lambda *a: pytest.fail("gebaut ohne Eimer"))
    assert code == 1
    assert "braucht Lesezugriff auf den Eimer" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Der echte Host-Bau und seine Wurzel
# --------------------------------------------------------------------------


def test_der_host_bau_ist_ein_lokaler_unterprozess(tmp_path, monkeypatch):
    gesehen = {}

    def run(befehl, **kw):
        gesehen.update(befehl=befehl, **kw)
        return subprocess.CompletedProcess(befehl, 0, "", "")

    monkeypatch.setattr(ahc.subprocess, "run", run)
    ahc.baue_gold(tmp_path / "w", 2024, (2021, 2022, 2023, 2024))
    assert gesehen["befehl"][1:] == [
        "-m", "gold_pipeline.build_gold", "--data-root", str(tmp_path / "w"),
        "--vintage", "2024", "--acs-vintages", "2021,2022,2023,2024"]
    assert gesehen["env"]["STORAGE_BACKEND"] == "local"
    assert gesehen["cwd"] == ahc.PROJEKT


def test_eine_wurzel_im_repository_wird_abgelehnt():
    with pytest.raises(ahc.AbdruckFehler, match="ausserhalb"):
        ahc.arbeitswurzel(PROJEKT / "data" / "abdruck")


def test_eine_wurzel_unter_der_datenwurzel_wird_abgelehnt(tmp_path):
    with pytest.raises(ahc.AbdruckFehler, match="Datenwurzel"):
        ahc.arbeitswurzel(tmp_path / "bestand" / "abdruck", tmp_path / "bestand")


def test_eine_datei_als_wurzel_ist_ein_sauberer_fehler(tmp_path, stern, capsys):
    datei = tmp_path / "datei"
    datei.write_text("x", encoding="utf-8")
    ablage, config = stern
    code, _, fehler = lauf(capsys, ablage, mini_bau(config), RELEASE, "--arbeit", str(datei))
    assert code == 1 and "kein Verzeichnis" in fehler


def test_ohne_bekannten_commit_bleibt_config_unvergleichbar():
    assert "nicht vergleichbar" in ahc.config_unterschiede(None)
    # Im Abbild gibt es weder .git noch zwingend git: Dann heisst es "git nicht
    # nutzbar" statt "nicht im lokalen Repository" - unvergleichbar ist beides.
    assert "nicht vergleichbar" in ahc.config_unterschiede("0" * 40)


def test_der_config_vergleich_gegen_head_liefert_eine_liste():
    """Der vergleichende Zweig: echtes ``git diff`` plus unverfolgte Dateien."""
    try:
        kopf = subprocess.run(["git", "-C", str(PROJEKT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git nicht nutzbar")
    if kopf.returncode != 0:
        pytest.skip("kein git-Repository")
    ergebnis = ahc.config_unterschiede(kopf.stdout.strip())
    assert isinstance(ergebnis, list), ergebnis
    offen = subprocess.run(["git", "-C", str(PROJEKT), "status", "--porcelain",
                            "--", "config/"], capture_output=True, text=True, timeout=30)
    if not offen.stdout.strip():
        assert ergebnis == []
