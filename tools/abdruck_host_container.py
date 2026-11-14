#!/usr/bin/env python3
"""FR-8: Ergibt ein Gold-Bau auf dem Host denselben Eingabe-Abdruck wie der im Container?

    python tools/abdruck_host_container.py 2026-11-14T09-09-47Z
    python tools/abdruck_host_container.py aktuell
    python tools/abdruck_host_container.py <release-id> --arbeit /tmp/abdruck

**Zweck.** FR-8 verlangt, dass ein Lauf im Container denselben
Eingabe-Fingerabdruck (``input_fingerprint``) erzeugt wie einer auf dem Host.
Eine Beschreibung belegt das nicht, ein gelaufener Vergleich schon. Dieses
Werkzeug nimmt ein Release, das auf ``srv01`` im Container gebaut wurde, baut
Gold auf dem Host aus **demselben** Silver noch einmal und stellt die Abdruecke
je Gold-Tabelle nebeneinander.

**Was es liest** - nur lesend, aus dem Eimer (Modus ``s3`` oder ``hybrid`` aus
der ``.env`` des Hosts):

- ``releases/release=<id>/release.json`` - Tabellen und Code-Stand des Release;
- ``releases/release=<id>/gold/dataset=<t>/manifest.json`` - je Gold-Tabelle
  der Container-Abdruck und die Herkunft (``derived_from``);
- ``silver/dataset=<t>[/vintage=<v>]/`` - das Silver, auf dem die Herkunft
  ruht, aber erst, nachdem jedes Silver-Manifest oben denselben
  ``input_fingerprint`` traegt wie die Herkunft im Release. Sonst bricht es ab:
  Silver ist seit dem Release weitergezogen, und ein Vergleich waere keiner.

**Was es schreibt** - nur in eine eigene Wurzel ausserhalb des Repositorys
(Vorgabe: ein temporaeres Verzeichnis, danach entfernt; ``--arbeit`` behaelt
sie). Dorthin kommt das geholte Silver, und dort baut
``python -m gold_pipeline.build_gold`` als **Unterprozess** mit
``STORAGE_BACKEND=local`` - es publiziert also nichts. Nichts geht in den
Eimer, ``releases/AKTUELL.json`` bleibt unberuehrt, und unter ``data/`` wird nie
gebaut. Der Container wird nicht gestartet: Der Containerlauf ist der, der das
Release gebaut hat.

**Warum ein Unterprozess.** ``AGENTS.md``: Reproduzierbarkeit nie in einem
Prozess pruefen. Der Host-Bau laeuft genau so, wie ein Mensch ihn aufruft.

**Vor dem Vergleich** sagt das Werkzeug, ob sich ``config/`` zwischen dem
Code-Stand des Release (``release.json``, ``code_version.git_commit``) und dem
Host unterscheidet. Eine Abweichung ist dann erklaert, nicht verschwiegen.

**Ausgabe.** Je Gold-Tabelle Container-Abdruck, Host-Abdruck und ``gleich``
oder ``ungleich``; bei ``ungleich`` der erste abweichende Herkunftsschluessel.
Exit 0 bei Gleichheit aller Tabellen, sonst 1.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "src" / "crime"))

from manifeste import FERTIG, MANIFEST, kennzeichen, read_manifest  # noqa: E402
from storage import Storage, StorageConfigError, StorageError, load  # noqa: E402
from storage import release as releases  # noqa: E402


class AbdruckFehler(RuntimeError):
    """Der Vergleich laesst sich nicht fuehren - mit Grund."""


#: ``bauen(wurzel, referenz_vintage, acs_vintages)`` - baut Gold unter
#: ``wurzel/gold`` aus ``wurzel/silver``. Fuer Tests austauschbar.
Bauen = Callable[[Path, int, tuple[int, ...]], None]


# ---------------------------------------------------------------------------
# Release lesen
# ---------------------------------------------------------------------------


def fertig(manifest: dict[str, Any]) -> bool:
    """Dieselbe Fertig-Regel wie ``manifeste.fertige_laeufe``: complete oder SUCCESS."""
    return str(manifest.get("status", "")).lower() in FERTIG


def json_oben(storage: Storage, schluessel: str) -> dict[str, Any]:
    return json.loads(storage.client.get(schluessel).decode("utf-8"))


def release_kennung(storage: Storage, was: str) -> str:
    if was != "aktuell":
        return was
    schluessel = f"{releases.RELEASES}/{releases.AKTUELL}"
    if storage.client.head(schluessel) is None:
        raise AbdruckFehler("Kein Zeiger oben - es wurde noch kein Release publiziert.")
    return json_oben(storage, schluessel)["release_id"]


def lies_release(storage: Storage, kennung: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """``release.json`` und die Gold-Manifeste darin, je Tabellenname."""
    rel = releases.relativ(kennung)
    schluessel = f"{rel}/{releases.RELEASE_MANIFEST}"
    if storage.client.head(schluessel) is None:
        raise AbdruckFehler(
            f"Release {kennung} unbekannt: kein {storage.s3_path(schluessel)}")
    manifest = json_oben(storage, schluessel)
    gold: dict[str, dict[str, Any]] = {}
    for name in sorted(manifest.get("tables", {})):
        schicht, _, tabelle = name.partition("/")
        if schicht != "gold":
            continue
        gold[tabelle] = json_oben(storage, f"{rel}/gold/dataset={tabelle}/{MANIFEST}")
        if not fertig(gold[tabelle]):
            raise AbdruckFehler(
                f"Release {kennung}: gold/{tabelle} hat den Status "
                f"{gold[tabelle].get('status')!r}, nicht fertig")
    if not gold:
        raise AbdruckFehler(f"Release {kennung} nennt keine Gold-Tabelle")
    return manifest, gold


# ---------------------------------------------------------------------------
# Silver: dasselbe wie im Release?
# ---------------------------------------------------------------------------


def silber_verzeichnis(pfad: str) -> str:
    """``silver/dataset=tract/vintage=2024`` aus einer Leseadresse.

    Die Adresse ist im Container ``s3://urban-crime/silver/...`` und auf dem
    Host ein lokaler Pfad; gemeinsam ist beiden nur der Teil ab ``silver/``.
    """
    roh = str(pfad).replace("\\", "/")
    anfang = roh.find("silver/dataset=")
    if anfang < 0:
        raise AbdruckFehler(f"keine Silver-Adresse: {pfad}")
    return roh[anfang:].rsplit("/", 1)[0]


def silberquellen(gold: dict[str, dict[str, Any]]) -> dict[str, str | None]:
    """Je Silver-Verzeichnis der Abdruck, den das Release nennt."""
    gefunden: dict[str, str | None] = {}
    for tabelle, manifest in sorted(gold.items()):
        for quelle in manifest.get("derived_from") or []:
            if quelle.get("layer") != "silver":
                continue
            verzeichnis = silber_verzeichnis(quelle["path"])
            abdruck = quelle.get("input_fingerprint")
            if verzeichnis in gefunden and gefunden[verzeichnis] != abdruck:
                raise AbdruckFehler(
                    f"{tabelle}: {verzeichnis} traegt im Release zwei Abdruecke - "
                    "das Release ruht nicht auf einem Silver-Stand")
            gefunden[verzeichnis] = abdruck
    if not gefunden:
        raise AbdruckFehler("Die Gold-Manifeste des Release nennen kein Silver")
    return gefunden


def pruefe_silber(storage: Storage, quellen: dict[str, str | None]) -> list[str]:
    """Je Silver-Stand, der nicht nachweislich derselbe ist wie im Release, ein Satz.

    Gleich heisst: Das Release nennt einen Abdruck, oben liegt ein fertiges
    Manifest (``complete``/``SUCCESS``), und es traegt genau diesen Abdruck.
    Fehlt eines davon, ist nichts bewiesen - ``None == None`` waere sonst gleich.
    """
    befunde = []
    for verzeichnis, erwartet in sorted(quellen.items()):
        schluessel = f"{verzeichnis}/{MANIFEST}"
        if not erwartet:
            befunde.append(f"{verzeichnis}: das Release nennt keinen Abdruck")
            continue
        if storage.client.head(schluessel) is None:
            befunde.append(f"{verzeichnis}: Release {erwartet}, oben kein Manifest")
            continue
        manifest = json_oben(storage, schluessel)
        if not fertig(manifest):
            befunde.append(f"{verzeichnis}: oben Status {manifest.get('status')!r}, "
                           "nicht fertig")
            continue
        oben = manifest.get("input_fingerprint")
        if oben != erwartet:
            befunde.append(f"{verzeichnis}: Release {erwartet}, oben {oben or '<kein Abdruck>'}")
    return befunde


def hole_silber(storage: Storage, wurzel: Path, verzeichnisse: list[str]) -> int:
    """Jedes Objekt unter den Verzeichnissen in die eigene Wurzel; Manifest zuletzt."""
    ablage = storage.mit_wurzel(wurzel)
    geholt = 0
    for verzeichnis in verzeichnisse:
        schluessel = sorted(
            (o.key for o in storage.client.list(verzeichnis + "/")
             if "/." not in o.key.removeprefix(verzeichnis)),
            key=lambda k: (k.endswith("/" + MANIFEST), k))
        for k in schluessel:
            ablage.hole(k)
            geholt += 1
    return geholt


def vintages(gold: dict[str, dict[str, Any]]) -> tuple[int, tuple[int, ...]]:
    """Referenz-Vintage (aus ``dim_tract``) und ACS-Vintages (aus ``dim_tract_acs``)."""
    def aus(tabelle: str) -> list[int]:
        gefunden = []
        for quelle in (gold.get(tabelle) or {}).get("derived_from") or []:
            if quelle.get("layer") == "silver" and quelle.get("table") == "tract":
                teil = silber_verzeichnis(quelle["path"]).rsplit("/", 1)[-1]
                if teil.startswith("vintage="):
                    gefunden.append(int(teil.removeprefix("vintage=")))
        return gefunden

    referenz = aus("dim_tract")
    if len(referenz) != 1:
        raise AbdruckFehler(
            f"dim_tract nennt {len(referenz)} Tract-Vintages statt eines - "
            "das Referenz-Vintage ist nicht ablesbar")
    acs = tuple(sorted(set(aus("dim_tract_acs")))) or (referenz[0],)
    return referenz[0], acs


# ---------------------------------------------------------------------------
# config/ zwischen Release und Host
# ---------------------------------------------------------------------------


def duckdb_version() -> str:
    try:
        import duckdb
    except ImportError:
        return "nicht installiert"
    return duckdb.__version__


def git(*argumente: str, wurzel: Path = PROJEKT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(wurzel), *argumente],
                          capture_output=True, text=True, timeout=30)


def config_unterschiede(commit: str | None, wurzel: Path = PROJEKT, *,
                        dirty: bool | None = False) -> list[str] | str:
    """Die ``config/``-Dateien, die sich seit ``commit`` geaendert haben.

    Eine Liste (leer: gleich) oder ein Satz, warum sich das nicht sagen laesst.
    Verglichen wird der Commit gegen den **Arbeitsbaum**, denn der Host-Bau
    liest ``config/`` aus dem Arbeitsbaum, nicht aus einem Commit.
    """
    if not commit:
        return "Code-Stand des Release unbekannt - config/ nicht vergleichbar"
    if dirty:
        # Der Commit sagt dann nicht, welches config/ der Bau las.
        return "config/ nicht vergleichbar: Release aus geaendertem Baum gebaut"
    try:
        if git("cat-file", "-e", f"{commit}^{{commit}}", wurzel=wurzel).returncode != 0:
            return (f"Release-Commit {commit} liegt nicht im lokalen Repository "
                    "(git fetch?) - config/ nicht vergleichbar")
        geaendert = git("diff", "--name-only", commit, "--", "config/", wurzel=wurzel)
        neu = git("ls-files", "--others", "--exclude-standard", "--", "config/",
                  wurzel=wurzel)
    except (OSError, subprocess.SubprocessError) as fehler:
        return f"git nicht nutzbar ({fehler}) - config/ nicht vergleichbar"
    if geaendert.returncode != 0 or neu.returncode != 0:
        return "git diff scheiterte - config/ nicht vergleichbar"
    return sorted({z for z in (geaendert.stdout + neu.stdout).splitlines() if z.strip()})


def host_stand(wurzel: Path = PROJEKT) -> str:
    try:
        commit = git("rev-parse", "HEAD", wurzel=wurzel)
        schmutzig = git("status", "--porcelain", wurzel=wurzel)
    except (OSError, subprocess.SubprocessError):
        return "unbekannt"
    if commit.returncode != 0:
        return "unbekannt"
    return commit.stdout.strip() + (" (mit Aenderungen)" if schmutzig.stdout.strip() else "")


# ---------------------------------------------------------------------------
# Bauen und vergleichen
# ---------------------------------------------------------------------------


def baue_gold(wurzel: Path, vintage: int, acs: tuple[int, ...]) -> None:
    """Der Host-Bau: ``build_gold`` als Unterprozess, lokal, ohne Publizieren."""
    befehl = [sys.executable, "-m", "gold_pipeline.build_gold",
              "--data-root", str(wurzel), "--vintage", str(vintage),
              "--acs-vintages", ",".join(str(v) for v in acs)]
    pfad = os.pathsep.join(p for p in (str(PROJEKT / "src" / "crime"),
                                       os.environ.get("PYTHONPATH", "")) if p)
    fertig = subprocess.run(
        befehl, cwd=PROJEKT, capture_output=True, text=True,
        env={**os.environ, "STORAGE_BACKEND": "local", "PYTHONPATH": pfad},
    )
    if fertig.returncode != 0:
        raise AbdruckFehler(
            f"Gold-Bau auf dem Host scheiterte (Exit {fertig.returncode}):\n"
            f"{fertig.stderr[-2000:]}")


def erster_unterschied(a: Any, b: Any, pfad: tuple = ()) -> tuple[tuple, Any, Any] | None:
    """Der erste Schluessel, an dem sich zwei Herkuenfte unterscheiden."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return pfad + (k,), a.get(k, "<fehlt>"), b.get(k, "<fehlt>")
            tiefer = erster_unterschied(a[k], b[k], pfad + (k,))
            if tiefer:
                return tiefer
        return None
    if isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            tiefer = erster_unterschied(x, y, pfad + (i,))
            if tiefer:
                return tiefer
        if len(a) != len(b):
            return pfad + ("len",), len(a), len(b)
        return None
    return None if a == b else (pfad, a, b)


def beschreibe(herkunft: list[dict[str, Any]], pfad: tuple) -> str:
    """``derived_from[1] (silver/dataset=tract/vintage=2024).input_fingerprint``."""
    teile = ["derived_from"]
    if pfad and isinstance(pfad[0], int) and pfad[0] < len(herkunft):
        quelle = herkunft[pfad[0]]
        if quelle.get("layer") == "silver" and quelle.get("path"):
            wo = silber_verzeichnis(quelle["path"])
        else:
            wo = f"{quelle.get('layer')}/{quelle.get('table')}"
        teile[0] = f"derived_from[{pfad[0]}] ({wo})"
        pfad = pfad[1:]
    for k in pfad:
        teile.append(f"[{k}]" if isinstance(k, int) else f".{k}")
    return "".join(teile)


def vergleiche(container: dict[str, dict[str, Any]], wurzel: Path) -> list[dict[str, Any]]:
    zeilen = []
    for tabelle, manifest in sorted(container.items()):
        # lokal mit Absicht: der Host-Bau liegt in der eigenen Wurzel dieses
        # Werkzeugs, im Modus local - nie im Eimer.
        datei = wurzel / "gold" / f"dataset={tabelle}" / MANIFEST
        zeile = {"tabelle": tabelle, "container": manifest.get("input_fingerprint"),
                 "host": None, "gleich": False, "unterschied": None}
        if not datei.is_file():
            zeile["unterschied"] = "auf dem Host nicht gebaut"
            zeilen.append(zeile)
            continue
        host = read_manifest(datei, fehler=AbdruckFehler)
        zeile["host"] = host.get("input_fingerprint")
        zeile["gleich"] = zeile["host"] == zeile["container"]
        if not zeile["gleich"]:
            links = manifest.get("derived_from") or []
            erst = erster_unterschied(kennzeichen(links),
                                      kennzeichen(host.get("derived_from") or []))
            if erst is None:
                zeile["unterschied"] = ("Herkunft gleich, Abdruck verschieden - die "
                                        "Abdruckregel selbst weicht ab")
            else:
                schluessel, c, h = erst
                zeile["unterschied"] = (f"{beschreibe(links, schluessel)}: "
                                        f"Container {c!r}, Host {h!r}")
        zeilen.append(zeile)
    return zeilen


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------


def arbeitswurzel(gewuenscht: Path | None,
                  datenwurzel: Path | None = None) -> tuple[Path, bool]:
    """(Wurzel, wegraeumen) - nie im Repository und nie unter der Datenwurzel.

    ``datenwurzel`` ist die konfigurierte lokale Wurzel (``LOCAL_DATA_ROOT``);
    sie kann ausserhalb des Repositorys liegen und ist trotzdem der Bestand.
    """
    if gewuenscht is None:
        return Path(tempfile.mkdtemp(prefix="abdruck-host-container-")), True
    wurzel = Path(gewuenscht).resolve()
    for verboten, was in ((PROJEKT, "im Repository"),
                          (Path(datenwurzel).resolve() if datenwurzel else None,
                           "unter der lokalen Datenwurzel")):
        if verboten is not None and (wurzel == verboten or verboten in wurzel.parents):
            raise AbdruckFehler(
                f"--arbeit {wurzel} liegt {was} - der Host-Bau gehoert in eine "
                "eigene Wurzel ausserhalb, nie unter data/")
    if wurzel.exists() and not wurzel.is_dir():
        raise AbdruckFehler(f"--arbeit {wurzel} ist kein Verzeichnis")
    if wurzel.exists() and any(wurzel.iterdir()):
        raise AbdruckFehler(f"--arbeit {wurzel} ist nicht leer")
    wurzel.mkdir(parents=True, exist_ok=True)
    return wurzel, False


def ausfuehren(was: str, *, storage: Storage, wurzel: Path,
               bauen: Bauen = baue_gold, projekt: Path = PROJEKT,
               aus: Callable[[str], None] = print) -> int:
    if not storage.config.remote:
        raise AbdruckFehler(
            f"STORAGE_BACKEND={storage.backend}: Das Werkzeug braucht Lesezugriff "
            "auf den Eimer (s3 oder hybrid) - dort liegt das Release aus dem Container")
    kennung = release_kennung(storage, was)
    manifest, gold = lies_release(storage, kennung)
    code = manifest.get("code_version") or {}
    commit = code.get("git_commit")
    werkzeug_oben = sorted({m.get("tool") for m in gold.values() if m.get("tool")})
    aus(f"Release      {kennung}")
    aus(f"Release-Code {commit or 'unbekannt'}")
    aus(f"Release-Bau  {', '.join(werkzeug_oben) or 'unbekannt'} (laut Gold-Manifest)")
    aus(f"Host-Code    {host_stand(projekt)}")
    aus(f"Host-Bau     {platform.machine()}, duckdb {duckdb_version()}")

    config = config_unterschiede(commit, projekt, dirty=code.get("git_dirty"))
    if isinstance(config, str):
        aus(f"config/      {config}")
    elif config:
        aus("config/      UNTERSCHIEDLICH zwischen Release und Host - eine "
            "Abweichung unten ist damit erklaert:")
        for datei in config:
            aus(f"               {datei}")
    else:
        aus("config/      gleich zwischen Release und Host")

    quellen = silberquellen(gold)
    weitergezogen = pruefe_silber(storage, quellen)
    if weitergezogen:
        aus("Silver ist seit dem Release weitergezogen - kein Bau, kein Vergleich:")
        for befund in weitergezogen:
            aus(f"  {befund}")
        return 1
    geholt = hole_silber(storage, wurzel, sorted(quellen))
    aus(f"Silver       {len(quellen)} Staende, {geholt} Objekte -> {wurzel / 'silver'}")

    vintage, acs = vintages(gold)
    aus(f"Host-Lauf    build_gold --vintage {vintage} --acs-vintages "
        f"{','.join(map(str, acs))} (STORAGE_BACKEND=local)")
    bauen(wurzel, vintage, acs)

    zeilen = vergleiche(gold, wurzel)
    aus("")
    breite = max(len(z["tabelle"]) for z in zeilen)
    aus(f"{'Tabelle':<{breite}}  {'Container':<64}  {'Host':<64}  Ergebnis")
    for z in zeilen:
        aus(f"{z['tabelle']:<{breite}}  {z['container'] or '-':<64}  "
            f"{z['host'] or '-':<64}  {'gleich' if z['gleich'] else 'ungleich'}")
    for z in zeilen:
        if not z["gleich"]:
            aus(f"  {z['tabelle']}: {z['unterschied']}")
    gleich = sum(z["gleich"] for z in zeilen)
    aus(f"\n{gleich} von {len(zeilen)} Gold-Tabellen gleich.")
    return 0 if gleich == len(zeilen) else 1


def main(argv: list[str] | None = None, *, storage: Storage | None = None,
         bauen: Bauen = baue_gold) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("release", help="Release-Kennung oder 'aktuell'")
    parser.add_argument("--arbeit", type=Path, default=None,
                        help="eigene, leere Wurzel fuer Silver und Host-Gold, "
                             "ausserhalb des Repositorys; bleibt danach stehen")
    args = parser.parse_args(argv)
    try:
        if storage is None:
            storage = Storage(load())
        wurzel, wegraeumen = arbeitswurzel(args.arbeit, storage.local_root)
    except (AbdruckFehler, StorageConfigError) as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1
    try:
        return ausfuehren(args.release, storage=storage, wurzel=wurzel, bauen=bauen)
    except (AbdruckFehler, StorageError) as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1
    finally:
        if wegraeumen:
            shutil.rmtree(wurzel, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
