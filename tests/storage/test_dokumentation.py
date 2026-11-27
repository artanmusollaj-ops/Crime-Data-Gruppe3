"""Haelt `docs/storage-architektur.md` an der Konfiguration fest.

Ein Architekturdokument veraltet leise: Niemand merkt, dass eine Vorgabe
nicht mehr stimmt, bis jemand danach handelt und sich wundert. Geprueft wird
deshalb die **Variablentabelle** - jede Variable, die der Code liest, muss
darin stehen, und jede genannte Vorgabe muss die echte sein.

Der Fliesstext bleibt ungeprueft; er beschreibt Entscheidungen.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from storage import Config
from storage import config as cfg


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOKUMENT = PROJECT_ROOT / "docs" / "storage-architektur.md"
README = PROJECT_ROOT / "README.md"

# Umgebungsvariable -> Feld in Config
FELDER = {
    "STORAGE_BACKEND": "backend",
    "LOCAL_DATA_ROOT": "local_root",
    "S3_ENDPOINT": "s3_endpoint",
    "S3_ACCESS_KEY": "s3_access_key",
    "S3_SECRET_KEY": "s3_secret_key",
    "S3_BUCKET": "s3_bucket",
    "S3_USE_SSL": "s3_use_ssl",
    "HYBRID_READ_PRIORITY": "hybrid_read_priority",
    "HYBRID_PUBLISH_AFTER_WRITE": "hybrid_publish_after_write",
    "STORAGE_KEEP_LOCAL": "keep_local",
    "STORAGE_ANALYSEBESTAND_LOKAL": "analysebestand_lokal",
}


@pytest.fixture(scope="module")
def text() -> str:
    assert DOKUMENT.exists(), f"{DOKUMENT} fehlt - das Architekturdokument"
    return DOKUMENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tabelle(text) -> dict[str, str]:
    """Die Variablentabelle: Name -> genannte Vorgabe."""
    gefunden = {}
    for name, vorgabe in re.findall(r"^\| `([A-Z0-9_]+)` \| ([^|]+) \|", text, re.M):
        gefunden[name] = vorgabe.strip().strip("`")
    assert gefunden, "keine Variablentabelle im Dokument gefunden"
    return gefunden


def test_jede_gelesene_variable_steht_im_dokument(tabelle):
    """Was der Code aus der Umgebung liest, muss dokumentiert sein."""
    quelle = Path(cfg.__file__).read_text(encoding="utf-8")
    gelesen = set(re.findall(r'env\.get\("([A-Z0-9_]+)"\)', quelle))
    assert gelesen, "keine env.get-Aufrufe in config.py gefunden"
    fehlend = sorted(gelesen - set(tabelle))
    assert not fehlend, f"nicht im Architekturdokument: {fehlend}"


def test_keine_erfundene_variable(tabelle):
    """Umgekehrt: Das Dokument darf nichts nennen, das niemand liest."""
    unbekannt = sorted(set(tabelle) - set(FELDER))
    assert not unbekannt, f"im Dokument, aber nicht in der Konfiguration: {unbekannt}"


def test_die_genannten_vorgaben_sind_die_echten(tabelle):
    """Die Stelle, die am leisesten veraltet - eine Vorgabe im Text."""
    echt = Config()
    falsch = []
    for name, genannt in tabelle.items():
        wert = getattr(echt, FELDER[name])
        if genannt == "—":
            if wert:
                falsch.append(f"{name}: Dokument sagt 'keine Vorgabe', echt ist {wert!r}")
            continue
        erwartet = {True: "true", False: "false"}.get(wert, str(wert))
        if genannt != erwartet:
            falsch.append(f"{name}: Dokument sagt {genannt!r}, echt ist {erwartet!r}")
    assert not falsch, falsch


def test_alle_drei_modi_sind_beschrieben(text):
    from storage import BACKENDS

    fehlend = [m for m in BACKENDS if f"`{m}`" not in text]
    assert not fehlend, f"Modi ohne Beschreibung: {fehlend}"


def test_die_drei_saetze_stehen_drin(text):
    """Die Kurzfassung, die ueberall gleich lauten muss."""
    for satz in ("Hybrid READ", "Hybrid WRITE", "Serving DuckDB"):
        assert satz in text, f"{satz} fehlt in der Kurzfassung"


def test_das_readme_verweist_auf_das_dokument():
    """Wer die Bedienung liest, muss den Aufbau finden koennen."""
    assert "docs/storage-architektur.md" in README.read_text(encoding="utf-8")


def test_die_genannten_dateien_gibt_es(text):
    """Abschnitt 15 zaehlt den Code auf - er darf nicht auf Verschobenes zeigen."""
    fehlend = [
        p for p in re.findall(r"`(src/crime/storage/[a-z_]+\.py)`", text)
        if not (PROJECT_ROOT / p).exists()
    ]
    assert not fehlend, f"genannt, aber nicht vorhanden: {fehlend}"


def test_die_felder_der_konfiguration_sind_vollstaendig_zugeordnet():
    """Kommt ein Feld dazu, faellt dieser Test - und nicht erst das Dokument."""
    echte = {f.name for f in dataclasses.fields(Config)}
    assert set(FELDER.values()) == echte, (
        f"Zuordnung unvollstaendig: {sorted(echte ^ set(FELDER.values()))}"
    )
