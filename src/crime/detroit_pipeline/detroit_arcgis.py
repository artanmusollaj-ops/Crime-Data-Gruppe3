"""Gemeinsame Funktionen fuer die Detroit Crime ArcGIS REST Pipeline.

Dieses Modul enthaelt bewusst sowohl den kleinen ArcGIS-HTTP-Client als auch
die deterministische Transformation einer rohen ArcGIS-Feature-Zeile. Die
eigentlichen Kommandozeilenprogramme befinden sich in ``extract_detroit.py``
und ``transform_detroit.py``.

Die Implementierung verwendet fuer den Download nur die Python-Standard-
bibliothek. Dadurch kann die Bronze-Extraktion auch in einer sehr schlanken
Laufzeitumgebung ausgefuehrt werden. Fuer Parquet wird erst im Transformations-
skript optional ``pyarrow`` benoetigt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from hashlib import sha256
import json
import logging
import random
import time
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


DETROIT_LAYER_URL = (
    "https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/"
    "RMS_Crime_Incidents/FeatureServer/0"
)
SOURCE_SYSTEM = "detroit_rms_crime"
SOURCE_DATASET_ID = "RMS_Crime_Incidents"
SOURCE_TIMEZONE = ZoneInfo("America/Detroit")

# Nur fachlich explizit freigegebene Werte werden in die vergleichbaren
# Kategorien uebernommen. Neue Werte bleiben UNREVIEWED statt stillschweigend
# in OTHER zu landen.
OFFENSE_MAPPING: dict[str, str] = {
    "ROBBERY": "ROBBERY",
    "BURGLARY": "BURGLARY",
    "LARCENY": "THEFT",
    "STOLEN VEHICLE": "VEHICLE_THEFT",
    "ASSAULT": "ASSAULT",
    "AGGRAVATED ASSAULT": "ASSAULT",
}

RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


class ArcGISRequestError(RuntimeError):
    """Signalisiert einen HTTP-, Netzwerk- oder ArcGIS-API-Fehler."""


class DataQualityError(RuntimeError):
    """Signalisiert, dass ein Vollstaendigkeits-Gate verletzt wurde."""


@dataclass(frozen=True)
class ArcGISLayerInfo:
    """Die fuer die Extraktion benoetigten Eigenschaften eines Feature Layers."""

    object_id_field: str
    max_record_count: int
    schema_fingerprint: str
    fields: tuple[str, ...]
    field_types: tuple[tuple[str, str], ...] = ()


def chunked(values: Sequence[int], size: int) -> Iterator[Sequence[int]]:
    """Teilt Object-IDs in API-vertraegliche Batches.

    ArcGIS begrenzt die Anzahl zurueckgegebener Features. Die Funktion stellt
    sicher, dass jede Query hoechstens ``size`` IDs enthaelt.
    """

    if size <= 0:
        raise ValueError("size muss groesser als 0 sein")
    for start in range(0, len(values), size):
        yield values[start : start + size]


@dataclass(frozen=True)
class DetroitDateWindow:
    """Lokale Kalendergrenzen und ihre eindeutigen UTC-Zeitpunkte."""

    start_local: datetime
    end_local: datetime

    @property
    def start_utc(self) -> datetime:
        return self.start_local.astimezone(timezone.utc)

    @property
    def end_utc(self) -> datetime:
        return self.end_local.astimezone(timezone.utc)

    def manifest_fields(self) -> dict:
        """Dokumentiert genau die fuer ArcGIS verwendeten Grenzen."""
        return {
            "window_contract_version": 2,
            "window_timezone": SOURCE_TIMEZONE.key,
            "query_timezone": "UTC",
            "window_start_local": self.start_local.isoformat(),
            "window_end_local_exclusive": self.end_local.isoformat(),
            "window_start_utc": self.start_utc.isoformat(),
            "window_end_utc_exclusive": self.end_utc.isoformat(),
            "window_duration_hours": (
                self.end_utc - self.start_utc
            ).total_seconds() / 3600,
        }

    def where(self, field_name: str) -> str:
        """Formatiert UTC-Literale fuer den UTC-deklarierten ArcGIS-Layer."""
        if field_name not in {"incident_occurred_at", "updated_at"}:
            raise ValueError(f"Nicht erlaubtes Datumsfeld: {field_name}")
        start = self.start_utc.strftime("%Y-%m-%d %H:%M:%S")
        end = self.end_utc.strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"{field_name} >= TIMESTAMP '{start}' "
            f"AND {field_name} < TIMESTAMP '{end}'"
        )


def build_local_date_window(start_date: date, end_date: date) -> DetroitDateWindow:
    """Interpretiert reine Datumswerte als Detroit-Mitternacht, Ende exklusiv.

    Beide Grenzen werden lokal konstruiert. Insbesondere wird nicht pauschal
    eine Anzahl von 24-Stunden-Perioden auf einen UTC-Start addiert.
    """
    if type(start_date) is not date or type(end_date) is not date:
        raise TypeError("Fenstergrenzen muessen date-Werte ohne Uhrzeit sein")
    if end_date <= start_date:
        raise ValueError("end_date muss nach start_date liegen")
    return DetroitDateWindow(
        datetime.combine(start_date, datetime_time.min, SOURCE_TIMEZONE),
        datetime.combine(end_date, datetime_time.min, SOURCE_TIMEZONE),
    )


def resolve_daily_window(
    reference_date: date | None = None,
    lookback_days: int = 14,
    *,
    now: datetime | None = None,
) -> DetroitDateWindow:
    """Waehlt lokale Kalendertage bis einschliesslich reference_date.

    Ohne Referenzdatum endet das Fenster mit dem abgeschlossenen Detroit-
    Vortag. Ein injizierter aware now-Zeitpunkt macht Tests reproduzierbar.
    Ein explizites Referenzdatum ist unabhaengig von der Ausfuehrungszeit.
    """
    if type(lookback_days) is not int or lookback_days <= 0:
        raise ValueError("lookback_days muss eine positive ganze Zahl sein")
    if reference_date is None:
        instant = now if now is not None else datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("now muss eine Zeitzone enthalten")
        reference_date = instant.astimezone(SOURCE_TIMEZONE).date() - timedelta(days=1)
    if type(reference_date) is not date:
        raise TypeError("reference_date muss ein date-Wert sein")
    end_date = reference_date + timedelta(days=1)
    return build_local_date_window(end_date - timedelta(days=lookback_days), end_date)


def build_field_date_where(
    field_name: str,
    start_date: date,
    end_date: date,
) -> str:
    """Erzeugt einen sicheren halb-offenen ArcGIS-Zeitfilter ``[start, end)``.

    Halb-offene Intervalle verhindern Doppelzaehlungen, wenn mehrere Jahre
    oder Daily-Fenster nacheinander extrahiert werden. Die Allowlist verhindert,
    dass ein frei eingegebener Feldname in die ArcGIS-WHERE-Klausel gelangt.
    """

    return build_local_date_window(start_date, end_date).where(field_name)


def build_date_where(start_date: date, end_date: date) -> str:
    """Erzeugt einen Tatzeitfilter fuer Full Loads und historische Analysen."""

    return build_field_date_where("incident_occurred_at", start_date, end_date)


def build_updated_where(start_date: date, end_date: date) -> str:
    """Erzeugt einen Update-Zeitfilter fuer inkrementelle Daily Loads.

    ``updated_at`` erfasst neben neuen Records auch nachtraegliche Aenderungen
    an bereits bekannten Faellen. Das 14-Tage-Overlap wird in Silver anhand des
    stabilen ``offense_key`` aufgeloest.
    """

    return build_field_date_where("updated_at", start_date, end_date)


def build_year_where(year: int) -> str:
    """Komfortfunktion fuer einen vollstaendigen Kalenderjahresfilter."""

    if not 2016 <= year <= 2100:
        raise ValueError("Detroit RMS ist erst ab Dezember 2016 verfuegbar")
    return build_date_where(date(year, 1, 1), date(year + 1, 1, 1))


def sha256_key(*parts: object) -> str:
    """Erzeugt aus fachlichen Schluesselteilen einen deterministischen Hash."""

    normalized = "|".join("" if value is None else str(value) for value in parts)
    return sha256(normalized.encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str | None:
    """Normalisiert Text, ohne fehlende Werte als leere Strings zu erfinden."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def safe_float(value: Any) -> float | None:
    """Konvertiert Koordinaten robust; unlesbare Werte werden zu ``None``."""

    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def epoch_ms_to_iso(value: Any, target_timezone: ZoneInfo | timezone) -> str | None:
    """Konvertiert einen ArcGIS-Epoch-Millisekundenwert in ISO-8601.

    ArcGIS liefert Datumsfelder als Millisekunden seit Unix Epoch. Der rohe
    Millisekundenwert bleibt in Silver zusaetzlich erhalten, damit die
    Transformation vollstaendig nachvollziehbar bleibt.
    """

    if value in (None, ""):
        return None
    try:
        timestamp = float(value) / 1000.0
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(
            target_timezone
        ).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


class ArcGISClient:
    """Kleiner ArcGIS-REST-Client mit Retry, Backoff und ID-basierter Pagination.

    Die Extraktion fragt zuerst alle passenden Object-IDs ab. Danach werden
    genau diese IDs in Batches geladen. Gegenueber ``resultOffset`` reduziert
    das das Risiko, dass gleichzeitig eingefuegte Datensaetze Seiten
    verschieben und dadurch Zeilen fehlen oder doppelt erscheinen.
    """

    def __init__(
        self,
        layer_url: str = DETROIT_LAYER_URL,
        *,
        timeout_seconds: int = 60,
        max_retries: int = 5,
        user_agent: str = "CrimeDataEngineeringStudentProject/1.0",
        aufzeichner: Callable[[str, bytes], None] | None = None,
    ) -> None:
        self.layer_url = layer_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.user_agent = user_agent
        self.aufzeichner = aufzeichner
        self.logger = logging.getLogger(self.__class__.__name__)

    def _request_json(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        post: bool = False,
        name: str = "antwort",
    ) -> dict[str, Any]:
        """Fuehrt einen JSON-Request mit exponentiellem Backoff aus.

        Query-Aufrufe werden als POST gesendet, damit lange Object-ID-Listen
        nicht an URL-Laengenlimits von Proxies oder Servern scheitern.

        Ist ein ``aufzeichner`` gesetzt, bekommt er die **gelieferten Bytes**
        vor dem Parsen zu sehen - das ist der Unterschied zwischen einer
        Raw-Schicht und einer Kopie unserer Deutung. ``name`` gibt der Antwort
        einen sprechenden Dateinamen.
        """

        encoded = urlencode(params or {}).encode("utf-8")
        request_url = url if post else f"{url}?{encoded.decode('utf-8')}"
        request = Request(
            request_url,
            data=encoded if post else None,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.user_agent,
            },
            method="POST" if post else "GET",
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read()
                payload = json.loads(body)
                if self.aufzeichner is not None:
                    self.aufzeichner(name, body)
                if "error" in payload:
                    raise ArcGISRequestError(
                        f"ArcGIS-Fehler: {json.dumps(payload['error'], ensure_ascii=False)}"
                    )
                return payload
            except HTTPError as exc:
                last_error = exc
                if exc.code not in RETRYABLE_HTTP_CODES or attempt == self.max_retries:
                    raise ArcGISRequestError(
                        f"HTTP {exc.code} fuer {url}"
                    ) from exc
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == self.max_retries:
                    raise ArcGISRequestError(f"Request fehlgeschlagen: {url}") from exc
                delay = 2**attempt

            # Kleiner Jitter verhindert, dass parallele Worker gleichzeitig
            # erneut auf den Dienst zugreifen.
            delay += random.uniform(0.0, 0.25)
            self.logger.warning(
                "Request fehlgeschlagen; Versuch %s/%s in %.2f Sekunden",
                attempt + 1,
                self.max_retries + 1,
                delay,
            )
            time.sleep(delay)

        raise ArcGISRequestError("Unerwarteter Request-Fehler") from last_error

    def get_layer_info(self) -> ArcGISLayerInfo:
        """Liest Metadaten und berechnet einen reproduzierbaren Schema-Hash.

        Der Schema-Hash dient dem Schema-Drift-Monitoring. Aendert Detroit
        Felder, Typen oder Aliasnamen, veraendert sich der Fingerprint.
        """

        metadata = self._request_json(
            self.layer_url, {"f": "json"}, name="layer_metadaten")
        fields = metadata.get("fields") or []
        if not fields:
            raise ArcGISRequestError("Layer-Metadaten enthalten keine Felder")

        object_id_field = metadata.get("objectIdField") or metadata.get(
            "objectIdFieldName"
        )
        if not object_id_field:
            raise ArcGISRequestError("Object-ID-Feld konnte nicht ermittelt werden")

        schema_projection = [
            {
                "name": field.get("name"),
                "type": field.get("type"),
                "alias": field.get("alias"),
            }
            for field in fields
        ]
        fingerprint = sha256(
            json.dumps(
                schema_projection, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

        return ArcGISLayerInfo(
            object_id_field=str(object_id_field),
            max_record_count=int(metadata.get("maxRecordCount") or 2000),
            schema_fingerprint=fingerprint,
            fields=tuple(str(field["name"]) for field in fields),
            field_types=tuple((str(f["name"]), str(f.get("type", ""))) for f in fields),
        )

    def get_count(self, where: str, *, name: str = "count") -> int:
        """Ermittelt die serverseitige Zeilenzahl fuer ein Qualitaets-Gate."""

        payload = self._request_json(
            f"{self.layer_url}/query",
            {"where": where, "returnCountOnly": "true", "f": "json"},
            post=True,
            name=name,
        )
        return int(payload["count"])

    def get_object_ids(self, where: str) -> tuple[str, list[int]]:
        """Fixiert die Mitgliedschaft des zu extrahierenden Snapshots.

        Die Antwort enthaelt nur IDs und ist deshalb auch fuer ein komplettes
        Jahr klein genug. Die sortierte Liste macht den Download deterministisch.
        """

        payload = self._request_json(
            f"{self.layer_url}/query",
            {"where": where, "returnIdsOnly": "true", "f": "json"},
            post=True,
            name="object_ids",
        )
        object_id_field = payload.get("objectIdFieldName")
        object_ids = sorted(int(value) for value in payload.get("objectIds", []))
        if not object_id_field:
            raise ArcGISRequestError("ID-Antwort enthaelt kein Object-ID-Feld")
        if len(object_ids) != len(set(object_ids)):
            raise DataQualityError("ArcGIS lieferte doppelte Object-IDs")
        return str(object_id_field), object_ids

    def iter_features(
        self,
        object_ids: Sequence[int],
        *,
        object_id_field: str,
        out_fields: Iterable[str] | str = "*",
        batch_size: int = 2000,
        pause_seconds: float = 0.05,
    ) -> Iterator[dict[str, Any]]:
        """Laedt Features batchweise und liefert sie als Iterator.

        Der Iterator erlaubt dem aufrufenden Skript, Zeilen direkt in eine
        NDJSON-Datei zu streamen, ohne den kompletten Jahresbestand im RAM zu
        halten.
        """

        field_expression = (
            out_fields if isinstance(out_fields, str) else ",".join(out_fields)
        )
        for batch_number, id_batch in enumerate(chunked(object_ids, batch_size), 1):
            payload = self._request_json(
                f"{self.layer_url}/query",
                {
                    "objectIds": ",".join(str(value) for value in id_batch),
                    "outFields": field_expression,
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "orderByFields": f"{object_id_field} ASC",
                    "f": "json",
                },
                post=True,
                name=f"features-{batch_number:04d}",
            )
            features = payload.get("features") or []
            if len(features) != len(id_batch):
                raise DataQualityError(
                    f"Batch {batch_number}: {len(id_batch)} IDs, aber "
                    f"{len(features)} Features empfangen"
                )
            yield from features
            if pause_seconds > 0:
                time.sleep(pause_seconds)


def parse_detroit_feature(
    feature: Mapping[str, Any],
    *,
    pipeline_run_id: str,
    ingested_at: str,
) -> dict[str, Any]:
    """Transformiert ein rohes Detroit-Feature in eine Silver-nahe Zeile.

    Die Funktion:

    1. trennt physische Offense-Zeile und fachliches Polizeiereignis,
    2. normalisiert Zeit und Koordinaten,
    3. mappt nur freigegebene Deliktkategorien,
    4. erzeugt deterministische Schluessel und
    5. dokumentiert Qualitaetsprobleme statt Zeilen zu verwerfen.
    """

    attributes = dict(feature.get("attributes") or {})
    geometry = dict(feature.get("geometry") or {})

    esri_oid = attributes.get("ESRI_OID")
    source_record_id = normalize_text(attributes.get("incident_entry_id"))
    if source_record_id is None and esri_oid is not None:
        source_record_id = str(esri_oid)

    source_event_id = normalize_text(attributes.get("report_number"))
    if source_event_id is None:
        source_event_id = normalize_text(attributes.get("case_id"))

    source_category = normalize_text(attributes.get("offense_category"))
    canonical_category = OFFENSE_MAPPING.get((source_category or "").upper())
    mapping_status = "MAPPED" if canonical_category else "UNREVIEWED"

    latitude = safe_float(attributes.get("latitude"))
    longitude = safe_float(attributes.get("longitude"))
    if latitude is None:
        latitude = safe_float(geometry.get("y"))
    if longitude is None:
        longitude = safe_float(geometry.get("x"))

    quality_flags: list[str] = []
    if source_record_id is None:
        quality_flags.append("MISSING_SOURCE_RECORD_ID")
    if source_event_id is None:
        quality_flags.append("MISSING_SOURCE_EVENT_ID")
    if attributes.get("incident_occurred_at") is None:
        quality_flags.append("MISSING_OCCURRED_AT")
    if attributes.get("updated_at") is None:
        # Der Record bleibt aus einem Full Load analysierbar, kann aber von
        # einem spaeteren Incremental Filter auf updated_at nicht erfasst
        # werden. Das Flag macht diese operative Luecke explizit.
        quality_flags.append("MISSING_SOURCE_UPDATED_AT")
    if latitude == 0.0 and longitude == 0.0:
        latitude = longitude = None
        quality_flags.append("PLACEHOLDER_COORDINATES")
    if latitude is not None and not -90 <= latitude <= 90:
        latitude = None
        quality_flags.append("INVALID_LATITUDE")
    if longitude is not None and not -180 <= longitude <= 180:
        longitude = None
        quality_flags.append("INVALID_LONGITUDE")
    if canonical_category is None:
        quality_flags.append("UNREVIEWED_OFFENSE_CATEGORY")

    case_status = normalize_text(attributes.get("case_status"))
    is_unfounded = (case_status or "").upper() == "UNFOUNDED"
    analysis_eligible = bool(
        canonical_category
        and source_record_id
        and source_event_id
        and not is_unfounded
    )

    offense_key = (
        sha256_key(SOURCE_SYSTEM, source_record_id) if source_record_id else None
    )
    event_key = (
        sha256_key(SOURCE_SYSTEM, source_event_id) if source_event_id else None
    )
    analysis_unit_key = (
        sha256_key(SOURCE_SYSTEM, source_event_id, canonical_category)
        if analysis_eligible
        else None
    )

    occurred_raw = attributes.get("incident_occurred_at")
    return {
        "source_system": SOURCE_SYSTEM,
        "source_dataset_id": SOURCE_DATASET_ID,
        "source_record_id": source_record_id,
        "source_event_id": source_event_id,
        "record_granularity": "INCIDENT_OFFENSE",
        "offense_key": offense_key,
        "event_key": event_key,
        "analysis_unit_key": analysis_unit_key,
        "incident_entry_id": normalize_text(attributes.get("incident_entry_id")),
        "report_number": normalize_text(attributes.get("report_number")),
        "case_id": normalize_text(attributes.get("case_id")),
        "crime_id": normalize_text(attributes.get("crime_id")),
        "source_offense_category": source_category,
        "source_offense_description": normalize_text(
            attributes.get("offense_description")
        ),
        "state_offense_code": normalize_text(attributes.get("state_offense_code")),
        "arrest_charge": normalize_text(attributes.get("arrest_charge")),
        "charge_description": normalize_text(attributes.get("charge_description")),
        "canonical_category": canonical_category,
        "mapping_status": mapping_status,
        "analysis_eligible": analysis_eligible,
        "case_status": case_status,
        "incident_occurred_at_epoch_ms": occurred_raw,
        "occurred_at_utc": epoch_ms_to_iso(occurred_raw, timezone.utc),
        "occurred_at_local": epoch_ms_to_iso(occurred_raw, SOURCE_TIMEZONE),
        "source_timezone": "America/Detroit",
        "incident_time_source": normalize_text(attributes.get("incident_time")),
        "incident_day_of_week_source": normalize_text(
            attributes.get("incident_day_of_week")
        ),
        "incident_hour_of_day_source": attributes.get("incident_hour_of_day"),
        "incident_year_source": attributes.get("incident_year"),
        "nearest_intersection": normalize_text(attributes.get("nearest_intersection")),
        "police_precinct": normalize_text(attributes.get("police_precinct")),
        "scout_car_area": normalize_text(attributes.get("scout_car_area")),
        "neighborhood": normalize_text(attributes.get("neighborhood")),
        "council_district": normalize_text(attributes.get("council_district")),
        "zip_code": normalize_text(attributes.get("zip_code")),
        "census_block_2020_geoid": normalize_text(
            attributes.get("census_block_2020_geoid")
        ),
        "latitude": latitude,
        "longitude": longitude,
        "case_status_updated_at_utc": epoch_ms_to_iso(
            attributes.get("case_status_updated_at"), timezone.utc
        ),
        "updated_in_ibr_at_utc": epoch_ms_to_iso(
            attributes.get("updated_in_ibr_at"), timezone.utc
        ),
        "source_updated_at_utc": epoch_ms_to_iso(
            attributes.get("updated_at"), timezone.utc
        ),
        "source_esri_oid": esri_oid,
        "quality_flags": ";".join(quality_flags),
        "pipeline_run_id": pipeline_run_id,
        "ingested_at": ingested_at,
    }
