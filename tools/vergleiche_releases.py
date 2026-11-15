#!/usr/bin/env python3
"""FR-47: Ergibt dasselbe Bronze in einer zweiten Umgebung dieselben Tabellen?

    python tools/vergleiche_releases.py
    python tools/vergleiche_releases.py --links ~/.config/urbancrime-probe/quelle.env \\
        --rechts ~/.config/urbancrime-probe/hmac.env \\
        --links-release 2026-11-14T09-09-47Z --rechts-release aktuell \\
        --json /tmp/vergleich.json

Ohne ``--links``/``--rechts`` gelten ``~/.config/urbancrime-probe/quelle.env``
und ``.../hmac.env`` (die schreibt ``docker/gcp-aufbauen.sh``). Die
Schluessel liegen dort mit Modus 600 und nie im Repository-Verzeichnis
(Entscheid vom 15.11.2026).

**Zweck.** FR-47 verlangt, dass die Portierung einmal trocken belegt wird:
"ein Lauf gegen einen anderen Objektspeicher, oder nachweislich gleiche
Pruefsummen". Dieses Werkzeug stellt zwei Releases aus zwei Eimern
nebeneinander - ueblicherweise das von ``srv01`` (SeaweedFS) und das der
Probe in Google Cloud (Cloud Storage), gebaut aus denselben Bronze-Laeufen.

**Was es liest** - nur lesend, je Seite aus dem Eimer, den eine eigene
``.env``-Datei beschreibt (``STORAGE_BACKEND`` ``s3`` oder ``hybrid``,
``S3_ENDPOINT``, ``S3_BUCKET``, Schluessel). Gelesen wird je Seite genau eine
Datei: ``releases/release=<id>/release.json``. Sie traegt je Tabelle den
Eingabe-Abdruck (``tables``) und je Datei die SHA-256 (``files``) - mehr
braucht der Vergleich nicht. Die Umgebung des aufrufenden Prozesses und eine
``.env`` im Arbeitsverzeichnis gelten **nicht**: Jede Seite kommt allein aus
ihrer Datei, damit nicht beide still denselben Eimer meinen.

**Was es schreibt:** nichts in einen Eimer. Mit ``--json`` das Ergebnis in
eine Datei.

**Ausgabe.** Je Gold- und Serving-Tabelle: Abdruck links und rechts,
``gleich``/``ungleich``, die Pruefsumme der Datendateien ``gleich``/``ungleich``
und bei ``ungleich`` die Gruende, die sich aus den beiden Manifesten ablesen
lassen (Zeilenzahl, Vertragsversion, Code-Stand). Was keiner davon erklaert,
heisst so: *nicht erklaert*. Darunter die Dateien ausserhalb der Tabellen
(``serving/tracts.geojson`` ...), nur zur Kenntnis.

**Exit 1, wenn ein Abdruck abweicht** oder eine Tabelle auf einer Seite
fehlt (Plan, I/O-Matrix "Vergleich"). Ungleiche Pruefsummen bei gleichem
Abdruck sind kein Fehler, sondern ein Befund, der erklaert werden muss: Der
Abdruck sagt, dass dieselbe Eingabe denselben Bau angestossen hat; die Bytes
koennen trotzdem abweichen - zwischen Host und Container lag es am
14.11.2026 an der letzten Gleitkommastelle von ``dim_tract.city_area_share``
(``docs/intern/fr-stand.md``, FR-8).

**Warum kein Abdruck kein Abdruck ist.** Fehlt er auf beiden Seiten, waere
``None == None`` gleich und bewiese nichts; das Werkzeug zaehlt es als
ungleich - dieselbe Regel wie ``tools/abdruck_host_container.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "src" / "crime"))

from manifeste import MANIFEST  # noqa: E402
from storage import Storage, StorageConfigError, StorageError, load  # noqa: E402
from storage import release as releases  # noqa: E402

#: Wo die Schluessel liegen (Plan, Decisions, 15.11.2026).
ZUSTAND = Path.home() / ".config" / "urbancrime-probe"
VORGABE_LINKS = ZUSTAND / "quelle.env"
VORGABE_RECHTS = ZUSTAND / "hmac.env"

#: Welche Schichten eines Release Tabellen tragen, die verglichen werden.
SCHICHTEN = ("gold", "serving")


class VergleichsFehler(RuntimeError):
    """Der Vergleich laesst sich nicht fuehren - mit Grund."""


# ---------------------------------------------------------------------------
# Die beiden Seiten
# ---------------------------------------------------------------------------


def lies_env(pfad: Path) -> dict[str, str]:
    """Die Variablen einer ``.env``-Datei - und nur sie."""
    from dotenv import dotenv_values

    if not pfad.is_file():
        raise VergleichsFehler(f"{pfad}: keine Datei")
    werte = {k: v for k, v in dotenv_values(pfad).items() if v is not None}
    # Die Pruefsummen-Einstellungen von botocore liest botocore selbst aus
    # der Umgebung, nicht aus der Ablage-Konfiguration (.env.gcp.example).
    # Gesetzt wird nur, was noch fehlt; "when_required" schadet SeaweedFS nicht.
    for name in ("AWS_REQUEST_CHECKSUM_CALCULATION", "AWS_RESPONSE_CHECKSUM_VALIDATION"):
        if werte.get(name):
            os.environ.setdefault(name, werte[name])
    return werte


def ablage(env: dict[str, str], seite: str) -> Storage:
    try:
        storage = Storage(load(env, dotenv=False))
    except StorageConfigError as fehler:
        raise VergleichsFehler(f"{seite}: {fehler}") from fehler
    if not storage.config.remote:
        raise VergleichsFehler(
            f"{seite}: STORAGE_BACKEND={storage.backend} - der Vergleich liest "
            "Releases aus einem Eimer (s3 oder hybrid)")
    return storage


def ort(storage: Storage) -> str:
    return f"{storage.config.s3_endpoint}/{storage.config.s3_bucket}"


def json_oben(storage: Storage, schluessel: str) -> dict[str, Any]:
    return json.loads(storage.client.get(schluessel).decode("utf-8"))


def lies_release(storage: Storage, was: str) -> dict[str, Any]:
    """``release.json`` des genannten Release oder des aktuellen."""
    if was == "aktuell":
        zeiger = f"{releases.RELEASES}/{releases.AKTUELL}"
        if storage.client.head(zeiger) is None:
            raise VergleichsFehler(f"{ort(storage)}: kein {zeiger} - noch kein Release")
        was = json_oben(storage, zeiger)["release_id"]
    schluessel = f"{releases.relativ(was)}/{releases.RELEASE_MANIFEST}"
    if storage.client.head(schluessel) is None:
        raise VergleichsFehler(f"{ort(storage)}: Release {was} unbekannt ({schluessel})")
    return json_oben(storage, schluessel)


# ---------------------------------------------------------------------------
# Der Vergleich - rein, ohne Ablage
# ---------------------------------------------------------------------------


def tabellen(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``gold/<t>`` und ``serving/<t>`` mit ihren Angaben aus ``tables``."""
    return {name: angaben for name, angaben in (manifest.get("tables") or {}).items()
            if name.partition("/")[0] in SCHICHTEN}


def verzeichnis(tabelle: str) -> str:
    schicht, _, name = tabelle.partition("/")
    return f"{schicht}/dataset={name}/"


def datendateien(manifest: dict[str, Any], tabelle: str) -> dict[str, str]:
    """Die Dateien einer Tabelle mit SHA-256, ohne ihr Manifest.

    Das Manifest traegt Bauzeit und Herkunftspfade und ist deshalb zwischen
    zwei Umgebungen nie gleich; verglichen werden die Daten.
    """
    anfang = verzeichnis(tabelle)
    return {pfad[len(anfang):]: angaben.get("sha256")
            for pfad, angaben in (manifest.get("files") or {}).items()
            if pfad.startswith(anfang) and not pfad.endswith("/" + MANIFEST)}


def uebrige_dateien(manifest: dict[str, Any]) -> dict[str, str]:
    """Was in keinem Tabellenverzeichnis liegt (Karte, Datenbank ...)."""
    anfaenge = tuple(verzeichnis(t) for t in tabellen(manifest))
    return {pfad: angaben.get("sha256")
            for pfad, angaben in (manifest.get("files") or {}).items()
            if not pfad.startswith(anfaenge)}


def commit(manifest: dict[str, Any]) -> str | None:
    return (manifest.get("code_version") or {}).get("git_commit")


def gruende(links: dict[str, Any], rechts: dict[str, Any],
            mlinks: dict[str, Any], mrechts: dict[str, Any]) -> list[str]:
    """Was aus den beiden Manifesten eine Abweichung erklaeren kann."""
    gefunden = []
    a, b = links.get("rows"), rechts.get("rows")
    if a != b:
        gefunden.append(f"Zeilen {a} gegen {b}")
    a, b = links.get("contract_version"), rechts.get("contract_version")
    if a != b:
        gefunden.append(f"Vertragsversion {a} gegen {b}")
    a, b = commit(mlinks), commit(mrechts)
    if a != b:
        gefunden.append(f"Code-Stand {a or 'unbekannt'} gegen {b or 'unbekannt'}")
    return gefunden


def vergleiche(mlinks: dict[str, Any], mrechts: dict[str, Any]) -> list[dict[str, Any]]:
    """Eine Zeile je Tabelle, die auf einer der beiden Seiten liegt."""
    tl, tr = tabellen(mlinks), tabellen(mrechts)
    zeilen = []
    for name in sorted(set(tl) | set(tr)):
        links, rechts = tl.get(name), tr.get(name)
        zeile: dict[str, Any] = {
            "tabelle": name,
            "abdruck_links": (links or {}).get("input_fingerprint"),
            "abdruck_rechts": (rechts or {}).get("input_fingerprint"),
        }
        if links is None or rechts is None:
            zeile.update(abdruck="fehlt " + ("links" if links is None else "rechts"),
                         pruefsumme="-", gruende=[])
            zeilen.append(zeile)
            continue
        gleicher_abdruck = (zeile["abdruck_links"] is not None
                            and zeile["abdruck_links"] == zeile["abdruck_rechts"])
        dl, dr = datendateien(mlinks, name), datendateien(mrechts, name)
        gleiche_bytes = bool(dl) and dl == dr
        zeile["abdruck"] = "gleich" if gleicher_abdruck else (
            "ungleich" if zeile["abdruck_links"] or zeile["abdruck_rechts"]
            else "ungleich (kein Abdruck)")
        zeile["pruefsumme"] = "gleich" if gleiche_bytes else "ungleich"
        zeile["gruende"] = [] if gleicher_abdruck and gleiche_bytes else (
            gruende(links, rechts, mlinks, mrechts) or ["nicht erklaert"])
        zeilen.append(zeile)
    return zeilen


def vergleiche_uebrige(mlinks: dict[str, Any], mrechts: dict[str, Any]) -> list[dict[str, Any]]:
    ul, ur = uebrige_dateien(mlinks), uebrige_dateien(mrechts)
    return [{"datei": pfad,
             "pruefsumme": ("fehlt links" if pfad not in ul else
                            "fehlt rechts" if pfad not in ur else
                            "gleich" if ul[pfad] == ur[pfad] else "ungleich")}
            for pfad in sorted(set(ul) | set(ur))]


# ---------------------------------------------------------------------------
# Ausfuehren
# ---------------------------------------------------------------------------


def ausfuehren(links: Storage, rechts: Storage, *, links_was: str = "aktuell",
               rechts_was: str = "aktuell", json_ziel: Path | None = None,
               aus: Callable[[str], None] = print) -> int:
    if ort(links) == ort(rechts):
        raise VergleichsFehler(
            f"Beide Seiten zeigen auf {ort(links)} - ein Eimer gegen sich selbst "
            "beweist keine Portierung")
    mlinks, mrechts = lies_release(links, links_was), lies_release(rechts, rechts_was)
    for seite, storage, m in (("links ", links, mlinks), ("rechts", rechts, mrechts)):
        aus(f"{seite}  {ort(storage)}  Release {m.get('release_id')}  "
            f"Code {commit(m) or 'unbekannt'}  Jahre {m.get('years') or '?'}  "
            f"Abdeckung {m.get('gate')}")
    if mlinks.get("years") != mrechts.get("years"):
        aus(f"Jahrgaenge verschieden: {mlinks.get('years')} gegen {mrechts.get('years')} - "
            "eine Abweichung unten ist damit erklaert")

    zeilen = vergleiche(mlinks, mrechts)
    uebrige = vergleiche_uebrige(mlinks, mrechts)
    if not zeilen:
        raise VergleichsFehler("Keines der beiden Releases nennt eine Gold- oder Serving-Tabelle")

    breite = max(len(z["tabelle"]) for z in zeilen)
    aus("")
    aus(f"{'Tabelle':<{breite}}  {'Abdruck links':<16}  {'Abdruck rechts':<16}  "
        f"{'Abdruck':<10}  Pruefsumme")
    for z in zeilen:
        aus(f"{z['tabelle']:<{breite}}  {(z['abdruck_links'] or '-')[:16]:<16}  "
            f"{(z['abdruck_rechts'] or '-')[:16]:<16}  {z['abdruck']:<10}  {z['pruefsumme']}")
    for z in zeilen:
        if z["gruende"]:
            aus(f"  {z['tabelle']}: {'; '.join(z['gruende'])}")
    if uebrige:
        aus("")
        aus("Weitere Dateien (zur Kenntnis):")
        for d in uebrige:
            aus(f"  {d['datei']:<{breite + 20}}  {d['pruefsumme']}")

    abdruck = sum(z["abdruck"] == "gleich" for z in zeilen)
    bytes_ = sum(z["pruefsumme"] == "gleich" for z in zeilen)
    aus("")
    aus(f"{abdruck} von {len(zeilen)} Tabellen mit gleichem Abdruck, "
        f"{bytes_} mit gleicher Pruefsumme.")
    if json_ziel is not None:
        json_ziel.write_text(json.dumps({
            "links": {"ort": ort(links), "release_id": mlinks.get("release_id"),
                      "git_commit": commit(mlinks)},
            "rechts": {"ort": ort(rechts), "release_id": mrechts.get("release_id"),
                       "git_commit": commit(mrechts)},
            "tabellen": zeilen, "weitere_dateien": uebrige,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        aus(f"Ergebnis -> {json_ziel}")
    return 0 if abdruck == len(zeilen) else 1


def main(argv: list[str] | None = None, *, links: Storage | None = None,
         rechts: Storage | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--links", type=Path, default=VORGABE_LINKS,
                        help=f".env der ersten Umgebung (Vorgabe: {VORGABE_LINKS})")
    parser.add_argument("--rechts", type=Path, default=VORGABE_RECHTS,
                        help=f".env der zweiten Umgebung (Vorgabe: {VORGABE_RECHTS})")
    parser.add_argument("--links-release", default="aktuell",
                        help="Release-Kennung links oder 'aktuell' (Vorgabe)")
    parser.add_argument("--rechts-release", default="aktuell",
                        help="Release-Kennung rechts oder 'aktuell' (Vorgabe)")
    parser.add_argument("--json", type=Path, default=None,
                        help="das Ergebnis zusaetzlich als JSON in diese Datei")
    args = parser.parse_args(argv)
    try:
        if links is None:
            links = ablage(lies_env(args.links), "links")
        if rechts is None:
            rechts = ablage(lies_env(args.rechts), "rechts")
        return ausfuehren(links, rechts, links_was=args.links_release,
                          rechts_was=args.rechts_release, json_ziel=args.json)
    except (VergleichsFehler, StorageError) as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
