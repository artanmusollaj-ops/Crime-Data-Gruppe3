"""Der Veroeffentlichungsstand: ein Verzeichnis je Release, ein Zeiger darauf.

    releases/release=2026-09-17T15-04-05Z/gold/dataset=fact_offense/part-0001.parquet
    releases/release=2026-09-17T15-04-05Z/serving/dataset=comparison_day/...
    releases/release=2026-09-17T15-04-05Z/serving/analyse.duckdb   <- selbstaendig
    releases/release=2026-09-17T15-04-05Z/serving/tracts.geojson
    releases/release=2026-09-17T15-04-05Z/release.json             <- Pruefsummen
    releases/AKTUELL.json                                           <- der Zeiger

**Was das loest.** Bis zum 17.9.2026 wurden die fuenf Gold-Tabellen einzeln
und nacheinander an festen Pfaden ueberschrieben. Zwischen ``fact_offense`` und
``dim_city_day`` lag ein Fenster, in dem eine Abfrage ueber beide einen
gemischten Stand sah - und sobald ein Dashboard danebensteht, fragt jemand
genau in diesem Fenster. Ein Release ist **unveraenderlich** und **ganz**:
Geschrieben wird vollstaendig unter einer neuen Kennung, geprueft, und erst
dann wird ``AKTUELL.json`` ersetzt - ein einziges Objekt, dessen Ersetzung
lokal (``rename``) wie auf S3 (``PUT``) unteilbar ist. Alle Tabellen wechseln
gemeinsam, ein Abbruch an jeder Stelle laesst den alten Stand gueltig.

**Eine Kennung je Release, nicht je Tabelle.** Ein frueherer Entwurf
versionierte jede Tabelle fuer sich. Das ist beweglicher - und genau die
Beweglichkeit ist die Moeglichkeit, aus der ein gemischter Stand entsteht.
Gold wird ohnehin immer als Ganzes gebaut.

**Die DuckDB im Release ist selbstaendig.** Die Arbeitsdatenbank
``data/serving/analyse.duckdb`` haelt Sichten mit absoluten Pfaden; auf einem
anderen Rechner ist sie wertlos. Die Datei im Release haelt **Tabellen** und
ist ein Download, der sofort antwortet. Der Bestand bleibt Parquet - die
DuckDB-Datei ist eine Ableitung davon und haengt an einer DuckDB-Version.

**Was ein Release enthaelt:** die fuenf Gold-Tabellen, die vier
Serving-Tabellen, das GeoJSON, die selbstaendige Datenbank und
``release.json`` mit SHA-256 je Datei, Vertrags- und Code-Versionen, dem
Eingabe-Abdruck und den Bronze-Laeufen, auf denen alles ruht. Nicht enthalten:
Silver und Bronze - die liegen an ihren festen Pfaden und sind ueber die
Manifeste erreichbar.

**Wie es auf SeaweedFS kommt.** Wie ein Lauf: unveraenderlich, identisch oben
wird uebersprungen, anders oben ist ein Fehler. ``release.json`` geht zuletzt
hoch, dann wird ``AKTUELL.json`` ersetzt. Die festen Pfade ``gold/dataset=...``
werden weiterhin bedient - wer heute dort liest, liest weiter; das Release ist
der Weg fuer alles, was einen **ganzen** Stand braucht.

**Was bewusst nicht hier steht:** Loeschen. Releases werden aufgehoben, bis
eine Regel dafuer entschieden ist (``docs/intern/datenhistorie.md``). Rund 15 MB
Parquet plus die Datenbank je Release - ein Jahr woechentlicher Releases ist
unter einem Gigabyte.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from manifeste import MANIFEST, PARQUET_FILE, code_stand, read_manifest
from storage import paths
from storage.backend import PublishError, Storage, StorageError


LOG = logging.getLogger("release")

RELEASES = "releases"
AKTUELL = "AKTUELL.json"
RELEASE_MANIFEST = "release.json"
DATENBANK = "analyse.duckdb"

# Was in ein Release kommt: (Schicht, Muster relativ zur Schicht). Tabellen als
# ganze Verzeichnisse, die beiden Karten-Dateien einzeln.
INHALT: tuple[tuple[str, str], ...] = (
    ("gold", "dataset=*"),
    ("serving", "dataset=*"),
    ("serving", "tracts.geojson"),
    ("serving", "tracts.manifest.json"),
)
# Was mindestens dasein muss, damit ein Release eines ist. ``storage`` kennt
# nur Dateien, nicht die Schichten darueber - deshalb ist das hier ein Boden,
# und der Aufrufer reicht die vollstaendige Liste nach (``orchestration.release``).
#
# Warum es diesen Parameter gibt: Am 17.9.2026 wurde ``data/serving/``
# beiseitegeschoben und ein Release gebildet. Es entstand mit 11 statt 21
# Dateien - ohne die vier Vergleichstabellen, ohne die Karte - und nannte sich
# ``complete``. Ein Teilstand, dem man es nicht ansieht, ist schlimmer als
# keiner.
PFLICHT = ("gold/dataset=fact_offense",)


class ReleaseFehler(StorageError):
    """Ein Release laesst sich nicht bilden oder nicht lesen."""


# ---------------------------------------------------------------------------
# Kennung und Pfade
# ---------------------------------------------------------------------------


def kennung(jetzt: datetime | None = None) -> str:
    """``2026-09-17T15-04-05Z`` - sortierbar, ohne Doppelpunkte (Windows, S3)."""
    return (jetzt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H-%M-%SZ")


def relativ(kennung_: str) -> str:
    return paths.relativ(RELEASES, f"release={kennung_}")


def verzeichnis(data_root: Path, kennung_: str) -> Path:
    return data_root / RELEASES / f"release={kennung_}"


def kennung_aus(verzeichnis_: Path | str) -> str:
    name = str(verzeichnis_).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if not name.startswith("release="):
        raise ReleaseFehler(f"kein Release-Verzeichnis: {verzeichnis_}")
    return name.removeprefix("release=")


# ---------------------------------------------------------------------------
# Sammeln und bilden
# ---------------------------------------------------------------------------


def sammle(data_root: Path) -> list[tuple[Path, str]]:
    """Was ins Release kommt: (lokale Datei, Pfad im Release).

    Nur Tabellen mit fertigem Manifest zaehlen; ein ``.part`` daneben nie.
    """
    dateien: list[tuple[Path, str]] = []
    for schicht, muster in INHALT:
        wurzel = data_root / schicht
        if not wurzel.is_dir():
            continue
        for treffer in sorted(wurzel.glob(muster)):
            if paths.versteckt(treffer.relative_to(wurzel).as_posix()):
                continue
            if treffer.is_dir():
                if not (treffer / MANIFEST).is_file():
                    LOG.warning("Ohne Manifest, nicht im Release: %s", treffer)
                    continue
                manifest = read_manifest(treffer / MANIFEST, streng=False) or {}
                if str(manifest.get("status", "")).lower() not in {"complete", "success"}:
                    LOG.warning("Nicht fertig, nicht im Release: %s", treffer)
                    continue
                for datei in sorted(treffer.rglob("*")):
                    rel = datei.relative_to(wurzel).as_posix()
                    if datei.is_file() and not paths.versteckt(rel):
                        dateien.append((datei, paths.relativ(schicht, rel)))
            elif treffer.is_file():
                dateien.append((treffer, paths.relativ(schicht, treffer.name)))
    return dateien


def sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with pfad.open("rb") as datei:
        for block in iter(lambda: datei.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tabellen_im(arbeit: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    """(Name, Parquet, Manifest) jeder Tabelle im Release, nach Schicht und Name."""
    gefunden = []
    for manifest_pfad in sorted(arbeit.glob(f"*/dataset=*/{MANIFEST}")):
        name = manifest_pfad.parent.name.removeprefix("dataset=")
        gefunden.append((name, manifest_pfad.parent / PARQUET_FILE,
                         read_manifest(manifest_pfad)))
    return gefunden


def release_manifest(arbeit: Path, kennung_: str, jetzt: datetime) -> dict[str, Any]:
    """Was ueber diesen Stand gesagt werden darf - aus den Manifesten darin."""
    tabellen: dict[str, Any] = {}
    vertraege: dict[str, int] = {}
    abdruck = None
    herkunft: dict[str, Any] = {}
    gate = None
    for name, parquet, manifest in tabellen_im(arbeit):
        schicht = parquet.parent.parent.name
        tabellen[f"{schicht}/{name}"] = {
            "rows": manifest.get("row_count", manifest.get("rows")),
            "contract_version": manifest.get("contract_version"),
            "built_at_utc": manifest.get("built_at_utc"),
            "input_fingerprint": manifest.get("input_fingerprint"),
        }
        if manifest.get("contract_version") is not None:
            vertraege[schicht if schicht == "gold" else f"{schicht}/{name}"] = \
                manifest["contract_version"]
        if name == "fact_offense":
            abdruck = manifest.get("input_fingerprint")
            herkunft = manifest.get("derived_from", {})
            gate = (manifest.get("reconciliation") or {}).get("coverage_percent")
    if not tabellen:
        raise ReleaseFehler(f"Kein Manifest unter {arbeit} - nichts, worueber ein "
                            "Release etwas sagen koennte")

    dateien = {
        p.relative_to(arbeit).as_posix(): {"sha256": sha256(p), "bytes": p.stat().st_size}
        for p in sorted(arbeit.rglob("*"))
        if p.is_file() and p.name != RELEASE_MANIFEST
    }
    return {
        "status": "complete",
        "release_id": kennung_,
        "created_at_utc": jetzt.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "code_version": code_stand(),
        "contract_versions": vertraege,
        "input_fingerprint": abdruck,
        "derived_from": herkunft,
        "gate": gate,
        "tables": tabellen,
        "files": dateien,
        "bytes": sum(d["bytes"] for d in dateien.values()),
    }


Ergaenzung = Callable[[Path, dict[str, Any]], None]


def erstelle(data_root: Path, *, ergaenze: Ergaenzung | None = None,
             pflicht: Iterable[str] = PFLICHT,
             kennung_: str | None = None, jetzt: datetime | None = None) -> Path:
    """Bildet ein Release lokal - vollstaendig oder gar nicht.

    Kopiert Gold und Serving, ruft ``ergaenze(arbeit, kern)`` - dort baut der
    Aufrufer, was ausser Kopien ins Release gehoert, etwa die selbstaendige
    Datenbank (``orchestration.release``) -, schreibt ``release.json`` und
    benennt zuletzt um. Danach zeigt das lokale ``AKTUELL.json`` darauf. Ein
    Abbruch laesst nichts Halbes zurueck.

    **Warum die Datenbank nicht hier gebaut wird.** ``storage`` ist ein
    Fundament: Es weiss, wie man Dateien ablegt und publiziert, nicht, was
    darin steht. Der Bau der Datenbank gehoert zu ``serving``, und ``serving``
    haengt an ``storage`` - anders herum waere es ein Zyklus, und der Wächter
    ueber den Importgraphen hat ihn beim ersten Versuch auch gefunden.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    kennung_ = kennung_ or kennung(jetzt)
    ziel = verzeichnis(data_root, kennung_)
    if ziel.exists():
        raise ReleaseFehler(f"Release gibt es schon: {ziel}. Releases sind "
                            "unveraenderlich; eine neue Kennung bekommt der naechste Lauf.")

    dateien = sammle(data_root)
    # Ein Eintrag der Pflichtliste ist entweder ein Tabellenverzeichnis
    # (``gold/dataset=fact_offense``) oder eine Datei (``serving/tracts.geojson``).
    vorhanden = {rel for _, rel in dateien} | {rel.rsplit("/", 1)[0] for _, rel in dateien}
    fehlend = [p for p in pflicht if p not in vorhanden]
    if fehlend:
        raise ReleaseFehler(
            f"Kein Release, es fehlt: {', '.join(fehlend)}. Ein Release ist der "
            "ganze Stand oder keiner - ein Teilstand, dem man es nicht ansieht, "
            "waere schlimmer als gar keiner. Zuerst bauen: "
            "python -m orchestration.run_all --ohne-ingestion"
        )

    arbeit = ziel.parent / f".{ziel.name}.part"
    shutil.rmtree(arbeit, ignore_errors=True)
    arbeit.mkdir(parents=True)
    try:
        for quelle, rel in dateien:
            (arbeit / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(quelle, arbeit / rel)

        if ergaenze is not None:
            ergaenze(arbeit, {
                "release_id": kennung_,
                "created_at_utc": jetzt.isoformat(timespec="seconds").replace("+00:00", "Z"),
            })

        manifest = release_manifest(arbeit, kennung_, jetzt)
        (arbeit / RELEASE_MANIFEST).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        arbeit.rename(ziel)
    except BaseException:
        shutil.rmtree(arbeit, ignore_errors=True)
        raise

    setze_aktuell(data_root / RELEASES / AKTUELL, manifest)
    LOG.info("Release %s: %d Dateien, %.1f MB -> %s",
             kennung_, len(manifest["files"]), manifest["bytes"] / 1e6, ziel)
    return ziel


def zeiger(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "release_id": manifest["release_id"],
        "created_at_utc": manifest["created_at_utc"],
        "path": relativ(manifest["release_id"]),
        "bytes": manifest.get("bytes"),
    }


def setze_aktuell(pfad: Path, manifest: dict[str, Any]) -> None:
    """Der lokale Zeiger - ueber ``.part`` und ``rename``, also unteilbar."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    arbeit = pfad.with_name(f".{pfad.name}.part")
    arbeit.write_text(json.dumps(zeiger(manifest), indent=2) + "\n", encoding="utf-8")
    arbeit.replace(pfad)


def lies(verzeichnis_: Path) -> dict[str, Any]:
    pfad = verzeichnis_ / RELEASE_MANIFEST
    if not pfad.is_file():
        raise ReleaseFehler(f"kein {RELEASE_MANIFEST} in {verzeichnis_}")
    return read_manifest(pfad, fehler=ReleaseFehler)


# ---------------------------------------------------------------------------
# Publizieren
# ---------------------------------------------------------------------------


def publiziere(storage: Storage, verzeichnis_: Path) -> list[str]:
    """Bringt ein Release nach SeaweedFS und legt den Zeiger um.

    Unveraenderlich wie ein Lauf: identisch oben wird uebersprungen, anders
    oben ist ein Fehler. ``release.json`` geht zuletzt hoch; erst dann wird
    ``AKTUELL.json`` ersetzt. Ohne publizierenden Modus passiert nichts,
    und das steht im Log.
    """
    if not storage.config.publiziert:
        LOG.info("Release nicht publiziert (STORAGE_BACKEND=%s): %s",
                 storage.backend, verzeichnis_)
        return []
    rel = storage.relativ(verzeichnis_)
    if rel is None:
        raise ReleaseFehler(f"ausserhalb der Ablagewurzel: {verzeichnis_}")
    manifest = lies(verzeichnis_)

    alle = [paths.relativ(rel, r) for r in manifest["files"]]
    oben = storage.publish_files(alle, ueberschreiben=False)
    oben += storage.publish_files([paths.relativ(rel, RELEASE_MANIFEST)], ueberschreiben=False)

    schluessel = paths.relativ(RELEASES, AKTUELL)
    try:
        storage.client.put(schluessel, (json.dumps(zeiger(manifest), indent=2) + "\n").encode("utf-8"))
    except Exception as fehler:  # noqa: BLE001 - jede Transportstoerung ist hier gleich
        raise PublishError(f"Zeiger nicht umgelegt: {storage.s3_path(schluessel)}: {fehler}") from fehler
    oben.append(schluessel)
    LOG.info("AKTUELL.json zeigt auf %s", manifest["release_id"])

    if storage.backend == "s3":
        shutil.rmtree(verzeichnis_, ignore_errors=True)
        LOG.info("Local release removed (STORAGE_BACKEND=s3): %s", rel)
    return oben


def erstelle_und_publiziere(data_root: Path, storage: Storage, *,
                            ergaenze: Ergaenzung | None = None,
                            pflicht: Iterable[str] = PFLICHT) -> dict[str, Any]:
    """Der Schritt am Ende eines gruenen Gesamtlaufs."""
    ziel = erstelle(data_root, ergaenze=ergaenze, pflicht=pflicht)
    manifest = lies(ziel)
    oben = publiziere(storage, ziel)
    return {
        "release_id": manifest["release_id"],
        "files": len(manifest["files"]),
        "bytes": manifest["bytes"],
        "published": bool(oben),
    }


# ---------------------------------------------------------------------------
# Holen und einsetzen
# ---------------------------------------------------------------------------


def hole(storage: Storage, was: str = "aktuell", *, nur_datenbank: bool = False) -> Path:
    """Ein Release von SeaweedFS in die lokale Wurzel - geprueft gegen ``release.json``.

    ``was`` ist eine Kennung oder ``aktuell``. Zuerst kommt ``release.json``,
    dann jede Datei darin; jede wird gegen ihre SHA-256 gehalten, nicht nur
    gegen das ETag. ``nur_datenbank`` holt allein ``serving/analyse.duckdb`` -
    fuer ein Dashboard, das nichts anderes braucht (Rat vom 17.9.2026,
    Schritte 3 bis 5). Was schon identisch da ist, wird nicht erneut geladen.
    """
    if was == "aktuell":
        zeiger = aktuell(storage)
        if zeiger is None:
            raise ReleaseFehler("Kein Zeiger - es wurde noch kein Release publiziert.")
        was = zeiger["release_id"]
    rel = relativ(was)
    manifest_pfad = storage.hole(paths.relativ(rel, RELEASE_MANIFEST))
    manifest = lies(manifest_pfad.parent)
    gewollt = [r for r in manifest["files"]
               if not nur_datenbank or r.endswith("/" + DATENBANK)]
    if nur_datenbank and not gewollt:
        raise ReleaseFehler(f"Release {was} enthaelt keine {DATENBANK}")
    for r in gewollt:
        pfad = storage.local_path(rel, r)
        angabe = manifest["files"][r]
        if pfad.is_file() and pfad.stat().st_size == angabe["bytes"] \
                and sha256(pfad) == angabe["sha256"]:
            continue
        storage.hole(paths.relativ(rel, r))
        if sha256(pfad) != angabe["sha256"]:
            pfad.unlink(missing_ok=True)
            raise ReleaseFehler(
                f"{r}: SHA-256 stimmt nicht mit release.json ueberein - die Datei "
                "oben ist nicht die, die das Release beschreibt. Geloescht."
            )
    ziel = manifest_pfad.parent
    if not nur_datenbank:
        setze_aktuell(storage.local_path(RELEASES, AKTUELL), manifest)
    LOG.info("Release %s geholt: %d Datei(en) -> %s", was, len(gewollt), ziel)
    return ziel


def einsetzen(data_root: Path, verzeichnis_: Path) -> list[Path]:
    """Die Tabellen eines Release an ihre festen Pfade setzen - Tabelle fuer Tabelle unteilbar.

    Danach liest, wer ``gold/dataset=...`` liest, genau den freigegebenen
    Stand. Die Manifeste kommen mit, deshalb sieht auch der Standvergleich der
    Ablage (Abschnitt 8) denselben Bauzeitpunkt wie oben. Eingesetzt wird nur,
    was das Release gegen seine Pruefsummen bestanden hat - also nur, was
    ``hole`` oder ``erstelle`` hingelegt hat.
    """
    manifest = lies(verzeichnis_)
    tabellen = sorted({r.rsplit("/", 1)[0] for r in manifest["files"] if "/dataset=" in r})
    eingesetzt: list[Path] = []
    for rel_dir in tabellen:
        quelle = verzeichnis_ / rel_dir
        for r, angabe in manifest["files"].items():
            if r.startswith(rel_dir + "/") and sha256(verzeichnis_ / r) != angabe["sha256"]:
                raise ReleaseFehler(f"{r}: Pruefsumme stimmt nicht - nicht eingesetzt")
        ziel = data_root / rel_dir
        arbeit = ziel.parent / f".{ziel.name}.release.part"
        verdraengt = ziel.parent / f".{ziel.name}.release.superseded"
        shutil.rmtree(arbeit, ignore_errors=True)
        shutil.rmtree(verdraengt, ignore_errors=True)
        shutil.copytree(quelle, arbeit)
        try:
            if ziel.exists():
                ziel.rename(verdraengt)
            arbeit.rename(ziel)
            shutil.rmtree(verdraengt, ignore_errors=True)
        except BaseException:
            shutil.rmtree(arbeit, ignore_errors=True)
            if verdraengt.exists() and not ziel.exists():
                verdraengt.rename(ziel)
            raise
        eingesetzt.append(ziel)
    for name in ("tracts.geojson", "tracts.manifest.json"):
        quelle = verzeichnis_ / "serving" / name
        if quelle.is_file():
            ziel = data_root / "serving" / name
            ziel.parent.mkdir(parents=True, exist_ok=True)
            arbeit = ziel.with_name(f".{name}.release.part")
            shutil.copy2(quelle, arbeit)
            arbeit.replace(ziel)
            eingesetzt.append(ziel)
    LOG.info("Release %s eingesetzt: %d Tabellen", manifest["release_id"], len(tabellen))
    return eingesetzt


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------


def aktuell(storage: Storage) -> dict[str, Any] | None:
    """Der Zeiger - lokal zuerst, sonst SeaweedFS; None, wenn es keinen gibt."""
    rel = paths.relativ(RELEASES, AKTUELL)
    if not storage.exists(rel):
        return None
    return json.loads(storage.read_text(rel))


def liste(storage: Storage) -> list[dict[str, Any]]:
    """Jedes Release, lokal oder oben, mit Kennung, Zeitpunkt, Groesse und Ort."""
    gefunden: dict[str, dict[str, Any]] = {}
    lokal = storage.local_path(RELEASES)
    if storage.config.liest_lokal and lokal.is_dir():
        for pfad in sorted(lokal.glob(f"release=*/{RELEASE_MANIFEST}")):
            if paths.versteckt(pfad.relative_to(lokal).as_posix()):
                continue
            m = read_manifest(pfad, streng=False) or {}
            k = kennung_aus(pfad.parent)
            gefunden[k] = {"release_id": k, "created_at_utc": m.get("created_at_utc"),
                           "bytes": m.get("bytes"), "wo": "lokal"}
    if storage.config.remote:
        for objekt in storage.client.list(RELEASES + "/"):
            if not objekt.key.endswith("/" + RELEASE_MANIFEST):
                continue
            k = kennung_aus(objekt.key.rsplit("/", 1)[0])
            if k in gefunden:
                gefunden[k]["wo"] = "beide"
                continue
            m = json.loads(storage.client.get(objekt.key).decode("utf-8"))
            gefunden[k] = {"release_id": k, "created_at_utc": m.get("created_at_utc"),
                           "bytes": m.get("bytes"), "wo": "oben"}
    return [gefunden[k] for k in sorted(gefunden)]
