"""Offline-Regressionspruefungen fuer lokale Kalenderfenster und Provenance."""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo

from detroit_pipeline.detroit_arcgis import (
    build_local_date_window, resolve_daily_window,
    DataQualityError,
)
from detroit_pipeline.extract_detroit import extract_updated_window, extract_year, _extract_where
from tests.detroit_pipeline.test_bronze_ingestion import FakeArcGISClient


class RecordingClient(FakeArcGISClient):
    """Erfasst die tatsaechlich an den Client uebergebenen Filter."""
    def __init__(self):
        super().__init__()
        self.filters = []

    def get_count(self, where, *, name="count"):
        self.filters.append(where)
        return super().get_count(where)

    def get_object_ids(self, where):
        self.filters.append(where)
        return super().get_object_ids(where)


class DetroitTimezoneTests(unittest.TestCase):
    def test_calendar_boundaries_and_dst(self):
        cases = [
            (date(2026, 1, 15), "2026-01-15T05:00:00+00:00", "2026-01-16T05:00:00+00:00", 24),
            (date(2026, 7, 15), "2026-07-15T04:00:00+00:00", "2026-07-16T04:00:00+00:00", 24),
            (date(2026, 3, 8), "2026-03-08T05:00:00+00:00", "2026-03-09T04:00:00+00:00", 23),
            (date(2026, 11, 1), "2026-11-01T04:00:00+00:00", "2026-11-02T05:00:00+00:00", 25),
        ]
        for day, start, end, hours in cases:
            with self.subTest(day=day):
                w = build_local_date_window(day, day + timedelta(days=1))
                self.assertEqual(w.start_utc.isoformat(), start)
                self.assertEqual(w.end_utc.isoformat(), end)
                self.assertEqual(w.manifest_fields()["window_duration_hours"], hours)
                # Einschluss der unteren und Ausschluss der oberen Grenze.
                self.assertTrue(w.start_utc <= w.end_utc - timedelta(microseconds=1) < w.end_utc)
                next_w = build_local_date_window(day + timedelta(days=1), day + timedelta(days=2))
                self.assertEqual(w.end_utc, next_w.start_utc)

    def test_daily_defaults_use_detroit_not_host_date(self):
        # UTC ist bereits 1. Januar, Detroit noch 31. Dezember.
        w = resolve_daily_window(lookback_days=1, now=datetime(2026, 1, 1, 2, tzinfo=timezone.utc))
        self.assertEqual(w.start_local.date(), date(2025, 12, 30))
        self.assertEqual(w.end_local.date(), date(2025, 12, 31))

    def test_zurich_09_and_10_produce_same_previous_day(self):
        for month, day in [(1, 15), (3, 8), (3, 29), (7, 15), (10, 25), (11, 1)]:
            with self.subTest(month=month, day=day):
                windows = [resolve_daily_window(now=datetime(2026, month, day, hour, tzinfo=ZoneInfo("Europe/Zurich"))) for hour in (9, 10)]
                self.assertEqual(windows[0], windows[1])
                self.assertEqual(windows[0].end_local.date(), date(2026, month, day))

    def test_zurich_07_uses_completed_detroit_previous_day(self):
        # Auch in den Wochen mit unterschiedlichen US-/EU-DST-Umschaltdaten
        # liegt 07:00 Uhr Zuerich sicher nach Detroit-Mitternacht.
        for month, day in [(1, 15), (3, 8), (3, 29), (7, 15), (10, 25), (11, 1)]:
            with self.subTest(month=month, day=day):
                window = resolve_daily_window(
                    lookback_days=14,
                    now=datetime(
                        2026,
                        month,
                        day,
                        7,
                        tzinfo=ZoneInfo("Europe/Zurich"),
                    ),
                )
                self.assertEqual(
                    window.end_local.date(), date(2026, month, day)
                )
                self.assertEqual(
                    window.end_local.date() - timedelta(days=1),
                    date(2026, month, day) - timedelta(days=1),
                )

    def test_explicit_reference_ignores_run_time(self):
        a = resolve_daily_window(date(2026, 3, 8), 14, now=datetime(2026, 4, 1, tzinfo=timezone.utc))
        b = resolve_daily_window(date(2026, 3, 8), 14, now=datetime(2026, 5, 1, tzinfo=timezone.utc))
        self.assertEqual(a, b)
        self.assertEqual(a.start_local.date(), date(2026, 2, 23))
        self.assertEqual(a.end_local.date(), date(2026, 3, 9))
        self.assertEqual(a.manifest_fields()["window_duration_hours"], 335)

    def test_invalid_inputs(self):
        for value in (0, -1, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_daily_window(lookback_days=value)
        with self.assertRaises(ValueError):
            resolve_daily_window(now=datetime(2026, 1, 1))
        with self.assertRaises(TypeError):
            build_local_date_window(datetime(2026, 1, 1), date(2026, 1, 2))
        with self.assertRaises(ValueError):
            build_local_date_window(date(2026, 1, 1), date(2026, 1, 1))

    def test_manifest_matches_actual_queries(self):
        cases = [
            (True, "incident_occurred_at >= TIMESTAMP '2024-01-01 05:00:00' AND incident_occurred_at < TIMESTAMP '2025-01-01 05:00:00'", "2024-01-01T05:00:00+00:00", "2025-01-01T05:00:00+00:00"),
            (False, "updated_at >= TIMESTAMP '2026-03-08 05:00:00' AND updated_at < TIMESTAMP '2026-03-09 04:00:00'", "2026-03-08T05:00:00+00:00", "2026-03-09T04:00:00+00:00"),
        ]
        for full, expected, start, end in cases:
            with self.subTest(full=full), TemporaryDirectory() as directory:
                client = RecordingClient()
                if full:
                    _, manifest = extract_year(2024, Path(directory), client=client)
                else:
                    _, manifest = extract_updated_window(date(2026, 3, 8), date(2026, 3, 9), Path(directory), client=client)
                data = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(client.filters, [expected, expected, expected])
                self.assertEqual(data["where"], expected)
                self.assertEqual(data["window_start_utc"], start)
                self.assertEqual(data["window_end_utc_exclusive"], end)
                self.assertEqual(data["window_timezone"], "America/Detroit")
                self.assertEqual(data["window_contract_version"], 2)
                self.assertTrue(data["started_at"].endswith("+00:00"))

    def test_inconsistent_query_rejected_before_download(self):
        with TemporaryDirectory() as directory, self.assertRaises(DataQualityError):
            _extract_where("updated_at >= TIMESTAMP '2026-03-08 00:00:00'", Path(directory), file_stem="invalid", extraction_mode="INCREMENTAL", date_field="updated_at", window_start=date(2026, 3, 8), window_end_exclusive=date(2026, 3, 9), client=RecordingClient())


if __name__ == "__main__":
    unittest.main()
