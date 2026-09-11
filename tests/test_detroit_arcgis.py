"""Unit Tests fuer Parser, Filter und Hilfsfunktionen."""

from datetime import date
import unittest

from detroit_pipeline.detroit_arcgis import (
    build_date_where,
    build_field_date_where,
    build_updated_where,
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

    def test_missing_updated_at_is_flagged(self) -> None:
        """Markiert Records, die ein Daily Load spaeter nicht erfassen kann."""

        self.feature["attributes"]["updated_at"] = None
        row = parse_detroit_feature(
            self.feature, pipeline_run_id="run", ingested_at="now"
        )
        self.assertIn("MISSING_SOURCE_UPDATED_AT", row["quality_flags"])
        # Fehlendes updated_at verhindert die fachliche Analyse des aus einem
        # Full Load stammenden Records nicht automatisch.
        self.assertTrue(row["analysis_eligible"])

    def test_present_updated_at_is_not_flagged(self) -> None:
        """Sichert den Gegenfall: ein echtes updated_at setzt kein Flag."""

        # Die Fixture fuehrt updated_at gar nicht, weshalb der Test darueber
        # denselben Codepfad nimmt wie ein ausdrueckliches None. Erst dieser
        # Fall trennt die beiden Zweige und faengt eine Regression, die das
        # Flag unabhaengig vom Feldwert setzt.
        self.feature["attributes"]["updated_at"] = 1704239400000
        row = parse_detroit_feature(
            self.feature, pipeline_run_id="run", ingested_at="now"
        )
        self.assertNotIn("MISSING_SOURCE_UPDATED_AT", row["quality_flags"])
        # Der Wert muss ausserdem in der Auswertespalte ankommen, sonst waere
        # das fehlende Flag nur ein Zufall.
        self.assertEqual(
            row["source_updated_at_utc"], "2024-01-02T23:50:00+00:00"
        )

    def test_multiple_offenses_share_event_and_category_analysis_key(self) -> None:
        """Prueft die 1:n-Beziehung Event zu Offense und Category-Deduplikation."""

        second_feature = {
            "attributes": {
                **self.feature["attributes"],
                "incident_entry_id": "OFFENSE-2",
                "offense_category": "AGGRAVATED ASSAULT",
            },
            "geometry": self.feature["geometry"],
        }
        # Beide Kategorien werden in der vergleichbaren Silver-Semantik auf
        # ASSAULT abgebildet.
        self.feature["attributes"]["offense_category"] = "ASSAULT"
        first = parse_detroit_feature(
            self.feature, pipeline_run_id="run", ingested_at="now"
        )
        second = parse_detroit_feature(
            second_feature, pipeline_run_id="run", ingested_at="now"
        )

        self.assertNotEqual(first["offense_key"], second["offense_key"])
        self.assertEqual(first["event_key"], second["event_key"])
        self.assertEqual(first["canonical_category"], "ASSAULT")
        self.assertEqual(second["canonical_category"], "ASSAULT")
        self.assertEqual(first["analysis_unit_key"], second["analysis_unit_key"])

    def test_date_filter_is_half_open(self) -> None:
        """Prueft, dass benachbarte Zeitpartitionen nicht ueberlappen."""

        where = build_date_where(date(2024, 1, 1), date(2025, 1, 1))
        self.assertIn(">= TIMESTAMP '2024-01-01 05:00:00'", where)
        self.assertIn("< TIMESTAMP '2025-01-01 05:00:00'", where)

    def test_updated_filter_is_half_open(self) -> None:
        """Prueft das Update-Wasserzeichen fuer den Daily Load."""

        where = build_updated_where(date(2026, 8, 23), date(2026, 9, 6))
        self.assertIn("updated_at >= TIMESTAMP '2026-08-23 04:00:00'", where)
        self.assertIn("updated_at < TIMESTAMP '2026-09-06 04:00:00'", where)

    def test_date_field_allowlist(self) -> None:
        """Verhindert frei eingeschleuste Feldnamen in der WHERE-Klausel."""

        with self.assertRaises(ValueError):
            build_field_date_where("updated_at OR 1=1", date(2024, 1, 1), date(2024, 1, 2))

    def test_chunking(self) -> None:
        """Prueft die Aufteilung der Object-IDs in API-Batches."""

        self.assertEqual(
            list(chunked([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]]
        )


if __name__ == "__main__":
    unittest.main()
