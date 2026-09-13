"""Prueft die Ablage, bevor eine Pipeline daran scheitert.

    python -m storage

Zeigt Modus, Wurzel, Endpoint und Bucket (nie die Schluessel), loest den
Hostnamen auf und listet, was unter ``silver/`` liegt. Exit 0, wenn die
Ablage antwortet; 1 mit einem Satz, wenn nicht.
"""

from __future__ import annotations

import socket
import sys

from storage import StorageError, get_storage
from storage.config import StorageConfigError


def main() -> int:
    try:
        ablage = get_storage()
    except StorageConfigError as fehler:
        print(f"Konfiguration: {fehler}")
        return 1
    c = ablage.config
    print(f"Modus     : {c.backend}")
    print(f"Lokal     : {c.local_root.resolve()}")
    if not c.remote:
        print("SeaweedFS : nicht im Spiel (STORAGE_BACKEND=local)")
        return 0

    print(f"Endpoint  : {c.endpoint_url}")
    print(f"Bucket    : {c.s3_bucket}")
    print(f"Schluessel: {'gesetzt' if c.s3_access_key and c.s3_secret_key else 'FEHLEN'}")
    try:
        adressen = sorted({a[4][0] for a in socket.getaddrinfo(c.s3_endpoint, None)})
        print(f"DNS       : {c.s3_endpoint} -> {', '.join(adressen)}")
    except socket.gaierror as fehler:
        print(f"DNS       : {c.s3_endpoint} loest nicht auf ({fehler}). "
              "Ohne Eintrag hilft kein Schluessel - S3_ENDPOINT pruefen.")
        return 1
    try:
        dateien = ablage.list_files("silver", "**/manifest.json")
    except StorageError as fehler:
        print(f"Verbindung: {fehler}")
        return 1
    print(f"Verbindung: ok - {len(dateien)} Manifest(e) unter silver/ "
          + (f"({dateien[0]}, ...)" if dateien else "(noch nichts publiziert)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
