"""Ein Release bilden, auflisten, den Zeiger lesen.

    python -m orchestration.release liste                    # jedes Release, lokal und oben
    python -m orchestration.release aktuell                  # worauf der Zeiger zeigt
    python -m orchestration.release erstellen                # aus Gold und Serving bilden
    python -m orchestration.release erstellen --publizieren  # ... hochbringen, Zeiger umlegen
    python -m orchestration.release holen                    # das aktuelle Release herunterladen
    python -m orchestration.release holen 2026-09-17T16-31-45Z --nur-datenbank
    python -m orchestration.release holen --einsetzen        # ... und an die festen Pfade setzen

Die Ablage (``storage.release``) weiss, wie ein Release liegt und publiziert
wird. Was **hinein** gehoert, ausser Kopien, weiss sie nicht - das ist die
selbstaendige Datenbank aus ``serving``, und ``serving`` haengt an ``storage``,
nicht umgekehrt. Hier treffen sich beide: Dieses Modul reicht der Ablage den
Haken, der die Datenbank baut. ``run_all`` ruft dasselbe am Ende eines
gruenen Laufs.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from gold_pipeline import TABELLEN as GOLD_TABELLEN
from serving.build_analysis_db import build_selbststaendig
from serving.build_comparison import TABELLEN as SERVING_TABELLEN
from serving.export_geojson import GEOJSON_NAME
from storage import StorageError, for_root, release
from storage.config import StorageConfigError


# Was in einem vollstaendigen Release stehen muss - abgeleitet aus den
# Schichten selbst, nicht abgeschrieben. Kommt eine Gold- oder
# Serving-Tabelle dazu, steht sie hier von allein.
#
# Warum es das braucht: Wird ``data/serving/`` beiseitegeschoben, sammelt
# ``storage.release`` einfach weniger ein - am 17.9.2026 entstand so ein
# Release mit 11 statt 21 Dateien, das sich ``complete`` nannte. ``storage``
# kann das nicht bemerken; es kennt nur Dateien. Diese Liste ist die Stelle,
# an der jemand weiss, was dazugehoert.
VOLLSTAENDIG: tuple[str, ...] = (
    tuple(f"gold/dataset={t}" for t in GOLD_TABELLEN)
    + tuple(f"serving/dataset={t}" for t in SERVING_TABELLEN)
    + (f"serving/{GEOJSON_NAME}",)
)


def datenbank(arbeit: Path, kern: dict[str, Any]) -> None:
    """Der Haken: die selbstaendige ``analyse.duckdb`` aus den Tabellen im Release."""
    build_selbststaendig(
        [(name, parquet) for name, parquet, _ in release.tabellen_im(arbeit)],
        arbeit / "serving" / release.DATENBANK,
        kern,
    )


def bilde(data_root: Path, **kw: Any) -> Path:
    """Ein Release mit allem, was hineingehoert - und nur dann."""
    kw.setdefault("pflicht", VOLLSTAENDIG)
    return release.erstelle(data_root, ergaenze=datenbank, **kw)


def bilde_und_publiziere(data_root: Path, storage,
                         jahre: Iterable[int] = ()) -> dict[str, Any]:
    """Bilden und hochbringen - mit den Jahrgaengen, die der Lauf gebaut hat.

    ``jahre`` kommt von ``run_all``, denn nur dort steht, welche Jahrgaenge
    dieser Stand traegt: Gold und Serving liegen an Pfaden ohne ``year=``.
    ``storage.release`` schreibt sie als ``years`` ins Manifest, und
    ``orchestration.platzbedarf`` liest sie dort, statt sie sich ueber
    ``pipeline_run.json`` zu erschliessen. Ohne Angabe fehlt der Schluessel -
    geraten wird nichts.
    """
    return release.erstelle_und_publiziere(
        data_root, storage, ergaenze=datenbank, pflicht=VOLLSTAENDIG, jahre=jahre
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m orchestration.release", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("was", choices=("erstellen", "liste", "aktuell", "holen"))
    p.add_argument("kennung", nargs="?", default="aktuell",
                   help="holen: eine Release-Kennung oder 'aktuell' (Vorgabe)")
    p.add_argument("--publizieren", action="store_true",
                   help="erstellen: nach dem Bilden hochbringen und AKTUELL.json umlegen")
    p.add_argument("--nur-datenbank", action="store_true",
                   help="holen: nur serving/analyse.duckdb")
    p.add_argument("--einsetzen", action="store_true",
                   help="holen: die Tabellen danach an die festen Pfade setzen")
    p.add_argument("--data-root", type=Path, default=None,
                   help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    args = p.parse_args(argv)
    if args.was in {"erstellen", "holen"}:
        from storage.managed import guard
        guard(for_root(args.data_root).local_root)

    try:
        ablage = for_root(args.data_root)
    except StorageConfigError as fehler:
        print(f"Konfiguration: {fehler}")
        return 1
    try:
        if args.was == "liste":
            eintraege = release.liste(ablage)
            if not eintraege:
                print("Kein Release - weder lokal noch auf SeaweedFS.")
                return 0
            zeiger = release.aktuell(ablage) or {}
            for e in eintraege:
                marke = "<- AKTUELL" if e["release_id"] == zeiger.get("release_id") else ""
                mb = f"{(e['bytes'] or 0) / 1e6:6.1f} MB"
                print(f"  {e['release_id']}  {e['created_at_utc'] or '?':22} {mb}  {e['wo']:6} {marke}")
            return 0
        if args.was == "aktuell":
            zeiger = release.aktuell(ablage)
            if zeiger is None:
                print("Kein Zeiger - es wurde noch kein Release gebildet.")
                return 1
            for k, v in zeiger.items():
                print(f"  {k:16}: {v}")
            return 0
        if args.was == "holen":
            ziel = release.hole(ablage, args.kennung, nur_datenbank=args.nur_datenbank)
            manifest = release.lies(ziel)
            print(f"Release {manifest['release_id']} geholt -> {ziel}")
            if args.einsetzen:
                if args.nur_datenbank:
                    print("--einsetzen braucht das ganze Release, nicht nur die Datenbank.")
                    return 1
                eingesetzt = release.einsetzen(ablage.local_root, ziel)
                print(f"Eingesetzt: {len(eingesetzt)} Ziel(e) unter {ablage.local_root}")
            return 0
        ziel = bilde(ablage.local_root)
        manifest = release.lies(ziel)
        print(f"Release {manifest['release_id']}: {len(manifest['files'])} Dateien, "
              f"{manifest['bytes'] / 1e6:.1f} MB -> {ziel}")
        if args.publizieren:
            oben = release.publiziere(ablage, ziel)
            if oben:
                print(f"Publiziert: {len(oben)} Objekt(e), AKTUELL.json zeigt auf "
                      f"{manifest['release_id']}.")
            else:
                print(f"Nicht publiziert (STORAGE_BACKEND={ablage.backend}).")
        return 0
    except StorageError as fehler:
        print(f"Release: {fehler}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
