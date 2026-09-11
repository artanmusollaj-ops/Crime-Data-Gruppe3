"""Integrationstest der Bronze-Ingestion mit einem kontrollierten Fake-Client.

Der Test fuehrt denselben Ablauf wie ein echter Jahresdownload aus, nutzt aber
fuenf lokale Features. Dadurch prueft CI Count-Reconciliation, Kategorie-
statistik, Bronze-Ausgabe und Manifest ohne instabile Live-API-Abhaengigkeit.
"""

import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from detroit_pipeline.detroit_arcgis import ArcGISLayerInfo
from detroit_pipeline.extract_detroit import (
    extract_year,
    extract_updated_window,
    format_load_summary,
)


BRONZE_TEST_CATEGORY_COUNTS = {
    "ASSAULT": 2,
    "LARCENY": 1,
    "ROBBERY": 1,
    "__MISSING__": 1,
}
BRONZE_TEST_TOTAL = sum(BRONZE_TEST_CATEGORY_COUNTS.values())


class FakeArcGISClient:
    """Minimale, deterministische Testimplementierung des ArcGIS-Clients."""

    layer_url = "https://example.invalid/FeatureServer/0"

    def __init__(self) -> None:
        categories = ["ASSAULT", "ASSAULT", "ROBBERY", "LARCENY", None]
        self.features = [
            {
                "attributes": {
                    "ESRI_OID": index,
                    "incident_entry_id": f"ENTRY-{index}",
                    "report_number": f"REPORT-{index}",
                    "offense_category": category,
                },
                "geometry": {"x": -83.05, "y": 42.35},
            }
            for index, category in enumerate(categories, 1)
        ]

    def get_layer_info(self) -> ArcGISLayerInfo:
        """Liefert das Schema und API-Limit fuer den Testlauf."""

        return ArcGISLayerInfo(
            object_id_field="ESRI_OID",
            max_record_count=2000,
            schema_fingerprint="test-schema",
            fields=(
                "ESRI_OID",
                "offense_category",
                "incident_occurred_at",
                "updated_at",
            ),
        )

    def get_count(self, where: str) -> int:
        """Simuliert den serverseitigen Count vor und nach dem Download."""

        return len(self.features)

    def get_object_ids(self, where: str) -> tuple[str, list[int]]:
        """Simuliert die fuer den Snapshot fixierte Object-ID-Liste."""

        return "ESRI_OID", [row["attributes"]["ESRI_OID"] for row in self.features]

    def iter_features(self, object_ids, **kwargs):
        """Liefert genau die Features der angefragten Object-IDs."""

        selected = set(object_ids)
        yield from (
            row for row in self.features if row["attributes"]["ESRI_OID"] in selected
        )


class BronzeIngestionTests(unittest.TestCase):
    def test_full_load_manifest_uses_occurrence_time(self) -> None:
        """Verankert incident_occurred_at als fachliche Full-Load-Zeitachse."""

        with TemporaryDirectory() as temporary_directory:
            _, manifest_path = extract_year(
                2024,
                Path(temporary_directory),
                client=FakeArcGISClient(),
                pause_seconds=0,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["extraction_mode"], "FULL")
            self.assertEqual(manifest["date_field"], "incident_occurred_at")
            self.assertEqual(
                manifest["selection_basis"], "INCIDENT_OCCURRENCE_TIME"
            )
            self.assertIn("incident_occurred_at >=", manifest["where"])
            self.assertNotIn("updated_at >=", manifest["where"])
            self.assertFalse(manifest["captures_source_deletions"])

    def test_counts_per_category_and_total(self) -> None:
        """Prueft und zeigt Kategorie- sowie Gesamtzahl der geladenen Records."""

        with TemporaryDirectory() as temporary_directory:
            bronze_path, manifest_path = extract_year(
                2024,
                Path(temporary_directory),
                client=FakeArcGISClient(),
                pause_seconds=0,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(bronze_path.exists())
            self.assertEqual(manifest["downloaded_count"], BRONZE_TEST_TOTAL)
            self.assertEqual(
                manifest["offense_category_counts"],
                BRONZE_TEST_CATEGORY_COUNTS,
            )
            self.assertEqual(
                sum(BRONZE_TEST_CATEGORY_COUNTS.values()),
                BRONZE_TEST_TOTAL,
            )

            # Die explizite Ausgabe macht beim lokalen Testlauf sofort sichtbar,
            # wie viele Datensaetze je Kategorie und insgesamt geladen wurden.
            print()
            print(
                format_load_summary(
                    BRONZE_TEST_CATEGORY_COUNTS,
                    BRONZE_TEST_TOTAL,
                )
            )

    def test_incremental_updated_window_manifest(self) -> None:
        """Prueft Daily-Modus, Update-Fenster, Dateiname und Manifestfelder."""

        with TemporaryDirectory() as temporary_directory:
            bronze_path, manifest_path = extract_updated_window(
                date(2026, 8, 23),
                date(2026, 9, 6),
                Path(temporary_directory),
                client=FakeArcGISClient(),
                pause_seconds=0,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual('part-0001.parquet', bronze_path.name)
            self.assertTrue(bronze_path.parent.name.startswith('run_'))
            self.assertEqual(manifest["extraction_mode"], "INCREMENTAL")
            self.assertEqual(manifest["date_field"], "updated_at")
            self.assertEqual(
                manifest["selection_basis"], "SOURCE_LAST_UPDATED_TIME"
            )
            self.assertEqual(manifest["record_granularity"], "INCIDENT_OFFENSE")
            self.assertTrue(manifest["window_is_half_open"])
            self.assertFalse(manifest["captures_source_deletions"])
            self.assertEqual(manifest["window_start"], "2026-08-23")
            self.assertEqual(manifest["window_end_exclusive"], "2026-09-06")
            self.assertIsNone(manifest["year"])
            self.assertIn("updated_at >=", manifest["where"])
            self.assertEqual(manifest["downloaded_count"], 5)


if __name__ == "__main__":
    unittest.main()
