"""Extrahiert Detroit RMS Crime Features unveraendert in den Bronze Layer.

Beispiele:

    python -m detroit_pipeline.extract_detroit --mode delta --years 2024
    python -m detroit_pipeline.extract_detroit --mode full \
        --years 2024 2025 --output-dir data/bronze/city=detroit

    python -m detroit_pipeline.extract_detroit --mode daily \
        --lookback-days 14 --output-dir data/bronze/city=detroit

Das Ergebnis besteht aus Parquet und Manifest in einem gemeinsam publizierten
Run-Verzeichnis. Die Feature-Daten werden in begrenzten Batches geschrieben.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import gzip
from hashlib import sha256
import json
import logging
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4
import pyarrow as pa
import pyarrow.parquet as pq

from manifeste import code_stand
from storage import for_root, get_storage
from .bronze_parquet import schema_for, schema_hash, to_row

from .detroit_arcgis import (
    ArcGISClient,
    DataQualityError,
    build_delta_where,
    build_local_date_window,
    delta_bedingung,
    build_updated_where,
    build_year_where,
    resolve_daily_window,
)


# Der Ladevertrag. Steht auf 2, seit das Abfragefenster am 11.9.2026 in
# Detroiter Ortszeit statt in UTC gezogen wird (Konzept 8.6) - Laeufe davor
# enthielten 66 Faelle aus 2023. Siehe "Vertragsversionen" in AENDERUNGEN.md.
CONTRACT_VERSION = 3

# Wie weit ein Delta hinter das Wasserzeichen zurueckgreift. Dieselben 14 Tage
# wie bei Chicago, und aus demselben Grund: Ein Lauf sieht den Stand der Quelle
# zu einem Zeitpunkt; was in den Stunden davor noch geschrieben wurde, kann ihm
# entgangen sein. Der Rueckgriff kostet doppelt geladene Zeilen - Silver
# dedupliziert sie ueber ``incident_entry_id`` und den juengsten ``updated_at``.
LOOKBACK_DAYS = 14


class Mitschrift:
    """Legt jede ArcGIS-Antwort unveraendert in der Raw-Schicht ab.

    Bronze hielt die Antwort der Quelle bisher nur **geparst** - je Zeile als
    ``_feature_json``. Das genuegt fuer die Auswertung, ist aber kein Beweis:
    Was der Dienst tatsaechlich geschickt hat, liess sich daraus nicht mehr
    zeigen. Detroit war damit die einzige der fuenf Quellen ohne Raw-Schicht,
    und Kapitel 7 des Konzepts macht die Trennung von Beweis und Ableitung zum
    Architekturprinzip.

    ``mtime=0`` macht die komprimierten Bytes zu einer reinen Funktion der
    Antwort - wie bei Chicago, damit der SHA-256 im Manifest reproduzierbar
    bleibt und nicht vom Zeitpunkt des Laufs abhaengt.
    """

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir
        self.dateien: list[dict[str, Any]] = []

    def __call__(self, name: str, body: bytes) -> None:
        pfad = self.work_dir / f"{len(self.dateien) + 1:04d}-{name}.json.gz"
        pfad.write_bytes(gzip.compress(body, mtime=0))
        self.dateien.append({
            "path": pfad.name,
            "sha256": sha256(body).hexdigest(),
            "size_bytes": pfad.stat().st_size,
            "bytes_unkomprimiert": len(body),
        })

    @property
    def bytes_roh(self) -> int:
        return sum(d["bytes_unkomprimiert"] for d in self.dateien)


def file_sha256(path: Path) -> str:
    """Berechnet die Checksumme des Bronze-Artefakts fuer Reproduzierbarkeit."""

    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict) -> None:
    """Schreibt JSON atomisch, damit nie ein halbes Manifest publiziert wird."""

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)


def _iso_utc(millisekunden: int | None) -> str | None:
    """Detroits Millisekunden seit Epoch als ISO-Zeitpunkt in UTC."""
    if millisekunden is None:
        return None
    return datetime.fromtimestamp(millisekunden / 1000, timezone.utc).isoformat(
        timespec="milliseconds")


def _extract_where(
    where: str,
    output_dir: Path,
    *,
    raw_dir: Path | None = None,
    file_stem: str,
    extraction_mode: str,
    date_field: str,
    window_start: date,
    window_end_exclusive: date,
    year: int | None = None,
    batch_size: int | None = None,
    pause_seconds: float = 0.05,
    client: ArcGISClient | None = None,
    watermark_vorher: str | None = None,
    delta_ab: datetime | None = None,
) -> tuple[Path, Path]:
    """Fuehrt einen count-verifizierten Snapshot fuer eine WHERE-Klausel aus.

    Schritte:

    1. Layer-Schema und ArcGIS-Limits lesen.
    2. Server-Count und feste Object-ID-Liste fuer das Jahr abfragen.
    3. Features ID-basiert in Batches in eine temporaere Parquet-Datei streamen.
    4. Downloadzahl und finalen Server-Count pruefen.
    5. Daten und Manifest gemeinsam als Run-Verzeichnis veroeffentlichen.
    """

    # Der optionale Client ermoeglicht einen isolierten Ingestion-Test ohne
    # Live-Netzwerk. Im produktiven Lauf wird automatisch der echte REST-Client
    # verwendet.
    client = client or ArcGISClient()
    if batch_size is not None and (type(batch_size) is not int or batch_size <= 0):
        raise ValueError('batch_size muss eine positive Ganzzahl sein')
    if pause_seconds < 0:
        raise ValueError('pause_seconds darf nicht negativ sein')
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)

    # Die drei Modi besitzen bewusst unterschiedliche fachliche Zeitachsen.
    # ``window_field`` traegt das Fenster, ``date_field`` die Auswahl - bei
    # FULL und INCREMENTAL dasselbe Feld, bei DELTA nicht: Das Fenster ist der
    # Tatjahrgang, ausgewaehlt wird darin nach Aenderungszeit. Diese
    # Invarianten verhindern, dass ein spaeterer Umbau einen Jahresbestand
    # versehentlich nach Update-Zeit oder einen Daily Load nach Tatzeit
    # selektiert.
    extraction_contracts = {
        "FULL": {
            "date_field": "incident_occurred_at",
            "window_field": "incident_occurred_at",
            "selection_basis": "INCIDENT_OCCURRENCE_TIME",
        },
        "DELTA": {
            "date_field": "updated_at",
            "window_field": "incident_occurred_at",
            "selection_basis": "SOURCE_LAST_UPDATED_TIME_WITHIN_INCIDENT_YEAR",
        },
        "INCREMENTAL": {
            "date_field": "updated_at",
            "window_field": "updated_at",
            "selection_basis": "SOURCE_LAST_UPDATED_TIME",
        },
    }
    contract = extraction_contracts.get(extraction_mode)
    if contract is None:
        raise ValueError(f"Nicht unterstuetzter Extraction Mode: {extraction_mode}")
    if date_field != contract["date_field"]:
        raise DataQualityError(
            f"{extraction_mode} muss {contract['date_field']} verwenden, "
            f"nicht {date_field}"
        )
    if (delta_ab is not None) != (extraction_mode == "DELTA"):
        raise DataQualityError(
            "Ein Startzeitpunkt gehoert zu DELTA und nur zu DELTA "
            f"(Modus {extraction_mode}, delta_ab={delta_ab!r})"
        )

    # Abfrage und Manifest muessen denselben lokalen Fenstervertrag erfuellen.
    window = build_local_date_window(window_start, window_end_exclusive)
    erwartet = window.where(contract["window_field"])
    if delta_ab is not None:
        erwartet = f"{erwartet} AND {delta_bedingung(delta_ab)}"
    if where != erwartet:
        raise DataQualityError("WHERE-Klausel passt nicht zum Detroit-Zeitfenster")

    # SCHRITT 1: Metadaten liefern Object-ID-Feld, Seitengroesse und Schema-Hash.
    layer_info = client.get_layer_info()
    for feld in {date_field, contract["window_field"]}:
        if feld not in layer_info.fields:
            raise DataQualityError(
                f"Erforderliches Datumsfeld fehlt im ArcGIS-Schema: {feld}"
            )
    effective_batch_size = min(
        batch_size or layer_info.max_record_count,
        layer_info.max_record_count,
    )

    # SCHRITT 2: Count und ID-Liste definieren die erwartete Snapshot-Groesse.
    source_count_before = client.get_count(where)
    object_id_field, object_ids = client.get_object_ids(where)
    if object_id_field != layer_info.object_id_field:
        raise DataQualityError(
            "Object-ID-Feld in Metadaten und Query-Antwort unterscheidet sich"
        )
    if source_count_before != len(object_ids):
        raise DataQualityError(
            f"Source-Count {source_count_before} != ID-Count {len(object_ids)}"
        )

    if len(set(object_ids)) != len(object_ids):
        raise DataQualityError('Doppelte Snapshot-IDs')

    output_dir.mkdir(parents=True, exist_ok=True)
    # Short filenames avoid the former Windows manifest path overflow.
    final_dir = output_dir / f'run_{run_id}'
    work_dir = output_dir / f'.run_{run_id}.partial'
    final_path = final_dir / 'part-0001.parquet'
    manifest_path = final_dir / 'manifest.json'
    temporary_path = work_dir / 'part-0001.parquet'
    schema = schema_for(layer_info)
    work_dir.mkdir()

    # Die Raw-Schicht faengt erst ab hier mit, nicht schon bei Metadaten und
    # Count: Vor diesem Punkt steht noch nicht fest, dass es ueberhaupt einen
    # Lauf gibt, und ein halb gefuelltes Raw-Verzeichnis waere kein Beweis,
    # sondern Abfall. Die drei Antworten davor sind Vorpruefungen; was der
    # Bestand ist, sagen die Feature-Batches.
    raw_final = raw_work = None
    client_mitschrift: Mitschrift | None = None
    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_final = raw_dir / f'run_{run_id}'
        raw_work = raw_dir / f'.run_{run_id}.partial'
        raw_work.mkdir()
        client_mitschrift = Mitschrift(raw_work)
        client.aufzeichner = client_mitschrift

    # SCHRITT 3: Jede rohe ArcGIS-Zeile wird inklusive technischer Provenance
    # sofort geschrieben. Fachliche Transformationen gehoeren nicht in Bronze.
    downloaded_count = 0
    offense_category_counts: dict[str, int] = {}
    # Der hoechste gesehene Aenderungszeitpunkt - das Wasserzeichen des
    # naechsten Laufs. Gelesen wird die rohe Quellzahl (Millisekunden seit
    # Epoch), abgelegt wird sie als ISO-Zeitpunkt in UTC: lesbar, sortierbar,
    # und ohne Zeitzone kein Missverstaendnis.
    max_updated_at: int | None = None
    remaining_ids = set(object_ids)
    extra_rows = 0
    try:
        with pq.ParquetWriter(temporary_path, schema, compression='zstd') as writer:
            rows = []
            for feature in client.iter_features(
                object_ids,
                object_id_field=object_id_field,
                batch_size=effective_batch_size,
                pause_seconds=pause_seconds,
            ):
                oid = (feature.get('attributes') or {}).get(object_id_field)
                if type(oid) is not int or oid not in remaining_ids:
                    raise DataQualityError(f'Doppelte, unerwartete oder ungueltige ID: {oid}')
                remaining_ids.remove(oid)
                row = to_row(feature, schema, run_id, started_at)
                extra_rows += row['_extra'] is not None
                rows.append(row)
                if len(rows) >= effective_batch_size:
                    writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                    rows.clear()
                downloaded_count += 1
                raw_category = (feature.get("attributes") or {}).get(
                    "offense_category"
                )
                category = str(raw_category).strip() if raw_category is not None else ""
                category = category or "__MISSING__"
                offense_category_counts[category] = (
                    offense_category_counts.get(category, 0) + 1
                )
                stempel = (feature.get("attributes") or {}).get("updated_at")
                if type(stempel) is int and (max_updated_at is None
                                             or stempel > max_updated_at):
                    max_updated_at = stempel
            if rows:
                writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        if downloaded_count != len(object_ids):
            raise DataQualityError(
                f"Download-Count {downloaded_count} != ID-Count {len(object_ids)}"
            )
        if remaining_ids or sum(offense_category_counts.values()) != downloaded_count:
            raise DataQualityError('Snapshot oder Kategoriesumme inkonsistent')
        with pq.ParquetFile(temporary_path) as parquet:
            if parquet.metadata.num_rows != downloaded_count:
                raise DataQualityError('Parquet-Zeilenzahl inkonsistent')
        # Publication is deliberately deferred until all metadata is ready.
        source_count_after = client.get_count(where, name="count_nachher")
        finished_at = datetime.now(timezone.utc)
        checksum = file_sha256(temporary_path)
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        if raw_work is not None:
            shutil.rmtree(raw_work, ignore_errors=True)
        raise
    finally:
        client.aufzeichner = None

    # SCHRITT 4: Der zweite Count dokumentiert, ob sich die Live-Quelle waehrend
    # des Laufs veraendert hat. Die feste ID-Liste bleibt der Snapshot-Vertrag.

    # SCHRITT 5: Das Manifest macht Vollstaendigkeit, Laufzeit, Filter und
    # Quellzustand maschinenlesbar und kann spaeter vom Monitoring gelesen werden.
    manifest = {
        # Detroit fuehrt seit jeher drei feinere Vertraege (bronze_, raw_,
        # window_). contract_version ist die gemeinsame Angabe aller fuenf
        # Quellen und traegt hier dieselbe Zahl wie der Bronze-Vertrag.
        "contract_version": CONTRACT_VERSION,
        "code_version": code_stand(),
        "bronze_contract_version": 2,
        "storage_format": "PARQUET",
        "compression": "ZSTD",
        "immutable": True,
        "storage_schema_fingerprint": schema_hash(schema),
        "storage_schema": str(schema),
        "source_field_types": dict(layer_info.field_types),
        "rows_with_extra": extra_rows,
        "snapshot_membership_verified": True,
        "snapshot_ids_sha256": sha256(','.join(map(str, sorted(object_ids))).encode()).hexdigest(),
        "payload_contract": (
            "_feature_json preserves parsed source JSON; the delivered HTTP "
            "bytes are in the raw layer"
            if raw_work is not None else
            "_feature_json preserves parsed source JSON; not HTTP bytes"
        ),
        "files": [{"path": "part-0001.parquet", "sha256": checksum,
                   "size_bytes": temporary_path.stat().st_size}],
        "raw_layer": (
            {
                "path": str(raw_final),
                "responses": len(client_mitschrift.dateien),
                "bytes_delivered": client_mitschrift.bytes_roh,
                "bytes_stored": sum(d["size_bytes"] for d in client_mitschrift.dateien),
                "files": client_mitschrift.dateien,
            }
            if raw_work is not None else None
        ),
        "pipeline_run_id": run_id,
        "status": "SUCCESS",
        "source_system": "detroit_rms_crime",
        "dataset_id": "RMS_Crime_Incidents",
        "layer_url": client.layer_url,
        "extraction_mode": extraction_mode,
        "date_field": date_field,
        "selection_basis": contract["selection_basis"],
        "record_granularity": "INCIDENT_OFFENSE",
        "window_is_half_open": True,
        "captures_source_deletions": False,
        "window_start": window_start.isoformat(),
        "window_end_exclusive": window_end_exclusive.isoformat(),
        **window.manifest_fields(),
        "year": year,
        "where": where,
        "object_id_field": object_id_field,
        "schema_fingerprint": layer_info.schema_fingerprint,
        "source_count_before": source_count_before,
        "snapshot_object_id_count": len(object_ids),
        "downloaded_count": downloaded_count,
        "offense_category_counts": dict(sorted(offense_category_counts.items())),
        "source_count_after": source_count_after,
        "source_changed_during_run": source_count_before != source_count_after,
        "batch_size": effective_batch_size,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "bronze_file": "part-0001.parquet",
        "bronze_sha256": checksum,
        # Das Wasserzeichen: der hoechste gesehene Aenderungszeitpunkt, und der
        # vorherige daneben. Es rueckt nie zurueck - ein Lauf, der nichts
        # Neueres sieht, laesst es stehen.
        "watermark": {
            "field": "updated_at",
            "maximum_seen": max(
                [w for w in (watermark_vorher, _iso_utc(max_updated_at)) if w],
                default=None,
            ),
            "previous_maximum": watermark_vorher,
            "lookback_days": LOOKBACK_DAYS,
            # Ab wo dieser Lauf tatsaechlich gesucht hat: Wasserzeichen minus
            # Rueckgriff. ``None`` heisst Vollschnappschuss.
            "delta_from_utc": delta_ab.astimezone(timezone.utc).isoformat()
                              if delta_ab is not None else None,
        },
    }
    # Raw zuerst veroeffentlichen, Bronze danach. Ein Raw-Lauf ohne
    # Bronze-Zwilling kostet eine Wiederholung; umgekehrt stuende eine
    # abgeleitete Tabelle ohne ihren Beweis da - und niemand saehe es ihr an.
    try:
        if raw_work is not None:
            write_json_atomic(raw_work / 'manifest.json', {
                "raw_contract_version": 1,
                "immutable": True,
                "status": "SUCCESS",
                "source_system": manifest["source_system"],
                "dataset_id": manifest["dataset_id"],
                "layer_url": manifest["layer_url"],
                "pipeline_run_id": run_id,
                "format": "application/json (gzip, eine ArcGIS-Antwort je Datei)",
                "note": (
                    "Jede Datei ist die Antwort des Dienstes, Byte fuer Byte, "
                    "vor dem Parsen abgelegt. Metadaten- und Count-Abrufe vor "
                    "dem eigentlichen Download sind Vorpruefungen und nicht "
                    "enthalten."
                ),
                "responses": len(client_mitschrift.dateien),
                "bytes_delivered": client_mitschrift.bytes_roh,
                "files": client_mitschrift.dateien,
                "derived_to": f"bronze/.../{run_id}",
                "started_at": manifest["started_at"],
                "finished_at": manifest["finished_at"],
            })
            raw_work.rename(raw_final)
        write_json_atomic(work_dir / 'manifest.json', manifest)
        work_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        if raw_work is not None:
            shutil.rmtree(raw_work, ignore_errors=True)
        raise
    return final_path, manifest_path


def previous_watermark(data_root: Path, year: int) -> str | None:
    """Das hoechste Wasserzeichen aus vollstaendigen Detroit-Bronze-Laeufen.

    Dasselbe Muster wie bei Chicago, und aus demselben Grund: Bronze wird
    zuletzt veroeffentlicht, das Wasserzeichen rueckt also erst vor, wenn der
    ganze Lauf stand. Ein Raw-Lauf ohne Bronze-Zwilling kostet eine
    Wiederholung, nie eine Luecke.

    **Warum nicht ein Kalenderrueckgriff.** ``--mode daily`` zieht ein Fenster
    von *gestern minus vierzehn Tagen*. Laeuft die Strecke drei Wochen nicht,
    fehlt eine Woche - und niemand sieht es den Daten an. Ein Wasserzeichen
    kennt den letzten wirklich geladenen Stand; der Rueckgriff ist dann eine
    Sicherheitsmarge, keine Annahme ueber die Laufhaeufigkeit.

    Gezaehlt werden nur Laeufe desselben Jahrgangs und ohne ``--max-records``:
    Ein abgeschnittener Testlauf darf das Wasserzeichen nicht vorruecken.
    """
    werte: list[str] = []
    laeufe = for_root(data_root).laeufe(
        "bronze/city=detroit", "**/run_*/manifest.json",
        streng=False, fehler=DataQualityError,
    )
    for lauf in laeufe:
        manifest = lauf.manifest
        if (
            str(manifest.get("status", "")).upper() == "SUCCESS"
            and manifest.get("year") == year
            and manifest.get("max_records") is None
        ):
            wert = (manifest.get("watermark") or {}).get("maximum_seen")
            if wert:
                werte.append(str(wert))
    # Textvergleich; die Werte sind ISO-Zeitpunkte fester Breite in UTC.
    return max(werte, default=None)


def delta_start(watermark: str | None) -> datetime | None:
    """Das Wasserzeichen minus dem Rueckgriff - oder ``None`` beim ersten Lauf."""
    if watermark is None:
        return None
    try:
        wert = datetime.fromisoformat(str(watermark).replace("Z", "+00:00"))
    except ValueError as fehler:
        raise DataQualityError(f"Unlesbares Wasserzeichen: {watermark!r}") from fehler
    if wert.tzinfo is None:
        wert = wert.replace(tzinfo=timezone.utc)
    return wert - timedelta(days=LOOKBACK_DAYS)


def extract_delta(
    year: int,
    output_dir: Path,
    *,
    data_root: Path | None = None,
    raw_dir: Path | None = None,
    batch_size: int | None = None,
    pause_seconds: float = 0.05,
    client: ArcGISClient | None = None,
    watermark: str | None = None,
) -> tuple[Path, Path]:
    """Der Jahrgang beim ersten Lauf, danach nur noch das Geaenderte.

    Genau wie Chicago: Ohne Wasserzeichen ein Vollschnappschuss, mit einem nur
    die Zeilen, deren ``updated_at`` seit dem letzten Lauf (minus Rueckgriff)
    bewegt wurde. Der Jahresfilter bleibt in beiden Faellen.

    **Dass das traegt, ist gemessen.** Zwischen vier Schnappschuessen haben
    sich 1'270 Zeilen inhaltlich geaendert - Beschreibung, Code, Kategorie,
    Fallstatus, Tatzeitpunkt oder Koordinate. **Jede einzelne** trug dabei
    einen neuen ``updated_at``; keine aenderte sich ohne. Umgekehrt bewegte
    sich der Stempel 499-mal ohne inhaltliche Aenderung - das kostet nur
    doppelt geladene Zeilen, die Silver ohnehin dedupliziert.
    """
    if watermark is None and data_root is not None:
        watermark = previous_watermark(data_root, year)
    ab = delta_start(watermark)
    return _extract_where(
        build_delta_where(year, ab),
        output_dir,
        raw_dir=raw_dir,
        file_stem=(f"detroit_rms_crime_{year}" if ab is None
                   else f"detroit_rms_crime_delta_{year}_{ab.date().isoformat()}"),
        extraction_mode="FULL" if ab is None else "DELTA",
        date_field="incident_occurred_at" if ab is None else "updated_at",
        window_start=date(year, 1, 1),
        window_end_exclusive=date(year + 1, 1, 1),
        year=year,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
        client=client,
        watermark_vorher=watermark,
        delta_ab=ab,
    )


def extract_year(
    year: int,
    output_dir: Path,
    *,
    raw_dir: Path | None = None,
    batch_size: int | None = None,
    pause_seconds: float = 0.05,
    client: ArcGISClient | None = None,
) -> tuple[Path, Path]:
    """Laedt einen vollstaendigen Kalenderjahresbestand nach Tatzeitpunkt."""

    window_start = date(year, 1, 1)
    window_end_exclusive = date(year + 1, 1, 1)
    return _extract_where(
        build_year_where(year),
        output_dir,
        raw_dir=raw_dir,
        file_stem=f"detroit_rms_crime_{year}",
        extraction_mode="FULL",
        date_field="incident_occurred_at",
        window_start=window_start,
        window_end_exclusive=window_end_exclusive,
        year=year,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
        client=client,
    )


def extract_updated_window(
    start_date: date,
    end_date_exclusive: date,
    output_dir: Path,
    *,
    raw_dir: Path | None = None,
    batch_size: int | None = None,
    pause_seconds: float = 0.05,
    client: ArcGISClient | None = None,
) -> tuple[Path, Path]:
    """Laedt neue und geaenderte Records eines halb-offenen Daily-Fensters.

    Der Filter verwendet ``updated_at``. Dadurch werden auch Korrekturen an
    aelteren Delikten erfasst. Das bewusste 14-Tage-Overlap muss Silver
    idempotent per ``offense_key`` und neuestem Update-Zeitpunkt konsolidieren.
    """

    where = build_updated_where(start_date, end_date_exclusive)
    return _extract_where(
        where,
        output_dir,
        raw_dir=raw_dir,
        file_stem=(
            "detroit_rms_crime_incremental_"
            f"{start_date.isoformat()}_{end_date_exclusive.isoformat()}"
        ),
        extraction_mode="INCREMENTAL",
        date_field="updated_at",
        window_start=start_date,
        window_end_exclusive=end_date_exclusive,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
        client=client,
    )


def format_load_summary(category_counts: dict[str, int], total: int) -> str:
    """Formatiert Kategorie- und Gesamtzahlen fuer Notebook, CLI und Tests.

    Die Summe der Kategorien wird bewusst gegen ``total`` validiert. Dadurch
    kann ein Fehler beim Zaehlen nicht unbemerkt in den Run-Report gelangen.
    """

    category_total = sum(category_counts.values())
    if category_total != total:
        raise DataQualityError(
            f"Kategoriesumme {category_total} != Gesamtzahl {total}"
        )
    lines = ["Geladene Datensaetze pro Deliktkategorie:"]
    width = max((len(category) for category in category_counts), default=10)
    for category, count in sorted(category_counts.items()):
        lines.append(f"  {category:<{width}} : {count:>8}")
    lines.append(f"  {'INSGESAMT':<{width}} : {total:>8}")
    return "\n".join(lines)


def parse_iso_date(value: str) -> date:
    """Liest ein reproduzierbares CLI-Referenzdatum im Format YYYY-MM-DD."""

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Ungueltiges Datum {value!r}; erwartet wird YYYY-MM-DD"
        ) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Definiert und validiert die CLI fuer Full- und Daily-Laeufe.

    ``full`` benoetigt mindestens ein Jahr. ``daily`` verwendet standardmaessig
    die letzten 14 lokalen Detroit-Kalendertage bis einschliesslich des
    abgeschlossenen Detroit-Vortags. Ein explizites Referenzdatum erlaubt
    reproduzierbare Backfills und bezeichnet den letzten eingeschlossenen Tag.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("delta", "full", "daily"),
        help="delta (Vorgabe fuer den Gesamtlauf): erster Aufruf laedt den "
             "Jahrgang voll, spaetere nur Geaendertes seit dem Wasserzeichen. "
             "full: immer der ganze Jahrgang. daily: Kalenderfenster, ohne "
             "Wasserzeichen",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        help="Kalenderjahre fuer Full, z. B. --years 2024 2025",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=14,
        help="Anzahl lokaler Detroit-Kalendertage im Daily-Fenster",
    )
    parser.add_argument(
        "--reference-date",
        type=parse_iso_date,
        default=None,
        help=(
            "Optionaler letzter eingeschlossener Detroit-Tag (YYYY-MM-DD); "
            "ohne Angabe wird der abgeschlossene Vortag verwendet"
        ),
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT). Setzt "
             "--output-dir und --raw-dir, wenn die nicht einzeln genannt sind",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Zielverzeichnis fuer Bronze und Manifest "
             "(Vorgabe: <data-root>/bronze/city=detroit)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help=(
            "Zielverzeichnis fuer die Raw-Schicht: jede ArcGIS-Antwort "
            "unveraendert als gzip. --no-raw schaltet sie ab"
        ),
    )
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Keine Raw-Schicht schreiben (nur Bronze wie vor dem 12.9.)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Optional kleinere Batch-Groesse; ArcGIS-Maximum wird respektiert",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.05,
        help="Pause zwischen Batches zur Schonung der API",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    args = parser.parse_args(argv)
    # Dieselbe Option wie bei den uebrigen elf Stufen. Sie fehlte hier, und
    # damit lief Detroit auch dann im Standardverzeichnis, wenn der
    # Gesamtlauf mit --data-root auf ein anderes gerichtet war.
    wurzel = for_root(args.data_root).local_root
    if args.output_dir is None:
        args.output_dir = wurzel / "bronze" / "city=detroit"
    if args.raw_dir is None:
        args.raw_dir = wurzel / "raw" / "city=detroit"

    if args.mode in ("full", "delta"):
        if not args.years:
            parser.error(f"--years ist fuer --mode {args.mode} erforderlich")
        if args.reference_date is not None:
            parser.error("--reference-date ist nur fuer --mode daily erlaubt")
    else:
        if args.years:
            parser.error("--years ist fuer --mode daily nicht erlaubt")
        if args.lookback_days <= 0:
            parser.error("--lookback-days muss groesser als 0 sein")

    if args.batch_size is not None and args.batch_size <= 0:
        parser.error("--batch-size muss groesser als 0 sein")
    if args.pause_seconds < 0:
        parser.error("--pause-seconds darf nicht negativ sein")
    return args


def print_extraction_result(bronze_path: Path, manifest_path: Path) -> None:
    """Gibt Artefaktpfade und die im Manifest gespeicherte Statistik aus."""

    print(f"Bronze:   {bronze_path}")
    print(f"Manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print()
    print(
        format_load_summary(
            manifest["offense_category_counts"], manifest["downloaded_count"]
        )
    )


def main(argv: list[str] | None = None) -> int:
    """Startet einen Full- oder Daily-Bronze-Load als CLI-Job."""

    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.mode == "delta":
        for year in args.years:
            wurzel = for_root(args.data_root).local_root
            watermark = previous_watermark(wurzel, year)
            logging.info(
                "Starte Detroit %s fuer %s%s",
                "Full Load" if watermark is None else "Delta",
                year,
                "" if watermark is None else f" (Wasserzeichen {watermark})",
            )
            raw_dir = None if args.no_raw else args.raw_dir / "full" / f"year={year}"
            bronze_path, manifest_path = extract_delta(
                year=year,
                output_dir=args.output_dir / "full" / f"year={year}",
                data_root=wurzel,
                raw_dir=raw_dir,
                batch_size=args.batch_size,
                pause_seconds=args.pause_seconds,
                watermark=watermark,
            )
            print_extraction_result(bronze_path, manifest_path)
            publiziere(bronze_path.parent, raw_dir)
        return 0

    if args.mode == "full":
        for year in args.years:
            logging.info("Starte Detroit Full Load fuer %s", year)
            raw_dir = None if args.no_raw else args.raw_dir / "full" / f"year={year}"
            bronze_path, manifest_path = extract_year(
                year=year,
                output_dir=args.output_dir / "full" / f"year={year}",
                raw_dir=raw_dir,
                batch_size=args.batch_size,
                pause_seconds=args.pause_seconds,
            )
            print_extraction_result(bronze_path, manifest_path)
            publiziere(bronze_path.parent, raw_dir)
        return 0

    daily_window = resolve_daily_window(
        reference_date=args.reference_date,
        lookback_days=args.lookback_days,
    )
    window_start = daily_window.start_local.date()
    window_end_exclusive = daily_window.end_local.date()
    run_date = window_end_exclusive - timedelta(days=1)

    logging.info(
        "Starte Detroit Daily Load: %s bis %s (exklusiv)",
        window_start,
        window_end_exclusive,
    )
    raw_dir = (None if args.no_raw else
               args.raw_dir / "incremental" / f"run_date={run_date.isoformat()}")
    bronze_path, manifest_path = extract_updated_window(
        start_date=window_start,
        end_date_exclusive=window_end_exclusive,
        output_dir=(
            args.output_dir / "incremental" / f"run_date={run_date.isoformat()}"
        ),
        raw_dir=raw_dir,
        batch_size=args.batch_size,
        pause_seconds=args.pause_seconds,
    )
    print_extraction_result(bronze_path, manifest_path)
    publiziere(bronze_path.parent, raw_dir)
    return 0


def publiziere(bronze_final: Path, raw_dir: Path | None) -> None:
    """Nach dem finalen Umbenennen: erst den Raw-Lauf, dann den Bronze-Lauf.

    Beide liegen bereits unter ihrem endgueltigen Namen, mit Manifest - die
    bestehenden Pruefungen (Count-Abgleich, Snapshot-IDs, Schema) sind
    durch. Was hier nicht ankommt, hat sie nicht bestanden. Liegt ein
    ``--output-dir`` ausserhalb von LOCAL_DATA_ROOT, sagt die Ablage das und
    publiziert nicht.
    """
    ablage = get_storage()
    if raw_dir is not None:
        ablage.publish_run(raw_dir / bronze_final.name)
    ablage.publish_run(bronze_final)


if __name__ == "__main__":
    raise SystemExit(main())
