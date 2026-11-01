"""Das Skript, das die Abbilder auf ``srv01`` einsetzt.

Fuenf Handgriffe wurden einer. Der dritte davon - die ``.env`` aendern - ist
der gefaehrliche: Sie traegt alle Geheimnisse des Stapels und laesst sich aus
dem Repository **nicht** wiederherstellen. Diese Datei fuehrt die Funktion
deshalb wirklich aus, gegen eine eigene ``.env`` im Temporaerverzeichnis,
statt den Quelltext zu lesen.

**Warum kein assoziatives Feld im Skript.** Die gibt es erst ab Bash 4;
macOS liefert 3.2, und hier laufen die Tests. Ein Skript, das sich nur auf
dem Server pruefen laesst, scheitert dort zum ersten Mal - diese Woche
zweimal passiert.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKRIPT = PROJECT_ROOT / "docker" / "srv01-abbild-einsetzen.sh"

#: Eine .env, wie sie auf srv01 liegt - mit den Fallen, die eine naive
#: Ersetzung zerstoert: ein Geheimnis mit ``=`` und ``/`` darin, ein
#: Kommentar mit ``=``, eine leere Variable.
BEISPIEL_ENV = """PIPELINE_IMAGE=ghcr.io/datenwerft/urban-crime@sha256:alt111
JUPYTER_IMAGE=ghcr.io/datenwerft/urban-crime-jupyter@sha256:alt222

S3_SECRET_KEY=geheim/mit=Gleichheitszeichen+und/Schraegstrich
CENSUS_API_KEY=abc123
# Ein Kommentar mit = darin
LEER=
"""


def rufe(env_datei: Path, *bash: str) -> str:
    """Holt die Funktionen des Skripts herein und ruft, was gesagt wurde."""
    fertig = subprocess.run(
        ["bash", "-c",
         f'set -Eeuo pipefail; source "{SKRIPT}"; ' + "; ".join(bash)],
        capture_output=True, text=True,
        env={**os.environ, "ENV_FILE": str(env_datei)},
    )
    assert fertig.returncode == 0, fertig.stderr
    return fertig.stdout


@pytest.fixture
def env_datei(tmp_path: Path, benutzbares_bash: str) -> Path:
    # Ueber die Fixture statt in jedem Test: Genau die Tests, die ``rufe``
    # aufrufen, nehmen diese Datei - und nur sie brauchen eine Shell.
    pfad = tmp_path / ".env"
    pfad.write_text(BEISPIEL_ENV, encoding="utf-8")
    pfad.chmod(0o600)
    return pfad


def test_das_skript_liegt_im_repository_und_ist_ausfuehrbar():
    assert SKRIPT.is_file()
    assert os.access(SKRIPT, os.X_OK), "ohne Ausfuehrungsrecht nuetzt es nichts"


def test_es_laeuft_nicht_los_wenn_es_nur_hereingeholt_wird():
    """Sonst liesse sich keine seiner Funktionen pruefen - und es fasste beim
    blossen Hereinholen die echte ``.env`` an."""
    text = SKRIPT.read_text(encoding="utf-8")
    assert '"${BASH_SOURCE[0]}" == "${0}"' in text


def test_es_kommt_ohne_assoziative_felder_aus():
    """Bash 3.2 kennt sie nicht, und auf dieser Maschine laufen die Tests."""
    text = SKRIPT.read_text(encoding="utf-8")
    assert "declare -A" not in text and "readonly -A" not in text


def test_eine_vorhandene_zeile_wird_ersetzt(env_datei):
    rufe(env_datei, 'setze_in_env PIPELINE_IMAGE "ghcr.io/x@sha256:neu999"')
    zeilen = env_datei.read_text(encoding="utf-8").splitlines()
    assert "PIPELINE_IMAGE=ghcr.io/x@sha256:neu999" in zeilen
    assert not any(z.startswith("PIPELINE_IMAGE=ghcr.io/datenwerft") for z in zeilen)


def test_die_uebrigen_zeilen_bleiben_unversehrt(env_datei):
    """Besonders das Geheimnis mit ``=`` und ``/`` darin.

    Eine Ersetzung ueber ``sed s/.../.../`` zerschnitte es am Schraegstrich,
    eine ueber ``cut -d=`` am Gleichheitszeichen. Beides faellt hier auf.
    """
    rufe(env_datei, 'setze_in_env JUPYTER_IMAGE "ghcr.io/y@sha256:neu"')
    danach = env_datei.read_text(encoding="utf-8")
    assert "S3_SECRET_KEY=geheim/mit=Gleichheitszeichen+und/Schraegstrich" in danach
    assert "# Ein Kommentar mit = darin" in danach
    assert "\nLEER=\n" in danach
    assert "CENSUS_API_KEY=abc123" in danach


def test_eine_fehlende_zeile_wird_angehaengt(env_datei):
    rufe(env_datei, 'setze_in_env NEUE_VARIABLE "wert"')
    assert env_datei.read_text(encoding="utf-8").endswith("NEUE_VARIABLE=wert\n")


def test_die_rechte_bleiben_wie_sie_waren(env_datei):
    """Die ``.env`` traegt Geheimnisse; 0600 darf das Schreiben nicht aufweichen."""
    rufe(env_datei, 'setze_in_env PIPELINE_IMAGE "ghcr.io/x@sha256:neu"')
    assert env_datei.stat().st_mode & 0o777 == 0o600


def test_gelesen_wird_was_zuletzt_dasteht(env_datei):
    """Steht eine Variable zweimal da, gilt die letzte - wie bei Compose."""
    with env_datei.open("a", encoding="utf-8") as datei:
        datei.write("PIPELINE_IMAGE=ghcr.io/zweit@sha256:spaeter\n")
    assert rufe(env_datei, "steht_in_env PIPELINE_IMAGE").strip() == \
        "ghcr.io/zweit@sha256:spaeter"


def test_es_startet_die_pipeline_nicht_neu():
    """Sie laeuft als ``run --rm`` und nimmt das neue Abbild von selbst.

    Ein ``up -d pipeline`` startete einen Dienst, der nie dauerhaft laufen
    soll - FR-9 nennt genau das: Aus einem Wochenlauf wuerde eine
    Dauerschleife, die jede Woche neue Bronze-Laeufe anhaeuft.
    """
    text = SKRIPT.read_text(encoding="utf-8")
    anfang = text.index("NEUSTART_DIENSTE=")
    assert "pipeline" not in text[anfang:text.index("\n", anfang)]


def test_jeder_dauerdienst_auf_dem_strecken_abbild_startet_neu():
    """Sonst laeuft er nach dem Einsetzen auf dem alten Abbild weiter.

    Bis zum 1.11.2026 stand hier nur ``jupyter``; die Konsole (``admin``)
    blieb auf dem alten Abbild, bis jemand ``up -d admin`` tippte. Gelesen
    wird aus der Compose-Datei: jeder Dienst ohne Profil, dessen Abbild
    ``PIPELINE_IMAGE`` ist.
    """
    import yaml

    beschreibung = yaml.safe_load(
        (SKRIPT.parents[1] / "docker-compose.srv01.yml").read_text(encoding="utf-8"))
    dauernd = {name for name, d in beschreibung["services"].items()
               if "PIPELINE_IMAGE" in d.get("image", "") and not d.get("profiles")}
    text = SKRIPT.read_text(encoding="utf-8")
    anfang = text.index("NEUSTART_DIENSTE=")
    zeile = text[anfang:text.index("\n", anfang)]
    fehlend = sorted(n for n in dauernd if f'"{n}"' not in zeile)
    assert dauernd and not fehlend, f"startet nach dem Einsetzen nicht neu: {fehlend}"
