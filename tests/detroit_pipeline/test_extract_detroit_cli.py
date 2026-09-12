"""Offline-Tests fuer die cron-faehige Detroit-Kommandozeilenschnittstelle."""

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import call, patch

from detroit_pipeline.extract_detroit import main, parse_args


class DetroitCliTests(unittest.TestCase):
    """Prueft Parametervertraege und die Auswahl des richtigen Extractors."""

    def test_full_accepts_multiple_years(self):
        args = parse_args(["--mode", "full", "--years", "2024", "2025"])
        self.assertEqual(args.mode, "full")
        self.assertEqual(args.years, [2024, 2025])

    def test_daily_defaults_to_fourteen_days(self):
        args = parse_args(["--mode", "daily"])
        self.assertEqual(args.lookback_days, 14)
        self.assertIsNone(args.reference_date)

    def test_daily_reference_date_is_parsed(self):
        args = parse_args(
            ["--mode", "daily", "--reference-date", "2026-09-07"]
        )
        self.assertEqual(args.reference_date, date(2026, 9, 7))

    def test_full_requires_years(self):
        with self.assertRaises(SystemExit):
            parse_args(["--mode", "full"])

    def test_daily_rejects_years(self):
        with self.assertRaises(SystemExit):
            parse_args(["--mode", "daily", "--years", "2025"])

    def test_daily_rejects_invalid_lookback(self):
        with self.assertRaises(SystemExit):
            parse_args(["--mode", "daily", "--lookback-days", "0"])

    def test_invalid_reference_date_is_rejected(self):
        with self.assertRaises(SystemExit):
            parse_args(
                ["--mode", "daily", "--reference-date", "07.09.2026"]
            )

    @patch("detroit_pipeline.extract_detroit.print_extraction_result")
    @patch("detroit_pipeline.extract_detroit.extract_year")
    def test_full_dispatches_each_year_to_partition(self, extract, print_result):
        extract.side_effect = [
            (Path("2024.ndjson"), Path("2024.manifest.json")),
            (Path("2025.ndjson"), Path("2025.manifest.json")),
        ]

        result = main(
            [
                "--mode",
                "full",
                "--years",
                "2024",
                "2025",
                "--output-dir",
                "bronze",
                "--raw-dir",
                "roh",
            ]
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            extract.call_args_list,
            [
                call(
                    year=2024,
                    output_dir=Path("bronze/full/year=2024"),
                    raw_dir=Path("roh/full/year=2024"),
                    batch_size=None,
                    pause_seconds=0.05,
                ),
                call(
                    year=2025,
                    output_dir=Path("bronze/full/year=2025"),
                    raw_dir=Path("roh/full/year=2025"),
                    batch_size=None,
                    pause_seconds=0.05,
                ),
            ],
        )
        self.assertEqual(print_result.call_count, 2)

    @patch("detroit_pipeline.extract_detroit.print_extraction_result")
    @patch("detroit_pipeline.extract_detroit.extract_updated_window")
    def test_daily_dispatches_reproducible_detroit_window(
        self, extract, print_result
    ):
        extract.return_value = (
            Path("daily.ndjson"),
            Path("daily.manifest.json"),
        )

        result = main(
            [
                "--mode",
                "daily",
                "--lookback-days",
                "14",
                "--reference-date",
                "2026-09-07",
                "--output-dir",
                "bronze",
                "--raw-dir",
                "roh",
            ]
        )

        self.assertEqual(result, 0)
        extract.assert_called_once_with(
            start_date=date(2026, 8, 25),
            end_date_exclusive=date(2026, 9, 8),
            output_dir=Path("bronze/incremental/run_date=2026-09-07"),
            raw_dir=Path("roh/incremental/run_date=2026-09-07"),
            batch_size=None,
            pause_seconds=0.05,
        )
        print_result.assert_called_once_with(
            Path("daily.ndjson"), Path("daily.manifest.json")
        )


if __name__ == "__main__":
    unittest.main()
