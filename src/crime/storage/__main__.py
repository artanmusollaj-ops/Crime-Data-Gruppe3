"""Die Ablage pruefen - und bestehende Laeufe nachpublizieren.

    python -m storage                          # Verbindung pruefen
    python -m storage publizieren              # zeigen, welche lokalen Laeufe oben fehlen
    python -m storage publizieren --wirklich   # sie hochbringen, Raw vor Bronze
    python -m storage holen                    # zeigen, welche Laeufe oben liegen und lokal fehlen
    python -m storage holen --wirklich         # sie herunterladen, Raw vor Bronze

Releases (der ganze Stand unter einer Kennung) bildet und listet
``python -m orchestration.release`` - dort, weil die Datenbank im Release aus
``serving`` kommt und ``storage`` als Fundament nichts davon wissen darf.

Die Pruefung zeigt Modus, Wurzel, Endpoint und Bucket (nie die Schluessel),
loest den Hostnamen auf und listet, was unter ``silver/`` liegt. Exit 0, wenn
die Ablage antwortet; 1 mit einem Satz, wenn nicht.

Das Nachpublizieren ist fuer den Anfang gedacht: Die Pipelines publizieren
nur den Lauf, den sie gerade schreiben. Was vorher da war - Chicagos
Vollschnappschuss, die Deltas, Detroit, Census, NOAA - kommt nur so nach
SeaweedFS. Es ist dieselbe Regel wie in den Pipelines: je Lauf, Manifest
zuletzt, unveraenderlich (identisch oben: uebersprungen; anders oben: Fehler).
Die Gegenrichtung gibt es seit dem 17.9.2026: ``holen`` bringt jeden Lauf,
der oben liegt und lokal fehlt, herunter - Manifest zuletzt, geprueft. Der
Gesamtlauf tut dasselbe von selbst, bevor er ableitet. Fuer Silver und Gold
gilt das weiterhin nicht: Sie werden gelesen, nicht kopiert.
"""

from __future__ import annotations

import argparse
import socket
import sys

from manifeste import MANIFEST
from storage import LAUFSCHICHTEN, StorageError, get_storage
from storage.config import StorageConfigError


# Nachpublizieren und Holen gelten nur fuer die Schichten aus unveraenderlichen
# Laeufen; Silver und Gold werden gelesen, nicht kopiert. Die Liste steht
# kanonisch in ``storage.backend`` - hier ist sie die Auswahl daraus.
SCHICHTEN = LAUFSCHICHTEN


def pruefen() -> int:
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
    return staende(ablage)


def staende(ablage) -> int:
    """Je abgeleitete Tabelle: ist die lokale so neu wie die auf SeaweedFS?

    Das ist die Frage, die sich niemand stellt, bis eine alte Zahl auf einer
    Folie steht. "lokal zuerst" liest still die aeltere Fassung.
    """
    from storage import ABGELEITET

    zeilen, veraltet = [], 0
    for schicht in ABGELEITET:
        for pfad in sorted(ablage.local_path(schicht).glob(f"dataset=*/**/{MANIFEST}")):
            rel = ablage.relativ(pfad.parent)
            if rel is None:
                continue
            try:
                befund = ablage.vergleiche_stand(rel)
            except StorageError as fehler:
                print(f"Staende    : nicht vergleichbar ({fehler})")
                return 1
            if befund is None:
                zeilen.append((rel, "nur lokal"))
            elif befund.veraltet:
                veraltet += 1
                zeilen.append((rel, "ALT - " + befund.satz().split(": ", 1)[1]))
            else:
                zeilen.append((rel, "aktuell"))
    if not zeilen:
        print("Staende    : lokal ist nichts gebaut")
        return 0
    print("Staende    :")
    for rel, was in zeilen:
        print(f"  {rel:<44} {was}")
    if veraltet:
        print(f"\n{veraltet} lokale Tabelle(n) sind aelter als auf SeaweedFS. Sie werden "
              "trotzdem gelesen.\nNeu bauen: python -m orchestration.run_all --ohne-ingestion")
    return 0


def publizieren(schichten: tuple[str, ...], wirklich: bool) -> int:
    try:
        ablage = get_storage()
    except StorageConfigError as fehler:
        print(f"Konfiguration: {fehler}")
        return 1
    from contextlib import nullcontext
    from storage.analysesitzung import schreibzugriff
    from storage.verwaltet import sperre

    if wirklich:
        sperre(ablage.local_root)
    with schreibzugriff(ablage.local_root) if wirklich else nullcontext():
        if not ablage.config.publiziert:
            print(f"STORAGE_BACKEND={ablage.backend}: hier wird nichts publiziert.")
            return 1

        try:
            oben = {
                o.key.rsplit("/", 1)[0]
                for o in ablage.client.list("")
                if o.key.endswith("/manifest.json")
            }
            fehlend = []
            for schicht in schichten:   # Raw vor Bronze, wie die Pipelines
                for lauf in ablage.laeufe(schicht):
                    if lauf.verzeichnis.exists() and lauf.relativ not in oben:
                        fehlend.append(lauf)
        except StorageError as fehler:
            print(f"Verbindung: {fehler}")
            return 1

        if not fehlend:
            print("Nichts zu tun: jeder fertige lokale Lauf liegt schon oben.")
            return 0
        # ``lokal=True``: Gemeint sind die Bytes, die von hier hochgehen muessen.
        # Im ``s3``-Modus liest die Ablage nicht lokal, und die Summe waere 0.
        mb = sum(ablage.bytes_unter(lauf.relativ, lokal=True) for lauf in fehlend) / 1e6
        print(f"{len(fehlend)} Lauf/Laeufe lokal, aber nicht auf SeaweedFS ({mb:.0f} MB):")
        for lauf in fehlend:
            print(f"  {lauf.relativ}")
        if not wirklich:
            print("\nNichts publiziert. Mit --wirklich gehen sie hoch, Raw vor Bronze.")
            return 0

        for i, lauf in enumerate(fehlend, 1):
            try:
                dateien = ablage.publish_run(lauf.relativ)
            except StorageError as fehler:
                print(f"\n[{i}/{len(fehlend)}] {lauf.relativ}: {fehler}")
                return 1
            print(f"[{i}/{len(fehlend)}] {lauf.relativ}: {len(dateien)} Datei(en)")
        print(f"\nFertig: {len(fehlend)} Laeufe publiziert.")
        return 0


def holen(schichten: tuple[str, ...], wirklich: bool) -> int:
    try:
        ablage = get_storage()
    except StorageConfigError as fehler:
        print(f"Konfiguration: {fehler}")
        return 1
    from contextlib import nullcontext
    from storage.analysesitzung import schreibzugriff
    from storage.verwaltet import sperre

    if wirklich:
        sperre(ablage.local_root)
    with schreibzugriff(ablage.local_root) if wirklich else nullcontext():
        if not ablage.config.remote:
            print(f"STORAGE_BACKEND={ablage.backend}: hier gibt es nichts zu holen.")
            return 1
        try:
            fehlend = ablage.fehlende_laeufe(schichten)
        except StorageError as fehler:
            print(f"Verbindung: {fehler}")
            return 1
        if not fehlend:
            print("Nichts zu tun: jeder Lauf auf SeaweedFS liegt schon lokal.")
            return 0
        print(f"{len(fehlend)} Lauf/Laeufe auf SeaweedFS, aber nicht lokal:")
        for rel in fehlend:
            print(f"  {rel}")
        if not wirklich:
            print("\nNichts geholt. Mit --wirklich kommen sie herunter, Raw vor Bronze.")
            return 0
        for i, rel in enumerate(fehlend, 1):
            try:
                dateien = ablage.hole_lauf(rel)
            except StorageError as fehler:
                print(f"\n[{i}/{len(fehlend)}] {rel}: {fehler}")
                return 1
            print(f"[{i}/{len(fehlend)}] {rel}: {len(dateien)} Datei(en)")
        print(f"\nFertig: {len(fehlend)} Laeufe geholt.")
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m storage", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    unter = p.add_subparsers(dest="befehl")
    pub = unter.add_parser("publizieren", help="bestehende lokale Laeufe nach SeaweedFS bringen")
    pub.add_argument("--schichten", nargs="+", default=list(SCHICHTEN), choices=SCHICHTEN)
    pub.add_argument("--wirklich", action="store_true", help="nicht nur zeigen, sondern hochladen")
    hol = unter.add_parser("holen", help="Laeufe von SeaweedFS holen, die lokal fehlen")
    hol.add_argument("--schichten", nargs="+", default=list(SCHICHTEN), choices=SCHICHTEN)
    hol.add_argument("--wirklich", action="store_true", help="nicht nur zeigen, sondern herunterladen")
    args = p.parse_args(argv)
    if args.befehl == "publizieren":
        return publizieren(tuple(args.schichten), args.wirklich)
    if args.befehl == "holen":
        return holen(tuple(args.schichten), args.wirklich)
    return pruefen()


if __name__ == "__main__":
    sys.exit(main())
