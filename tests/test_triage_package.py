"""Tests for the private local model-triage package exporter."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ghostwells.build_dataset import file_sha256
from ghostwells.export_triage_package import export_triage_package


class TriagePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset_dir = self.root / "dataset"
        self.crop_dir = self.dataset_dir / "crops"
        self.crop_dir.mkdir(parents=True)
        self.ranker_dir = self.root / "ranker"
        self.ranker_dir.mkdir()
        self.queue_path = self.ranker_dir / "uncertain_crop_priority.csv"
        self.report_path = self.ranker_dir / "ranker_run.json"
        self.crop_path = self.crop_dir / "sample-001.png"
        Image.new("RGB", (8, 8), color="white").save(self.crop_path)
        self.negative_crop_path = self.crop_dir / "negative_sample-002.png"
        Image.new("RGB", (8, 8), color="gray").save(self.negative_crop_path)
        self.write_queue()
        self.write_report()

    def write_queue(self, crop_hash: str | None = None) -> None:
        fields = [
            "priority_rank",
            "sample_id",
            "candidate_id",
            "source_id",
            "sheet",
            "county",
            "source_review_status",
            "uncalibrated_symbol_rank_score",
            "crop_path",
            "crop_sha256",
        ]
        with self.queue_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "priority_rank": "1",
                        "sample_id": "sample-001",
                        "candidate_id": "candidate-001",
                        "source_id": "source-001",
                        "sheet": "Example",
                        "county": "Example County",
                        "source_review_status": "ai_screen_uncertain",
                        "uncalibrated_symbol_rank_score": "0.8123",
                        "crop_path": "crops/sample-001.png",
                        "crop_sha256": crop_hash or file_sha256(self.crop_path),
                    },
                    {
                        "priority_rank": "2",
                        "sample_id": "sample-002",
                        "candidate_id": "",
                        "source_id": "source-002",
                        "sheet": "Example",
                        "county": "Example County",
                        "source_review_status": "uncertain",
                        "uncalibrated_symbol_rank_score": "0.7012",
                        "crop_path": "crops/negative_sample-002.png",
                        "crop_sha256": file_sha256(self.negative_crop_path),
                    },
                ]
            )

    def write_report(self) -> None:
        self.report_path.write_text(
            json.dumps(
                {
                    "training_scope": "frozen_imagenet_embedding_weighted_linear_probe_fit_only",
                    "dataset_id": "test-dataset",
                    "uncertain_priority_count": 2,
                    "uncertain_priority_csv_sha256": file_sha256(self.queue_path),
                    "validation_metrics": None,
                    "evaluation_ready": False,
                    "deployment_ready": False,
                }
            ),
            encoding="utf-8",
        )

    def test_exports_only_ranked_crops_with_closed_gates(self) -> None:
        output_dir = self.root / "package"
        result = export_triage_package(
            dataset_dir=self.dataset_dir,
            ranker_dir=self.ranker_dir,
            output_dir=output_dir,
        )
        self.assertEqual(result["crop_count"], 2)
        self.assertFalse(result["evaluation_ready"])
        self.assertFalse(result["deployment_ready"])
        self.assertTrue((output_dir / "crops/sample-001.png").is_file())
        self.assertTrue((output_dir / "crops/negative_sample-002.png").is_file())
        manifest = json.loads((output_dir / "triage_package.json").read_text())
        self.assertEqual(manifest["status"], "uncalibrated_rank_only")
        self.assertEqual(manifest["crop_count"], 2)

        with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
            export_triage_package(
                dataset_dir=self.dataset_dir,
                ranker_dir=self.ranker_dir,
                output_dir=output_dir,
            )

    def test_rejects_crop_hash_mismatch_before_creating_package(self) -> None:
        self.write_queue("0" * 64)
        self.write_report()
        output_dir = self.root / "package"
        with self.assertRaisesRegex(ValueError, "Crop hash mismatch"):
            export_triage_package(
                dataset_dir=self.dataset_dir,
                ranker_dir=self.ranker_dir,
                output_dir=output_dir,
            )
        self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
