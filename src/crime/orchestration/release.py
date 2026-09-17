"""Ein Release bilden, auflisten, den Zeiger lesen.

    python -m orchestration.release liste                    # jedes Release, lokal und oben
    python -m orchestration.release aktuell                  # worauf der Zeiger zeigt
    python -m orchestration.release erstellen                # aus Gold und Serving bilden
    python -m orchestration.release erstellen --publizieren  # ... hochbringen, Zeiger umlegen

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
from pathlib import Path
from typing import Any

from serving.build_analysis_db import build_selbststaendig
from storage import StorageError, for_root, release
from storage.config import StorageConfigError


def datenbank(arbeit: Path, kern: dict[str, Any]) -> None:
    """Der Haken: die selbstaendige ``analyse.duckdb`` aus den Tabellen im Release."""
    build_selbststaendig(
        [(name, parquet) for name, parquet, _ in release.tabellen_im(arbeit)],
        arbeit / "serving" / release.DATENBANK,
        kern,
    )


def bilde(data_root: Path, **kw: Any) -> Path:
    """Ein Release mit allem, was hineingehoert."""
    return release.erstelle(data_root, ergaenze=datenbank, **kw)


def bilde_und_publiziere(data_root: Path, storage) -> dict[str, Any]:
    return release.erstelle_und_publiziere(data_root, storage, ergaenze=datenbank)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m orchestration.release", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("was", choices=("erstellen", "liste", "aktuell"))
    p.add_argument("--publizieren", action="store_true",
                   help="nach dem Bilden hochbringen und AKTUELL.json umlegen")
    p.add_argument("--data-root", type=Path, default=None,
                   help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    args = p.parse_args(argv)

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
