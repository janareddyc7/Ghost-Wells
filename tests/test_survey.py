"""Tests for review state and aggregate evidence safeguards."""

import tempfile
import unittest
from pathlib import Path

from ghostwells.__main__ import read_sheets, summarize


class SurveyTests(unittest.TestCase):
    def make_csv(self, row: str) -> Path:
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "sheets.csv"
        path.write_text(
            "sheet_id,quadrangle,county,edition_year,source_url,review_status,"
            "well_symbols,lookalikes,reviewer,notes\n" + row,
            encoding="utf-8",
        )
        return path

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()

    def test_pending_rows_do_not_create_symbol_evidence(self) -> None:
        path = self.make_csv("S1,Example,Washington,1960,,pending,,,,queued\n")
        report = summarize(read_sheets(path))
        self.assertEqual(report["reviewed_well_symbols"], 0)
        self.assertEqual(report["statuses"]["pending"], 1)

    def test_reviewed_rows_need_provenance(self) -> None:
        path = self.make_csv("S1,Example,Washington,1960,,reviewed,2,1,Ada,checked\n")
        with self.assertRaisesRegex(ValueError, "source_url"):
            read_sheets(path)

    def test_reviewed_counts_are_aggregated(self) -> None:
        path = self.make_csv(
            "S1,Example,Washington,1960,https://example.org,reviewed,2,1,Ada,checked\n"
        )
        report = summarize(read_sheets(path))
        self.assertEqual(report["reviewed_well_symbols"], 2)
        self.assertEqual(report["by_county"]["Washington"]["lookalikes"], 1)

    def test_duplicate_edition_is_rejected(self) -> None:
        row = "S1,Example,Washington,1960,,pending,,,,queued\n"
        path = self.make_csv(row + row)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            read_sheets(path)


if __name__ == "__main__":
    unittest.main()
