#!/usr/bin/env python3
"""Ein Release aus einem Eimer in einen zweiten bringen und dort zum aktuellen machen.

    python tools/kopiere_release.py --release aktuell
    python tools/kopiere_release.py --release 2026-11-14T09-09-47Z \\
        --von ~/.config/urbancrime-probe/quelle.env \\
        --nach ~/.config/urbancrime-probe/hmac.env --trocken

**Zweck.** Kibana laeuft seit dem 1.11.2026 nur noch in der Probe in Google
Cloud (C-9), gezeigt werden soll dort aber das Release, das der Server
gerade fuehrt (Entscheid vom 15.11.2026). ``docker/gcp-starten.sh
--nur-kibana`` ruft dieses Werkzeug deshalb vor jedem Einspielen auf. Gebaut
wird in der Probe dafuer nichts: Das Release wird kopiert, nicht nachgebaut.
Das unterscheidet es von ``tools/kopiere_laeufe.py``, das die Bronze-Laeufe
fuer einen Nachbau kopiert (FR-47).

**Wie.** Gelesen wird ``releases/release=<id>/release.json`` im Quelleimer
(``aktuell`` folgt ``releases/AKTUELL.json``). Dann:

1. **Vorpruefung gegen das Ziel**, bevor irgendetwas geholt wird: Jede Datei
   des Release, die im Ziel schon liegt, muss dort die Groesse aus
   ``release.json`` tragen und, solange ``release.json`` dort fehlt, auch
   die SHA-256 (``vorpruefung``). Liegt eine anders da, bricht das Werkzeug ab -
   Releases sind unveraenderlich, ueberschrieben wird nie. Liegt
   ``release.json`` im Ziel schon gleich und zeigt ``AKTUELL.json`` darauf,
   ist nichts zu tun.
2. ``storage.release.hole`` holt das Release in ein Temporaerverzeichnis und
   haelt jede Datei gegen ihre SHA-256.
3. ``storage.release.publiziere`` bringt es ins Ziel - identische Dateien
   uebersprungen, ``release.json`` zuletzt - und legt dort ``AKTUELL.json``
   um. Dieselbe Funktion, mit der ``run_all`` ein Release publiziert; das
   Ziel bekommt also genau die Form, die ``holen aktuell`` dort erwartet.

Geloescht wird im Ziel nichts. Quelle und Ziel im selben Eimer lehnt es ab,
``--trocken`` macht nur die Vorpruefung und sagt, was kopiert wuerde.

**Die Schluessel** stehen wie bei ``tools/kopiere_laeufe.py`` in zwei
``.env``-Dateien unter ``~/.config/urbancrime-probe/`` (Modus 600, nie im
Repository-Verzeichnis; Entscheid vom 15.11.2026). Die Umgebung des Aufrufs
gilt nicht.

Exit 0, wenn das Release im Ziel liegt und ``AKTUELL.json`` darauf zeigt
(oder, mit ``--trocken``, wenn nichts dagegen spricht); 1, wenn es in der
Quelle fehlt, eine Datei im Ziel abweicht oder die Konfiguration nicht reicht.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

WERKZEUGE = Path(__file__).resolve().parent
sys.path.insert(0, str(WERKZEUGE))

from vergleiche_releases import (  # noqa: E402
    ZUSTAND, VergleichsFehler, ablage, json_oben, lies_env, lies_release, ort)
from storage import Storage, StorageError  # noqa: E402
from storage import release as releases  # noqa: E402

VORGABE_VON = ZUSTAND / "quelle.env"
VORGABE_NACH = ZUSTAND / "hmac.env"


class KopierFehler(RuntimeError):
    """Das Release laesst sich nicht (vollstaendig) kopieren - mit Grund."""


def sha(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def vorpruefung(von: Storage, nach: Storage, manifest: dict[str, Any]) -> tuple[list[str], int]:
    """(fehlend im Ziel, schon gleich). Weicht eine Datei im Ziel ab: KopierFehler.

    Ohne die Dateien zu laden: Liegt ``release.json`` im Ziel byteweise gleich
    wie in der Quelle, gilt jede Datei mit der Groesse aus ``release.json`` als
    vorhanden - ``release.json`` geht beim Publizieren zuletzt hoch, und
    darunter hat ``publiziere`` jede Datei geprueft. Sonst (ein halb
    kopiertes Release) wird jede Datei gleicher Groesse einzeln gehasht. Eine
    andere Groesse ist immer eine Abweichung. So laedt ein ``--nur-kibana``
    mit demselben Release nur zwei kleine JSON-Dateien.
    """
    rel = releases.relativ(manifest["release_id"])
    manifest_schluessel = f"{rel}/{releases.RELEASE_MANIFEST}"
    fehlend: list[str] = []
    gleich = 0
    if nach.client.head(manifest_schluessel) is None:
        manifest_gleich = False
        fehlend_manifest = True
    else:
        fehlend_manifest = False
        if sha(nach.client.get(manifest_schluessel)) != sha(von.client.get(manifest_schluessel)):
            raise KopierFehler(
                f"{ort(nach)}/{manifest_schluessel} liegt schon - anders als in {ort(von)}; "
                "nichts kopiert")
        manifest_gleich = True
    for datei, angabe in sorted((manifest.get("files") or {}).items()):
        schluessel = f"{rel}/{datei}"
        oben = nach.client.head(schluessel)
        if oben is None:
            fehlend.append(schluessel)
            continue
        if oben.size != angabe.get("bytes") or (
                not manifest_gleich and sha(nach.client.get(schluessel)) != angabe.get("sha256")):
            raise KopierFehler(
                f"{ort(nach)}/{schluessel} liegt schon - mit anderen Bytes als in "
                f"{releases.RELEASE_MANIFEST}. Releases sind unveraenderlich; nichts kopiert")
        gleich += 1
    if fehlend_manifest:
        fehlend.append(manifest_schluessel)
    else:
        gleich += 1
    return fehlend, gleich


def zeigt_auf(storage: Storage, kennung: str) -> bool:
    zeiger = f"{releases.RELEASES}/{releases.AKTUELL}"
    if storage.client.head(zeiger) is None:
        return False
    return json_oben(storage, zeiger).get("release_id") == kennung


def umgehaengt(storage: Storage, wurzel: Path) -> Storage:
    """Dieselbe Ablage mit einer anderen lokalen Wurzel (dem Temporaerverzeichnis)."""
    return Storage(replace(storage.config, local_root=wurzel), storage.client)


def ausfuehren(von: Storage, nach: Storage, *, release: str = "aktuell",
               trocken: bool = False, aus: Callable[[str], None] = print) -> int:
    if ort(von) == ort(nach):
        raise KopierFehler(f"Quelle und Ziel sind derselbe Eimer ({ort(von)})")
    manifest = lies_release(von, release)
    kennung = manifest["release_id"]
    fehlend, gleich = vorpruefung(von, nach, manifest)
    aktuell = zeigt_auf(nach, kennung)
    aus(f"Release {kennung} aus {ort(von)} -> {ort(nach)}: {len(fehlend)} Datei(en) "
        f"fehlen, {gleich} schon gleich; AKTUELL.json zeigt "
        + ("schon darauf" if aktuell else "noch nicht darauf")
        + ("  [trocken]" if trocken else ""))
    if not fehlend and aktuell:
        aus("Nichts zu tun.")
        return 0
    if trocken:
        return 0

    with tempfile.TemporaryDirectory(prefix="kopiere-release-") as tmp:
        wurzel = Path(tmp)
        verzeichnis = releases.hole(umgehaengt(von, wurzel), kennung)
        oben = releases.publiziere(umgehaengt(nach, wurzel), verzeichnis)
    if not zeigt_auf(nach, kennung):
        raise KopierFehler(f"{ort(nach)}: AKTUELL.json zeigt nach dem Publizieren nicht auf {kennung}")
    aus(f"{len(fehlend)} Datei(en) kopiert, {len(oben)} Objekte oben; "
        f"AKTUELL.json in {ort(nach)} zeigt auf {kennung}.")
    return 0


def main(argv: list[str] | None = None, *, von: Storage | None = None,
         nach: Storage | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", required=True,
                        help="Release-Kennung in der Quelle oder 'aktuell'")
    parser.add_argument("--von", type=Path, default=VORGABE_VON,
                        help=f".env des Quelleimers, nur gelesen (Vorgabe: {VORGABE_VON})")
    parser.add_argument("--nach", type=Path, default=VORGABE_NACH,
                        help=f".env des Zieleimers (Vorgabe: {VORGABE_NACH})")
    parser.add_argument("--trocken", action="store_true",
                        help="nur pruefen und zeigen, was kopiert wuerde")
    args = parser.parse_args(argv)
    try:
        if von is None:
            von = ablage(lies_env(args.von), "von")
        if nach is None:
            nach = ablage(lies_env(args.nach), "nach")
        return ausfuehren(von, nach, release=args.release, trocken=args.trocken)
    except (KopierFehler, VergleichsFehler, StorageError, json.JSONDecodeError) as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
