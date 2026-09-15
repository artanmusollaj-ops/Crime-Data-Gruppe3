"""Die Silver-Schicht: aus mehreren Quellen werden vergleichbare Tabellen.

Bronze haelt je Quelle einen unveraenderten Schnappschuss. Silver ist die
erste Schicht, die **deutet**: Typen setzen, Einheiten aufloesen, Fehlwerte
als solche kennzeichnen, Schluessel harmonisieren, Quellen zusammenfuehren.

Die Quellen haben drei verschiedene Koerner, deshalb gibt es nicht eine
Tabelle, sondern drei:

===========================  ==========================================
``tract``                    eine Zeile je Census Tract
``crime_offense``            eine Zeile je Delikt
``weather_day``              eine Zeile je Stadt und Tag
===========================  ==========================================

Sie in eine Tabelle zu zwingen wuerde entweder Zeilen vervielfachen - ein
Wetterwert an jedem Delikt derselben Stadt und desselben Tages - oder
Information wegwerfen. Zusammengefuehrt wird erst in Gold, dort auf dem
Aggregationsebene.

Werkzeug ist DuckDB, fuer den raeumlichen Join mit der ``spatial``-Extension
(Absprache 5.3). Es liest Bronze direkt, gleichgueltig ob Parquet oder NDJSON,
sodass die noch offene Formatfrage aus Absprache 4.1 die Silver-Schicht nicht
aufhaelt.

Anders als Bronze sind Silver-Tabellen **abgeleitet und wiederherstellbar**.
Sie werden deshalb ersetzt und nicht als Lauf angehaeuft; das Manifest nennt
aber die ``run_id`` jedes Bronze-Laufs, aus dem die Tabelle entstanden ist -
ohne diese Herkunft ist der Referenzstand aus Absprache 7.1 nicht belegbar.

Dieses Modul haelt, was alle Bausteine teilen: Fehlerart, Manifestzugriff,
Laufauswahl, Verbindung und das atomare Veroeffentlichen.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from typing import Any

import duckdb

from manifeste import Lauf
from storage import Storage, get_storage
from storage import duckdb as storage_duckdb


SILVER_LAYER = "silver"
BRONZE_LAYER = "bronze"
PARQUET_FILE = "part-0001.parquet"

# Die beiden Staedte des Projekts, ueber ihre FIPS-Ortsnummer. Ueber den Namen
# zu gehen waere falsch: Illinois fuehrt neben Chicago city auch ein Detroit
# village.
#
# Der Wert ist der **amtliche Name, wie TIGER ihn schreibt** - gross. Genau so
# prueft ``build_place``, dass eine GEOID auf den Ort zeigt, den wir meinen.
# Gold braucht denselben Ort als kleingeschriebenen Verbundschluessel (die
# Spalte ``city`` in ``crime_offense``) und leitet ihn hieraus ab; siehe
# ``gold_pipeline.STADT_SCHLUESSEL``.
#
# **Eine dritte Stadt wird genau hier eingetragen, sonst nirgends.** Bis zum
# 14.9.2026 stand diese Zuordnung zweimal im Projekt - einmal gross, einmal
# klein -, und wer sie erweitert haette, haette eine der beiden vergessen.
STUDIENSTAEDTE = {
    "1714000": "Chicago",
    "2622000": "Detroit",
}

# Der Fehlwert des ACS. In Bronze bleibt er unveraendert stehen; ihn zu deuten
# ist ausdruecklich Aufgabe dieser Schicht.
ACS_MISSING_VALUE = "-666666666"


class TransformError(RuntimeError):
    """Eine Silver-Tabelle konnte nicht sicher gebaut werden."""


def read_manifest(directory: Path) -> dict[str, Any]:
    """Liest das Manifest eines Laufs oder einer Tabelle."""
    pfad = directory / "manifest.json"
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformError(f"Invalid manifest: {pfad}") from error


def newest_complete_run(storage: Storage, prefix: str, *, what: str) -> Lauf:
    """Der juengste vollstaendige Bronze-Lauf unter ``prefix`` (relativ zur Ablage).

    Gelesen wird das Manifest und nicht das Verzeichnis: Ein Lauf zaehlt nur
    mit ``status == "complete"``. Die ``run_id`` ist ein UTC-Zeitstempel,
    deshalb ist der letzte sortierte Eintrag der juengste. Woher der Lauf
    kommt - lokal oder SeaweedFS -, entscheidet die Ablage; die Parquet-Datei
    wird ueber ``storage.resolve_read_path(lauf.relativ, PARQUET_FILE)`` gelesen.
    """
    kandidaten = []
    for lauf in storage.laeufe(prefix, "run_*/manifest.json", fehler=TransformError):
        if not storage.exists(lauf.relativ, PARQUET_FILE):
            raise TransformError(f"Lauf ohne Parquet-Datei: {lauf.relativ}")
        kandidaten.append(lauf)

    if not kandidaten:
        raise TransformError(
            f"Kein vollstaendiger Bronze-Lauf fuer {what}. "
            "Zuerst die Ingestion starten."
        )
    return kandidaten[-1]


def connect(*, spatial: bool = False) -> duckdb.DuckDBPyConnection:
    """Eine DuckDB-Verbindung, auf Wunsch mit der ``spatial``-Extension.

    Kann die Ablage S3 lesen, bringt die Verbindung ``httpfs`` und ein
    temporaeres Secret mit - siehe ``storage.duckdb``.
    """
    try:
        con = storage_duckdb.connect(get_storage().config)
    except storage_duckdb.DuckDBFehler as error:
        raise TransformError(str(error)) from error
    if spatial:
        try:
            con.execute("INSTALL spatial")
            con.execute("LOAD spatial")
        except duckdb.Error as error:
            raise TransformError(
                f"spatial-Extension nicht verfuegbar: {error}"
            ) from error
    return con


def publish(
    con: duckdb.DuckDBPyConnection,
    relation: str,
    target: Path,
    manifest: dict[str, Any],
) -> Path:
    """Schreibt Parquet und Manifest und veroeffentlicht sie atomar.

    Silver ist abgeleitet und wird ersetzt, nicht angehaeuft. Ersetzt wird
    trotzdem in drei Schritten, damit nie ein halber Stand sichtbar ist: neu
    schreiben, alt beiseiteschieben, neu einhaengen, alt entfernen. Scheitert
    etwas, bleibt der vorherige Stand unberuehrt.

    **Warum die Arbeitsverzeichnisse die Prozessnummer tragen.** Sie hiessen
    bis zum 15.9.2026 fest ``.<name>.part`` und ``.<name>.superseded``, und
    jeder Lauf raeumte sie zu Beginn weg - auch die eines anderen, der gerade
    schrieb. Zwei gleichzeitige Laeufe derselben Tabelle zerstoerten einander
    also das halbfertige Ergebnis. Mit eigenem Namen je Prozess kann das nicht
    mehr passieren; das abschliessende ``rename`` ist atomar, ein Leser sieht
    danach den einen oder den anderen vollstaendigen Stand.

    Was das **nicht** loest: Zwei gleichzeitige Gesamtlaeufe koennen die fuenf
    Gold-Tabellen verschraenkt ersetzen. Dagegen hilft nur eine Sperre ueber
    den ganzen Lauf; das steht im Ausblick.
    """
    kennung = f"{os.getpid()}"
    arbeit = target.parent / f".{target.name}.{kennung}.part"
    verdraengt = target.parent / f".{target.name}.{kennung}.superseded"
    shutil.rmtree(arbeit, ignore_errors=True)
    shutil.rmtree(verdraengt, ignore_errors=True)
    arbeit.mkdir(parents=True)

    try:
        parquet = arbeit / PARQUET_FILE
        con.execute(
            f"COPY {relation} TO '{parquet}' (FORMAT PARQUET, COMPRESSION SNAPPY)"
        )
        (arbeit / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if target.exists():
            target.rename(verdraengt)
        arbeit.rename(target)
        shutil.rmtree(verdraengt, ignore_errors=True)
        return target
    except BaseException:
        shutil.rmtree(arbeit, ignore_errors=True)
        if verdraengt.exists() and not target.exists():
            verdraengt.rename(target)
        shutil.rmtree(verdraengt, ignore_errors=True)
        raise


def schema_of(con: duckdb.DuckDBPyConnection, relation: str) -> dict[str, str]:
    """Spaltennamen und -typen der Relation, fuer das Manifest."""
    namen, typen = con.execute(
        f"SELECT list(column_name), list(column_type) "
        f"FROM (DESCRIBE SELECT * FROM {relation})"
    ).fetchone()
    return dict(zip(namen, typen))
