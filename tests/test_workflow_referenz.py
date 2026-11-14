"""Der Referenz-Waechter laeuft auf jedem Pull Request - und kann dort nicht
still ausfallen.

``tests/test_referenz.py::test_ein_zweiter_lauf_liefert_dieselben_dateien``
vergleicht nur mit der Python-Version, der pdoc-Version und der Plattform,
mit denen ``docs/referenz/`` abgelegt ist (``erzeugt-mit.json``). Bis zum
14.11.2026 passte kein CI-Job dazu: Linux lief mit 3.11, Windows unter
``nt``. Der Waechter uebersprang sich ueberall, und #236 und #239 kamen mit
veralteten Referenzseiten auf ``main``. Seither gibt es den Job ``referenz``;
dieser Test haelt ihn an der Marke fest. Wird die Referenz mit einer neuen
Python- oder pdoc-Version abgelegt, ist er rot, bis der Job mitzieht.
"""

import json
import re
from pathlib import Path

import yaml

PROJEKT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJEKT / ".github" / "workflows" / "tests.yml"
MARKE = PROJEKT / "docs" / "referenz" / "erzeugt-mit.json"


def _job():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert "referenz" in jobs, "tests.yml hat keinen Job 'referenz'"
    return workflow, jobs["referenz"]


def test_der_referenz_job_laeuft_mit_der_marke_und_ohne_ueberspringen():
    marke = json.loads(MARKE.read_text(encoding="utf-8"))
    workflow, job = _job()
    assert marke["plattform"] == "posix" and job["runs-on"].startswith("ubuntu"), job["runs-on"]
    python = next((s["with"]["python-version"] for s in job["steps"]
                   if s.get("uses", "").startswith("actions/setup-python")), None)
    assert python is not None, "Job referenz hat keinen Schritt actions/setup-python"
    assert str(python) == marke["python"], (
        f"Job referenz nimmt Python {python}, die Referenz ist mit {marke['python']} abgelegt")
    lock = (PROJEKT / "requirements.lock").read_text(encoding="utf-8")
    treffer = re.search(r"(?mi)^pdoc==(\S+)", lock)
    assert treffer, "requirements.lock pinnt kein pdoc"
    pdoc = treffer.group(1)
    assert pdoc == marke["pdoc"], (
        f"requirements.lock pinnt pdoc {pdoc}, die Referenz ist mit {marke['pdoc']} abgelegt")
    befehle = " ".join(s.get("run", "") for s in job["steps"])
    assert "requirements.lock" in befehle and "tests/test_referenz.py" in befehle
    assert str(job.get("env", {}).get("REFERENZ_PFLICHT")) == "1", (
        "ohne REFERENZ_PFLICHT=1 kann der Waechter im Job still ueberspringen")
    # Auf jedem Pull Request, nicht nur auf main: Dort kam das Veraltete her.
    # PyYAML liest den Schluessel ``on`` als True.
    ausloeser = workflow.get("on", workflow.get(True))
    assert "pull_request" in ausloeser
    # Und der Job selbst schliesst Pull Requests nicht aus: Er hat keine
    # Bedingung oder genau die, die nur den woechentlichen Zeitplan auslaesst.
    assert job.get("if") in (None, "github.event_name != 'schedule'"), (
        f"Job referenz laeuft unter {job.get('if')!r} - auf jedem Pull Request?")
