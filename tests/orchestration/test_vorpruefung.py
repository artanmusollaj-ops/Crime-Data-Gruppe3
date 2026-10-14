"""Prueft die Vorpruefung - und vor allem, dass sie vorn steht.

Am 12.10.2026 feuerte der woechentliche Anstoss auf ``srv01`` zum ersten Mal
und brach nach rund einer halben Stunde ab: ``CENSUS_API_KEY`` fehlte. Chicago
und Detroit waren zu dem Zeitpunkt vollstaendig geladen, nach SeaweedFS
publiziert und die lokalen Arbeitskopien entfernt. Der Schluessel wird in
Stufe 13 von 39 gebraucht, geprueft wurde er auch erst dort.

Der Wert dieser Pruefung liegt deshalb nicht darin, **dass** sie fehlende
Schluessel findet - das tat ``census_pipeline`` schon -, sondern **wann**.
Darum haelt der wichtigste Test hier eine Reihenfolge und keinen Rueckgabewert.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from orchestration import vorpruefung as vp

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKRIPT = PROJECT_ROOT / "docker" / "srv01-datenlauf.sh"


def test_die_vorpruefung_steht_vor_jeder_ingestion():
    """Die Aussage dieses Stuecks, als Reihenfolge im Skript.

    Stuende sie hinter dem ersten Ladeaufruf, waere sie wertlos: Genau die
    halbe Stunde, die am 12.10.2026 verloren ging, laege dann wieder davor.
    """
    text = SKRIPT.read_text(encoding="utf-8")
    vorpruefung = text.index("orchestration.vorpruefung")
    lader = [text.index(m) for m in (
        "chicago_pipeline.download_chicago",
        "detroit_pipeline.extract_detroit",
        "census_pipeline.download_tiger",
        "orchestration.run_all",
    )]
    assert vorpruefung < min(lader), (
        "die Vorpruefung steht nicht vor dem ersten Ladeaufruf - dann prueft "
        "sie, was laengst geladen ist")


def test_der_name_des_schluessels_wird_gelesen_und_nicht_getippt():
    """Eine zweite Liste von Schluesseln waere die, die veraltet.

    Kaeme eine Quelle mit eigenem Schluessel dazu und stuende sein Name hier
    nur abgeschrieben, brauchte es zwei Aenderungen statt einer - und die
    zweite vergisst jemand.
    """
    from census_pipeline.download_acs import KEY_VARIABLE

    assert KEY_VARIABLE in vp.pflichtschluessel()


@pytest.mark.parametrize("wert", ("", "   ", None))
def test_ein_fehlender_oder_leerer_schluessel_faellt_auf(wert):
    umgebung = {} if wert is None else {"CENSUS_API_KEY": wert}
    assert vp.fehlende(umgebung) == ["CENSUS_API_KEY"]


def test_ein_gesetzter_schluessel_genuegt():
    assert vp.fehlende({"CENSUS_API_KEY": "abc"}) == []


def test_der_optionale_token_ist_keine_pflicht():
    """``SOCRATA_APP_TOKEN`` fehlen zu lassen darf keinen Lauf verhindern.

    ``chicago_pipeline.download_chicago`` nimmt ihn mit ``os.getenv(...) or
    None`` - ohne ihn antwortet die Quelle weiter, nur mit engeren Grenzen.
    Ein Lauf, der daran scheitert, waere strenger als die Wirklichkeit.
    """
    assert "SOCRATA_APP_TOKEN" not in vp.pflichtschluessel()
    assert "SOCRATA_APP_TOKEN" in vp.OPTIONAL


def test_die_meldung_sagt_was_zu_tun_ist(tmp_path):
    """Eine Fehlermeldung, die nur den Namen nennt, kostet eine Suche.

    Gelaufen wird in einem leeren Verzeichnis: Im Projekt liegt eine ``.env``
    mit dem Schluessel, und ``find_dotenv(usecwd=True)`` faende sie - der
    Test uebersprunge sich dann selbst und bewiese nichts.
    """
    lauf = subprocess.run(
        [sys.executable, "-m", "orchestration.vorpruefung"],
        cwd=tmp_path, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
             "STORAGE_BACKEND": "local", "LOCAL_DATA_ROOT": str(tmp_path),
             "PYTHONPATH": str(PROJECT_ROOT / "src" / "crime")},
    )
    assert lauf.returncode == 1, (
        f"ohne .env und ohne Umgebung muesste die Vorpruefung fallen; "
        f"stdout={lauf.stdout!r} stderr={lauf.stderr!r}")
    meldung = lauf.stderr
    assert "CENSUS_API_KEY" in meldung
    assert ".env" in meldung, "die Meldung sagt nicht, wohin der Schluessel"
    assert "abbrechen" in meldung or "Mitte" in meldung, (
        "die Meldung sagt nicht, was sonst passiert waere")
