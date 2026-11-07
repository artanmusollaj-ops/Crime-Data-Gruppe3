#!/usr/bin/env python3
"""Fuehrt die belegenden Notebooks aus und legt ihre Ausgaben als Nachweis ab.

    python tools/build_nachweise.py

Schreibt ``docs/nachweise/<datum>_<commit>/`` mit einer HTML-Datei je Notebook
und ``nachweis.json``, und erneuert das Verzeichnis ``docs/nachweise/README.md``.

**Warum es das gibt.** Die Beurteilung von LN1 (3.11.2026) sagt dreimal
dasselbe: Der Replay in Notebook 36 und die Benchmarks in 31 und 33 sind als
Code vorhanden, *"seine wiederholte Ausfuehrung aber nicht durch gespeicherte
Notebook-Ausgaben belegt"*. Die Notebooks im Repository bleiben trotzdem ohne
Ausgaben - ``tests/test_notebooks.py`` verlangt das, und der Grund dort gilt
weiter: Eine Ausgabe im Arbeitsnotebook veraltet still. Ein Nachweis daneben
veraltet dagegen laut: ``tests/test_nachweise.py`` haelt den Abdruck der
Codezellen im Nachweis gegen das Notebook und wird rot, sobald sie
auseinanderlaufen.

**Ein Nachweis, kein Erzeugnis.** Laufzeiten wiederholen sich nie byteweise,
also gibt es keinen Waechter "zweiter Lauf gleich erstem" wie beim
Feldkatalog. Es gibt stattdessen Datum, Commit, Umgebung und den Datenstand.

**In einer Kopie.** Notebook 36 baut fuer den Replay dreimal neu
(``run_all --ohne-ingestion``) und schreibt dabei nach ``data/``. Das
Werkzeug fuehrt deshalb alles in einer Kopie des Projekts aus: der Code aus
``git archive`` des Commits, ``data/`` geklont (APFS: ``cp -c``, kostet keinen
Platz). Das echte ``data/`` wird nur gelesen, und eine ``.env`` gibt es in
der Kopie nicht - ``STORAGE_BACKEND`` ist ``local``, nichts geht in den Eimer.

**Nur von einem sauberen Stand.** Weicht ``notebooks/``, ``src/``, ``config/``
oder ``tools/`` vom Commit ab, bricht es ab: Der Nachweis nennt einen Commit,
und der muss der Code sein, der gelaufen ist.

Ausgefuehrt wird mit nbclient, exportiert mit nbconvert, nach deren
Dokumentation: https://nbclient.readthedocs.io/en/latest/client.html und
https://nbconvert.readthedocs.io/en/latest/nbconvert_library.html
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[1]
ZIEL = PROJEKT / "docs" / "nachweise"

#: Die Notebooks, deren Ausgaben Aussagen der Abgabe tragen. 31 und 33 die
#: Benchmarks, 34 das Sternschema, 35 die Kontrollen, 36 die Hypothesen samt
#: Replay, 37 die Quellbewegung.
NOTEBOOKS = (
    "31_storage_evaluation",
    "33_serving_evaluation",
    "34_gold_sternschema",
    "35_kontrollen",
    "36_hypothesen",
    "37_quellbewegung",
)

#: Was sauber sein muss, damit der Commit den gelaufenen Code beschreibt.
SAUBER = ("notebooks", "src", "config", "tools")

#: Pakete, deren Version die Zahlen beruehren kann.
PAKETE = ("duckdb", "pyarrow", "pandas", "nbclient", "nbconvert", "ipykernel")

ZEITLIMIT_S = 3600


def code_abdruck(notebook: dict) -> str:
    """SHA-256 ueber die Codezellen allein.

    Nur der Code bestimmt die Ausgabe. Wer einen Satz im Markdown korrigiert,
    soll nicht neu messen muessen; wer eine Zeile Code aendert, schon.
    """
    teile = ["".join(z["source"]) if isinstance(z["source"], list) else z["source"]
             for z in notebook["cells"] if z["cell_type"] == "code"]
    return hashlib.sha256("\n\x00\n".join(teile).encode("utf-8")).hexdigest()


def git(*argumente: str) -> str:
    return subprocess.run(["git", *argumente], cwd=PROJEKT, check=True,
                          capture_output=True, text=True).stdout


def pruefe_sauber() -> None:
    offen = git("status", "--porcelain", "--", *SAUBER).strip()
    if offen:
        raise SystemExit(
            "Abgebrochen: Der Arbeitsbaum weicht vom Commit ab, der Nachweis "
            f"nennte also den falschen Code.\n{offen}\nErst committen.")


def kopiere_projekt(kopie: Path) -> None:
    """Code aus dem Commit, Daten geklont."""
    archiv = kopie.parent / "projekt.tar"
    subprocess.run(["git", "archive", "--format=tar", "-o", str(archiv), "HEAD"],
                   cwd=PROJEKT, check=True)
    kopie.mkdir()
    with tarfile.open(archiv) as tar:
        tar.extractall(kopie, filter="data")
    archiv.unlink()
    # lokal mit Absicht: Das Werkzeug liest die Arbeitsschichten genau so, wie
    # die Notebooks sie lesen, also als Dateien unter data/.
    if not (PROJEKT / "data" / "silver").is_dir():
        raise SystemExit("Abgebrochen: data/silver fehlt - zuerst python -m orchestration.run_all")
    if sys.platform == "darwin":
        # clonefile: Kopie beim Schreiben, die 1,9 GB belegen nichts.
        # "data/." statt "data": git archive bringt die wenigen versionierten
        # Pfade unter data/ schon mit, und cp legte sonst data/data an.
        (kopie / "data").mkdir(exist_ok=True)
        subprocess.run(["cp", "-cR", f"{PROJEKT / 'data'}/.", str(kopie / "data")], check=True)
    else:
        shutil.copytree(PROJEKT / "data", kopie / "data", symlinks=True, dirs_exist_ok=True)


def lenke_in_die_kopie(kopie: Path, commit: str) -> None:
    """Jeder Prozess ab hier - Kernel, run_all, dessen Stufen - nimmt die Kopie.

    Ohne das faende ``import orchestration`` ueber ``pip install -e`` den Code
    des echten Repositorys, und ``manifeste.projektwurzel`` naehme dessen
    Wurzel. ``PYTHONPATH`` geht vor den ``.pth``-Eintrag, ``PROJECT_ROOT``
    gilt vor der Paketlage. ``GIT_COMMIT`` traegt die Herkunft, weil die
    Kopie kein ``.git`` hat.
    """
    os.environ["PYTHONPATH"] = str(kopie / "src" / "crime")
    os.environ["PROJECT_ROOT"] = str(kopie)
    os.environ["GIT_COMMIT"] = commit
    sicht = subprocess.run(
        [sys.executable, "-c", "import orchestration, manifeste; "
         "print(orchestration.__file__); print(manifeste.projektwurzel())"],
        cwd=kopie, check=True, capture_output=True, text=True).stdout.split()
    if not all(Path(z).resolve().is_relative_to(kopie.resolve()) for z in sicht):
        raise SystemExit(f"Abgebrochen: Die Kopie sieht nicht sich selbst: {sicht}")


def baue_neu(kopie: Path) -> dict:
    """Silver, Gold und Serving in der Kopie neu, mit den Jahrgaengen des Baus.

    Die Notebooks 34, 35 und 37 lesen nur einen Bestand, den ``run_all``
    nach gruenem Lauf bestaetigt hat (``storage.analysesitzung``). So belegt
    der Nachweis ausserdem: Der Commit baut aus den vorhandenen Bronze-Laeufen
    durch.
    """
    # lokal mit Absicht: pipeline_run.json der Kopie nennt die Jahrgaenge.
    lauf = json.loads((kopie / "data" / "pipeline_run.json").read_text(encoding="utf-8"))
    jahre = ",".join(str(j) for j in lauf["years"])
    print(f"== Neubau in der Kopie, Jahrgaenge {jahre}", flush=True)
    start = time.perf_counter()
    fertig = subprocess.run(
        [sys.executable, "-m", "orchestration.run_all", "--ohne-ingestion", "--jahre", jahre],
        cwd=kopie, capture_output=True, text=True)
    dauer = time.perf_counter() - start
    if fertig.returncode != 0:
        raise SystemExit(f"Abgebrochen: Der Neubau ist gescheitert.\n{fertig.stdout[-2000:]}"
                         f"\n{fertig.stderr[-2000:]}")
    print(f"   {dauer:6.1f} s", flush=True)
    return {"befehl": f"python -m orchestration.run_all --ohne-ingestion --jahre {jahre}",
            "laufzeit_s": round(dauer, 1), "exit": fertig.returncode}


def datenstand(daten: Path) -> dict:
    """Woran der Lauf gebunden ist: Silver, Gold und das letzte Release."""
    def lies(*teile: str) -> dict:
        # lokal mit Absicht: Manifeste der Kopie, die die Notebooks gelesen haben.
        pfad = daten.joinpath(*teile)
        return json.loads(pfad.read_text(encoding="utf-8")) if pfad.is_file() else {}

    silver = lies("silver", "dataset=crime_offense", "manifest.json")
    gold = lies("gold", "dataset=fact_offense", "manifest.json")
    lauf = lies("pipeline_run.json")
    aktuell = lies("releases", "AKTUELL.json")
    release = lies(*aktuell["path"].split("/"), "release.json") if aktuell.get("path") else {}
    fp = silver.get("input_fingerprint")
    return {
        "jahrgaenge": lauf.get("years"),
        "silver_crime_offense": {"zeilen": silver.get("row_count"),
                                 "gebaut_utc": silver.get("built_at_utc"),
                                 "input_fingerprint": fp},
        "gold_fact_offense": {"zeilen": gold.get("row_count"),
                              "gebaut_utc": gold.get("built_at_utc")},
        "release_aktuell": aktuell.get("release_id"),
        "release_input_fingerprint": release.get("input_fingerprint"),
        "release_passt_zum_arbeitsstand": bool(fp) and fp == release.get("input_fingerprint"),
    }


def bereinige(notebook: dict, kopie: Path) -> None:
    """Rechnerpfade aus den Ausgaben nehmen.

    Ein Nachweis geht an Dritte; Heimverzeichnis und Temp-Pfad gehoeren
    nicht hinein und sagen ueber das Ergebnis nichts.
    """
    ersetzungen = [(str(kopie), "<projekt>"), (str(kopie.resolve()), "<projekt>"),
                   (str(PROJEKT), "<projekt>"), (str(Path.home()), "~")]

    def ersetze(text: str) -> str:
        for alt, neu in ersetzungen:
            text = text.replace(alt, neu)
        return text

    def tief(wert):
        if isinstance(wert, str):
            return ersetze(wert)
        if isinstance(wert, list):
            return [tief(w) for w in wert]
        if isinstance(wert, dict):
            return {k: tief(w) for k, w in wert.items()}
        return wert

    for zelle in notebook.cells:
        if zelle.cell_type == "code":
            zelle.outputs = tief(zelle.outputs)


def fuehre_aus(name: str, kopie: Path) -> tuple[dict, float]:
    import nbformat
    from nbclient import NotebookClient

    pfad = kopie / "notebooks" / f"{name}.ipynb"
    notebook = nbformat.read(pfad, as_version=4)
    start = time.perf_counter()
    NotebookClient(notebook, timeout=ZEITLIMIT_S, kernel_name="python3",
                   resources={"metadata": {"path": str(pfad.parent)}}).execute()
    dauer = time.perf_counter() - start
    fehler = [z for z in notebook.cells if z.cell_type == "code"
              for a in z.get("outputs", []) if a.get("output_type") == "error"]
    if fehler:
        raise SystemExit(f"Abgebrochen: {name} hat eine Fehlerausgabe.")
    bereinige(notebook, kopie)
    return notebook, dauer


def als_html(notebook) -> str:
    from nbconvert import HTMLExporter

    html, _ = HTMLExporter(template_name="lab").from_notebook_node(notebook)
    return html


def verzeichnis(ziel: Path = ZIEL) -> str:
    """Der Text von ``docs/nachweise/README.md``, aus allen ``nachweis.json``.

    Anders als die Nachweise selbst ist das Verzeichnis ein Erzeugnis: Es
    folgt byteweise aus den abgelegten Dateien, ``tests/test_nachweise.py``
    vergleicht.
    """
    zeilen = [
        "# Nachweise — ausgeführte Notebooks",
        "",
        "Erzeugt von `tools/build_nachweise.py` — nie von Hand ändern.",
        "",
        "Die Notebooks unter `notebooks/` liegen ohne Ausgaben im Repository. Hier",
        "liegen sie **ausgeführt**: je Lauf ein Ordner mit einer HTML-Datei je",
        "Notebook, lesbar ohne Python und ohne Daten, und `nachweis.json` mit",
        "Commit, Umgebung, Laufzeit und Datenstand. `tests/test_nachweise.py` hält",
        "den jüngsten Nachweis gegen die Notebooks: Ändert sich der Code eines",
        "Notebooks, ist der Nachweis veraltet und der Test rot.",
        "",
        "Ein Nachweis ist kein Erzeugnis: Laufzeiten wiederholen sich nie byteweise.",
        "Er belegt, dass dieser Code an diesem Tag auf diesem Datenstand gelaufen",
        "ist und dies ausgegeben hat.",
        "",
        "| Lauf | Commit | Datenstand (Silver) | Release passt | Notebooks |",
        "| --- | --- | --- | --- | --- |",
    ]
    for datei in sorted(ziel.glob("*/nachweis.json"), reverse=True):
        n = json.loads(datei.read_text(encoding="utf-8"))
        d = n["datenstand"]
        fp = (d["silver_crime_offense"]["input_fingerprint"] or "")[:12]
        passt = (f"ja, `{d['release_aktuell']}`" if d["release_passt_zum_arbeitsstand"]
                 else f"nein (letztes: `{d['release_aktuell']}`)")
        links = ", ".join(f"[{name[:2]}]({datei.parent.name}/{name}.html)"
                          for name in n["notebooks"])
        zeilen.append(f"| {datei.parent.name} | `{n['commit'][:7]}` | `{fp}` | {passt} | {links} |")
    return "\n".join(zeilen) + "\n"


def schreibe_verzeichnis() -> None:
    (ZIEL / "README.md").write_text(verzeichnis(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nur", nargs="+", choices=NOTEBOOKS,
                        help="nur diese Notebooks (Probe; schreibt nach --ziel)")
    parser.add_argument("--ziel", type=Path, default=ZIEL,
                        help="Ablage der Nachweise (Vorgabe: docs/nachweise)")
    args = parser.parse_args(argv)
    if args.nur and args.ziel.resolve() == ZIEL.resolve():
        raise SystemExit("Eine Probe mit --nur gehoert nicht nach docs/nachweise: --ziel angeben.")

    pruefe_sauber()
    commit = git("rev-parse", "HEAD").strip()
    erstellt = datetime.now(timezone.utc)
    ordner = args.ziel / f"{erstellt:%Y-%m-%d}_{commit[:7]}"
    if ordner.exists():
        raise SystemExit(f"Abgebrochen: {ordner} gibt es schon - ein Nachweis wird nicht ueberschrieben.")

    # Kein Weg in den Eimer, auch wenn die Shell eine s3-Umgebung traegt.
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ.pop("LOCAL_DATA_ROOT", None)

    with tempfile.TemporaryDirectory(prefix="nachweis-") as tmp:
        kopie = Path(tmp) / "projekt"
        kopiere_projekt(kopie)
        lenke_in_die_kopie(kopie, commit)
        aufbau = baue_neu(kopie)
        stand = {**datenstand(kopie / "data"), "aufbau": aufbau}
        ergebnisse = {}
        for name in args.nur or NOTEBOOKS:
            print(f"== {name}", flush=True)
            notebook, dauer = fuehre_aus(name, kopie)
            ergebnisse[name] = (notebook, dauer)
            print(f"   {dauer:6.1f} s", flush=True)

        ordner.mkdir(parents=True)
        eintraege = {}
        for name, (notebook, dauer) in ergebnisse.items():
            html = als_html(notebook)
            (ordner / f"{name}.html").write_text(html, encoding="utf-8")
            quelle = json.loads((PROJEKT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))
            eintraege[name] = {
                "code_sha256": code_abdruck(quelle),
                "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
                "laufzeit_s": round(dauer, 1),
                "codezellen": sum(1 for z in notebook.cells if z.cell_type == "code"),
            }

    nachweis = {
        "erstellt_utc": erstellt.isoformat(timespec="seconds"),
        "commit": commit,
        "umgebung": {
            "python": platform.python_version(),
            "system": f"{platform.system()} {platform.release()} {platform.machine()}",
            "pakete": {p: importlib.metadata.version(p) for p in PAKETE},
        },
        "datenstand": stand,
        "notebooks": eintraege,
        "hinweis": "Ausgefuehrt in einer Kopie des Projekts mit STORAGE_BACKEND=local. "
                   "Kein Erzeugnis: Laufzeiten wiederholen sich nicht byteweise.",
    }
    (ordner / "nachweis.json").write_text(
        json.dumps(nachweis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.ziel.resolve() == ZIEL.resolve():
        schreibe_verzeichnis()
    print(f"\nNachweis: {ordner.relative_to(PROJEKT) if ordner.is_relative_to(PROJEKT) else ordner}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
