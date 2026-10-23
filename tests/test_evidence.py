"""Manifest validation tests."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ghostwells.__main__ import read_sheets
from ghostwells.evidence import verify_files


class EvidenceTests(unittest.TestCase):
    def test_pilot_manifest_matches_pending_inventory(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "evidence/pilot_sheets.json").read_text(encoding="utf-8"))
        inventory = read_sheets(root / "evidence/survey_inventory.csv")
        sources = {row["sheet_id"]: row for row in inventory}
        self.assertEqual(len(sources), len(manifest["sheets"]))
        for sheet in manifest["sheets"]:
            row = sources[sheet["source_id"]]
            self.assertEqual(row["source_url"], sheet["source_url"])
            self.assertEqual(row["review_status"], "pending")
            self.assertFalse(sheet["full_count_complete"])

    def test_matching_scan_and_changed_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scan = root / "sample.pdf"
            scan.write_bytes(b"original")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sheets": [
                            {
                                "local_file": "sample.pdf",
                                "sha256": hashlib.sha256(b"original").hexdigest(),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(verify_files(manifest, root), [])
            scan.write_bytes(b"changed")
            self.assertIn("SHA-256 mismatch", verify_files(manifest, root)[0])

    def test_manifest_cannot_escape_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sheets": [{"local_file": "../secret.pdf", "sha256": "0"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                verify_files(manifest, root)
