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


BELEGEN = ("03_chicago_data_quality", "13_detroit_data_quality",
           "31_storage_evaluation", "32_nibrs_source",
           "33_serving_evaluation", "34_gold_sternschema")
LADEN = ("01_chicago_source", "02_chicago_bronze_ingestion",
         "11_detroit_source", "12_detroit_bronze_ingestion",
         "21_census_source", "22_weather_source")


def test_die_belegenden_notebooks_laufen_nach_dem_bau():
    """Sechs von zwoelf, und nach der Strecke - vorher gaebe es keine Daten."""
    t = text()
    strecke = t.index("python -m orchestration.run_all")
    notebooks = t.index("nbconvert --to notebook --execute")
    assert strecke < notebooks
    for nb in BELEGEN:
        assert nb in t, f"{nb} fehlt im Datenlauf"


def test_die_ladenden_notebooks_laufen_nicht():
    """Sie wuerden im Lauf zusaetzliche Bronze-Laeufe erzeugen."""
    t = text()
    for nb in LADEN:
        assert nb not in t, f"{nb} laedt und gehoert nicht in den Datenlauf"


def test_jedes_notebook_im_repository_ist_eingeordnet():
    """Ein neues Notebook muss entweder laufen oder ausdruecklich nicht."""
    vorhanden = {p.stem for p in (PROJECT_ROOT / "notebooks").glob("*.ipynb")}
    eingeordnet = set(BELEGEN) | set(LADEN)
    assert vorhanden == eingeordnet, (
        f"nicht eingeordnet: {sorted(vorhanden - eingeordnet)}, "
        f"nicht mehr da: {sorted(eingeordnet - vorhanden)}"
    )


def test_der_datenlauf_erzwingt_eine_frische_schwelle():
    """Aufzeichnen allein ist keine Kontrolle."""
    assert "--maximal-alter-tage" in text()


# --------------------------------------------------------------------------
# Drift statt Rot (seit 13.9.2026)
# --------------------------------------------------------------------------


def test_die_waechter_des_referenzstands_laufen_nicht_im_datenlauf():
    """Auf frischen Daten waeren sie jede Woche rot - ein Alarm, der immer
    klingelt, ist keiner."""
    t = text()
    assert '-m "not referenzstand"' in t, (
        "pytest muss den Marker referenzstand abwaehlen"
    )


def test_die_drift_wird_ausgewiesen_auch_wenn_es_rot_ist():
    t = text()
    tests = t.index("python -m pytest")
    drift_ = t.index("python -m orchestration.drift")
    assert tests < drift_, "die Drift kommt nach den Tests"
    schritt = t[t.index("Drift ausweisen"):drift_]
    assert "if: always()" in schritt, "die Drift muss auch bei roten Tests erscheinen"
    assert "$GITHUB_STEP_SUMMARY" in t, "die Tabelle gehoert in die Job-Zusammenfassung"
    assert "data/drift.json" in t[t.index("Gesamtmanifest sichern"):], (
        "die Drift muss als Artefakt bleiben"
    )


def test_jeder_waechter_der_zahlen_gegen_daten_haelt_traegt_den_marker():
    """Ein Test, der eine dokumentierte Zahl gegen Parquet haelt und den
    Marker nicht traegt, macht den Datenlauf wieder jede Woche rot."""
    import re
    fehlend = []
    for datei in ("test_aenderungen.py", "test_abgabedokumente.py"):
        quelle = (PROJECT_ROOT / "tests" / datei).read_text(encoding="utf-8")
        for m in re.finditer(r"((?:@pytest\.mark\.[^\n]+\n)*)def (test_\w+)\(([^)]*)\)", quelle):
            dekoratoren, name, parameter = m.groups()
            braucht_daten = "con" in parameter.split(",") or "con," in parameter.replace(" ", "")
            if name in ("test_der_kopf_nennt_die_zeilenzahlen", "test_der_kopf_nennt_die_raten",
                        "test_der_kopf_nennt_das_fallkorn"):
                braucht_daten = True
            if braucht_daten and "referenzstand" not in dekoratoren:
                fehlend.append(f"{datei}::{name}")
    assert not fehlend, fehlend


def test_die_drift_hat_eine_schwelle():
    """Eine Tabelle, die niemand ansehen muss, ist der umgekehrte Fehler.
    Der Schritt darf die Toleranz nicht abschalten."""
    t = text()
    drift_ = t[t.index("python -m orchestration.drift"):].splitlines()[0]
    assert "--nur-melden" not in drift_
