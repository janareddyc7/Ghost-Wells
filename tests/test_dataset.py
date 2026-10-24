"""Integration tests for reproducible private crop-pilot construction."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from ghostwells.build_dataset import build_dataset
from ghostwells.sample_negatives import sample_negatives


class DatasetPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        project_root = Path(__file__).resolve().parents[1]
        frame_path = project_root / "evidence" / "map_frame_bounds.json"
        self.frames = json.loads(frame_path.read_text(encoding="utf-8"))["sheets"]
        manifest_sheets = []
        candidate_sheets = []

        for source_id, frame in self.frames.items():
            filename = f"{source_id}.pdf"
            pdf_path = self.root / filename
            document = pymupdf.open()
            document.new_page(width=600, height=800)
            document.save(pdf_path)
            document.close()

            source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            manifest_sheets.append(
                {
                    "source_id": source_id,
                    "name": frame["name"],
                    "county": "Test County",
                    "year": 1960,
                    "local_file": filename,
                    "sha256": source_hash,
                }
            )
            candidate_sheets.append(
                {
                    "source_id": source_id,
                    "sheet": frame["name"],
                    "source_sha256": source_hash,
                    "page_size_pixels": [600, 800],
                    "candidates": [{"page_x": 300, "page_y": 400, "mask_area_pixels": 50}],
                }
            )

        self.manifest_path = self.root / "manifest.json"
        self.candidates_path = self.root / "candidates.json"
        self.decisions_path = self.root / "decisions.json"
        self.write_json(self.manifest_path, {"schema_version": 1, "sheets": manifest_sheets})
        self.write_json(
            self.candidates_path,
            {
                "schema_version": 1,
                "model_sha256": "a" * 64,
                "render_scale_pixels_per_pdf_point": 1.0,
                "sheets": candidate_sheets,
            },
        )
        first_source = next(iter(self.frames))
        self.write_json(
            self.decisions_path,
            {
                "schema_version": 1,
                "decisions": {
                    f"{first_source}:0001": {
                        "status": "confirmed_symbol",
                        "note": "Synthetic integration-test annotation.",
                    }
                },
            },
        )

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def build_sample_set(self, name: str) -> tuple[Path, dict]:
        output = self.root / name
        result = sample_negatives(
            manifest_path=self.manifest_path,
            candidates_path=self.candidates_path,
            data_dir=self.root,
            output_dir=output,
            grid_rows=1,
            grid_columns=1,
            exclusion_radius=182,
        )
        return output, result

    def build_dataset_at(self, output: Path, negative_dir: Path) -> dict:
        return build_dataset(
            manifest_path=self.manifest_path,
            candidates_path=self.candidates_path,
            decisions_path=self.decisions_path,
            data_dir=self.root,
            output_dir=output,
            negative_queue_path=negative_dir / "negative_review_queue.csv",
            negative_decisions_path=self.root / "negative_decisions.json",
        )

    def test_pipeline_is_reproducible_and_rejects_tampered_negative_crop(self) -> None:
        negative_a, sample_a = self.build_sample_set("negative-a")
        negative_b, sample_b = self.build_sample_set("negative-b")
        self.assertEqual(sample_a["sample_set_id"], sample_b["sample_set_id"])
        self.assertEqual(
            sample_a["input_hashes"]["negative_review_queue_sha256"],
            sample_b["input_hashes"]["negative_review_queue_sha256"],
        )

        for negative_dir, sample in ((negative_a, sample_a), (negative_b, sample_b)):
            self.write_json(
                self.root / "negative_decisions.json",
                {
                    "schema_version": 1,
                    "sample_set_id": sample["sample_set_id"],
                    "all_queued_samples_reviewed": True,
                    "default_status": "no_well_symbol_visible",
                    "default_note": "Synthetic review note.",
                    "uncertain": {},
                },
            )

        data_a = self.build_dataset_at(self.root / "dataset-a", negative_a)
        data_b = self.build_dataset_at(self.root / "dataset-b", negative_b)
        self.assertEqual(data_a["dataset_id"], data_b["dataset_id"])
        self.assertEqual(data_a["output_hashes"], data_b["output_hashes"])
        self.assertFalse(data_a["training_ready"])
        self.assertEqual(data_a["candidate_count"], 6)
        self.assertEqual(data_a["reviewed_crop_count"], 1)
        self.assertEqual(data_a["negative_sample_crop_count"], 6)
        self.assertEqual(data_a["training_eligible_example_count"], 0)

        with (self.root / "dataset-a" / "reviewed_examples.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            reviewed_rows = list(csv.DictReader(stream))
        self.assertEqual(len(reviewed_rows), 1)
        self.assertEqual(reviewed_rows[0]["training_eligible"], "False")
        self.assertEqual(
            reviewed_rows[0]["training_eligibility_reason"], "requires_independent_review"
        )

        with (self.root / "dataset-a" / "negative_review_examples.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            negative_rows = list(csv.DictReader(stream))
        self.assertEqual(len(negative_rows), 6)
        self.assertTrue(all(row["training_eligible"] == "False" for row in negative_rows))

        decisions_path = self.root / "negative_decisions.json"
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
        decisions["all_queued_samples_reviewed"] = "true"
        self.write_json(decisions_path, decisions)
        invalid_overlay_output = self.root / "invalid-overlay-dataset"
        with self.assertRaisesRegex(ValueError, "does not attest to complete review"):
            self.build_dataset_at(invalid_overlay_output, negative_a)
        self.assertFalse(invalid_overlay_output.exists())
        decisions["all_queued_samples_reviewed"] = True
        self.write_json(decisions_path, decisions)

        with (negative_a / "negative_review_queue.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            first_sample = next(csv.DictReader(stream))
        tampered_crop = negative_a / first_sample["crop_path"]
        tampered_crop.write_bytes(tampered_crop.read_bytes() + b"tampered")
        tampered_output = self.root / "tampered-dataset"
        with self.assertRaisesRegex(ValueError, "crop hash mismatch"):
            self.build_dataset_at(tampered_output, negative_a)
        self.assertFalse(tampered_output.exists())


if __name__ == "__main__":
    unittest.main()
