"""Formpruefung des woechentlichen Datenlaufs.

Ohne pyyaml und ohne Netz - geprueft wird der Text. Was ein Workflow
behauptet, muss er auch tun: den Controller rufen, die Tests danach laufen
lassen, das Secret vorher pruefen. Ein Workflow, der stillschweigend nur die
Haelfte davon tut, waere schlimmer als keiner - er liesse glauben, die
Waechter liefen.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "datenlauf.yml"


def text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_der_workflow_liegt_im_repository():
    assert WORKFLOW.exists()


def test_er_laeuft_nach_zeitplan_und_von_hand():
    t = text()
    assert "schedule:" in t and "cron:" in t, "kein Zeitplan"
    assert "workflow_dispatch:" in t, "nicht von Hand startbar"


def test_er_laeuft_nicht_auf_pull_requests():
    """Netz, Schluessel, zwanzig Minuten - nichts davon gehoert in einen PR."""
    assert "pull_request" not in text()


def test_er_ruft_den_controller_und_dann_die_tests():
    t = text()
    controller = t.index("python -m orchestration.run_all")
    tests = t.index("python -m pytest")
    assert controller < tests, "die Tests muessen nach dem Bau laufen, nicht davor"


def test_er_prueft_das_secret_vorab():
    t = text()
    pruefung = t.index("CENSUS_API_KEY fehlt")
    strecke = t.index("python -m orchestration.run_all")
    assert pruefung < strecke, "das Secret gehoert vor die Strecke geprueft"


def test_er_sichert_das_gesamtmanifest_auch_bei_rot():
    t = text()
    assert "pipeline_run.json" in t
    sichern = t.index("Gesamtmanifest sichern")
    assert "if: always()" in t[sichern:], "das Manifest muss auch bei roten Tests bleiben"


def test_er_committet_keine_daten():
    t = text()
    assert "git commit" not in t and "git push" not in t
