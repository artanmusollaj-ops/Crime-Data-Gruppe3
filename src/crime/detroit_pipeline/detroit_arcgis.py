"""Der ArcGIS-HTTP-Client und die Zeitfenster fuer die Detroit-Ingestion.

Das Modul beantwortet zwei Fragen: **Wie** wird geladen (Retry, Backoff,
ID-basierte Pagination, Vollstaendigkeits-Gates) und **welcher Ausschnitt**
(``build_local_date_window`` und die ``where``-Ausdruecke). Das
Kommandozeilenprogramm dazu ist ``extract_detroit.py``.

Was die Zeilen *bedeuten*, steht bewusst nicht hier. Die fachliche
Transformation beider Staedte liegt in ``silver_pipeline.build_crime_offense``
- eine Stelle, eine Granularität, ein Crosswalk. Dieses Modul laedt, es deutet nicht.

Der Download verwendet nur die Standardbibliothek. Dadurch laeuft die
Bronze-Extraktion auch in einer sehr schlanken Laufzeitumgebung; ``pyarrow``
braucht erst das Schreiben der Parquet-Datei in ``extract_detroit.py``.
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
SOURCE_TIMEZONE = ZoneInfo("America/Detroit")

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

