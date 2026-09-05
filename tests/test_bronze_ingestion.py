"""Integrationstest der Bronze-Ingestion mit einem kontrollierten Fake-Client.

Der Test fuehrt denselben Ablauf wie ein echter Jahresdownload aus, nutzt aber
fuenf lokale Features. Dadurch prueft CI Count-Reconciliation, Kategorie-
statistik, Bronze-Ausgabe und Manifest ohne instabile Live-API-Abhaengigkeit.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from detroit_pipeline.detroit_arcgis import ArcGISLayerInfo
from detroit_pipeline.extract_detroit import (
    extract_year,
    format_load_summary,
)


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
            fields=("ESRI_OID", "offense_category"),
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

            expected_counts = {
                "ASSAULT": 2,
                "LARCENY": 1,
                "ROBBERY": 1,
                "__MISSING__": 1,
            }
            self.assertTrue(bronze_path.exists())
            self.assertEqual(manifest["downloaded_count"], 5)
            self.assertEqual(manifest["offense_category_counts"], expected_counts)
            self.assertEqual(sum(expected_counts.values()), 5)

            # Die explizite Ausgabe macht beim lokalen Testlauf sofort sichtbar,
            # wie viele Datensaetze je Kategorie und insgesamt geladen wurden.
            print()
            print(format_load_summary(expected_counts, 5))


if __name__ == "__main__":
    unittest.main()
