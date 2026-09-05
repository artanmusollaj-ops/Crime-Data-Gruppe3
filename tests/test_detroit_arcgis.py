"""Unit Tests fuer Parser, Filter und Hilfsfunktionen."""

from datetime import date
import unittest

from detroit_pipeline.detroit_arcgis import (
    build_date_where,
    chunked,
    parse_detroit_feature,
)


class DetroitParserTests(unittest.TestCase):
    def setUp(self) -> None:
        """Erzeugt eine kleine, reproduzierbare ArcGIS-Beispielzeile."""

        self.feature = {
            "attributes": {
                "incident_entry_id": "OFFENSE-1",
                "report_number": "REPORT-1",
                "offense_category": "STOLEN VEHICLE",
                "offense_description": "MOTOR VEHICLE THEFT",
                "incident_occurred_at": 1704153000000,
                "incident_time": "18:50",
                "incident_hour_of_day": 18,
                "incident_year": 2024,
                "case_status": "ACTIVE",
                "ESRI_OID": 123,
            },
            "geometry": {"x": -83.05, "y": 42.35},
        }

    def test_parses_and_maps_vehicle_theft(self) -> None:
        """Prueft Mapping, Granularitaet, Zeit und Koordinaten."""

        row = parse_detroit_feature(
            self.feature,
            pipeline_run_id="run-test",
            ingested_at="2026-09-05T00:00:00+00:00",
        )
        self.assertEqual(row["canonical_category"], "VEHICLE_THEFT")
        self.assertEqual(row["record_granularity"], "INCIDENT_OFFENSE")
        self.assertTrue(row["analysis_eligible"])
        self.assertEqual(row["incident_time_source"], "18:50")
        self.assertIn("2024-01-01T18:50:00", row["occurred_at_local"])
        self.assertEqual(row["longitude"], -83.05)

    def test_unfounded_is_retained_but_not_eligible(self) -> None:
        """Prueft, dass UNFOUNDED erhalten, aber nicht analysiert wird."""

        self.feature["attributes"]["case_status"] = "UNFOUNDED"
        row = parse_detroit_feature(
            self.feature, pipeline_run_id="run", ingested_at="now"
        )
        self.assertFalse(row["analysis_eligible"])
        self.assertIsNone(row["analysis_unit_key"])

    def test_unknown_category_is_not_silently_mapped(self) -> None:
        """Prueft das explizite UNREVIEWED-Verhalten bei neuen Kategorien."""

        self.feature["attributes"]["offense_category"] = "NEW CATEGORY"
        row = parse_detroit_feature(
            self.feature, pipeline_run_id="run", ingested_at="now"
        )
        self.assertEqual(row["mapping_status"], "UNREVIEWED")
        self.assertIn("UNREVIEWED_OFFENSE_CATEGORY", row["quality_flags"])

    def test_date_filter_is_half_open(self) -> None:
        """Prueft, dass benachbarte Zeitpartitionen nicht ueberlappen."""

        where = build_date_where(date(2024, 1, 1), date(2025, 1, 1))
        self.assertIn(">= TIMESTAMP '2024-01-01 00:00:00'", where)
        self.assertIn("< TIMESTAMP '2025-01-01 00:00:00'", where)

    def test_chunking(self) -> None:
        """Prueft die Aufteilung der Object-IDs in API-Batches."""

        self.assertEqual(
            list(chunked([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]]
        )


if __name__ == "__main__":
    unittest.main()
