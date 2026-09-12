"""Unit Tests fuer die Zeitfenster-Filter und die Batch-Bildung.

Was die geladenen Zeilen fachlich bedeuten, pruefen die Tests zu
``silver_pipeline.build_crime_offense``. Dieses Modul laedt nur.
"""

from datetime import date
import unittest

from detroit_pipeline.detroit_arcgis import (
    build_date_where,
    build_field_date_where,
    build_updated_where,
    chunked,
)


class DetroitFilterTests(unittest.TestCase):
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
