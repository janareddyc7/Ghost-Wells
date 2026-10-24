"""Tests for fit-only training gates and held-out detector evaluation."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ghostwells.build_dataset import file_sha256
from ghostwells.evaluate_detector import evaluate_detector, maximum_matches
from ghostwells.train_patch_classifier import read_fit_rows
from ghostwells.validation import load_split_plan


class TrainingEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def test_county_split_rejects_leakage_and_requires_blind_frozen_plan(self) -> None:
        sources_path = self.root / "sources.json"
        self.write_json(
            sources_path,
            {
                "schema_version": 1,
                "sheets": [
                    {"source_id": "a1", "county": "A"},
                    {"source_id": "a2", "county": "A"},
                    {"source_id": "b1", "county": "B"},
                ],
            },
        )
        plan_path = self.root / "split.json"
        valid_plan = {
            "schema_version": 1,
            "split_level": "county",
            "training_source_ids": ["a1", "a2"],
            "evaluation_source_ids": ["b1"],
            "frozen_before_metrics": True,
            "review_inventory_blind_to_model_candidates": True,
        }
        self.write_json(plan_path, valid_plan)
        plan = load_split_plan(plan_path, sources_path)
        self.assertEqual(plan["evaluation_counties"], ["B"])

        leaking = dict(valid_plan, training_source_ids=["a1"], evaluation_source_ids=["a2", "b1"])
        self.write_json(plan_path, leaking)
        with self.assertRaisesRegex(ValueError, "County leakage"):
            load_split_plan(plan_path, sources_path)

        unblinded = dict(valid_plan, review_inventory_blind_to_model_candidates=False)
        self.write_json(plan_path, unblinded)
        with self.assertRaisesRegex(ValueError, "blind to detector candidates"):
            load_split_plan(plan_path, sources_path)

    def test_fit_rows_require_ready_manifest_and_intact_reviewed_crops(self) -> None:
        dataset_dir = self.root / "dataset"
        crop_dir = dataset_dir / "crops"
        crop_dir.mkdir(parents=True)
        rows = []
        for index, (source_id, label) in enumerate(
            [("a", "candidate_well_symbol"), ("a", "candidate_lookalike")]
        ):
            crop_path = crop_dir / f"{index}.png"
            Image.new("RGB", (8, 8), color=(index * 80, 0, 0)).save(crop_path)
            rows.append(
                {
                    "sample_id": str(index),
                    "source_id": source_id,
                    "training_label": label,
                    "label_provenance": "independent_blind_human_review",
                    "training_eligible": "True",
                    "evaluation_use": "prohibited",
                    "crop_path": f"crops/{index}.png",
                    "crop_sha256": file_sha256(crop_path),
                }
            )
        csv_path = dataset_dir / "independent_training_examples.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        manifest_path = dataset_dir / "dataset_manifest.json"
        self.write_json(
            manifest_path,
            {
                "dataset_id": "test-fit-only",
                "status": "exploratory_fit_ready",
                "training_ready": True,
                "evaluation_ready": False,
                "output_hashes": {
                    "independent_training_examples_csv_sha256": file_sha256(csv_path)
                },
            },
        )
        manifest, loaded_rows = read_fit_rows(dataset_dir)
        self.assertEqual(manifest["dataset_id"], "test-fit-only")
        self.assertEqual(len(loaded_rows), 2)

        manifest["training_ready"] = False
        self.write_json(manifest_path, manifest)
        with self.assertRaisesRegex(ValueError, "not marked exploratory_fit_ready"):
            read_fit_rows(dataset_dir)

    def test_eval_scores_complete_held_out_sheet_with_one_to_one_matches(self) -> None:
        sources_path = self.root / "sources.json"
        sources = {
            "schema_version": 1,
            "sheets": [
                {"source_id": "train", "county": "A", "scale": 24000, "sha256": "a" * 64},
                {"source_id": "eval", "county": "B", "scale": 24000, "sha256": "b" * 64},
            ],
        }
        self.write_json(sources_path, sources)
        split_path = self.root / "split.json"
        self.write_json(
            split_path,
            {
                "schema_version": 1,
                "split_level": "county",
                "training_source_ids": ["train"],
                "evaluation_source_ids": ["eval"],
                "frozen_before_metrics": True,
                "review_inventory_blind_to_model_candidates": True,
            },
        )
        tile_path = self.root / "tile_manifest.json"
        self.write_json(
            tile_path,
            {
                "schema_version": 1,
                "chips": [
                    {
                        "image_file": "train.jpg",
                        "source_id": "train",
                        "page_pixel_origin": [0, 0],
                        "image_size": [100, 100],
                        "render_scale": 1.0,
                    },
                    {
                        "image_file": "eval.jpg",
                        "source_id": "eval",
                        "page_pixel_origin": [0, 0],
                        "image_size": [100, 100],
                        "render_scale": 1.0,
                    },
                ],
            },
        )
        annotations_path = self.root / "annotations.json"
        self.write_json(
            annotations_path,
            {
                "schema_version": 1,
                "coordinate_space": "rendered_page_pixels",
                "reviewer": "test-reviewer",
                "review_inventory_blind_to_model_candidates": True,
                "sheets": [
                    {"source_id": "eval", "source_sha256": "b" * 64},
                ],
                "reviewed_chips": ["train.jpg", "eval.jpg"],
                "unreviewed_chips": [],
                "marks": [
                    {
                        "chip": "eval.jpg",
                        "sourceId": "eval",
                        "pageX": 10,
                        "pageY": 10,
                        "renderScale": 1.0,
                        "label": "well_symbol",
                    }
                ],
            },
        )
        candidates_path = self.root / "candidates.json"
        self.write_json(
            candidates_path,
            {
                "schema_version": 1,
                "model_sha256": "c" * 64,
                "render_scale_pixels_per_pdf_point": 1.0,
                "sheets": [
                    {"source_id": "train", "candidates": []},
                    {
                        "source_id": "eval",
                        "candidates": [
                            {"page_x": 11, "page_y": 10},
                            {"page_x": 80, "page_y": 80},
                        ],
                    },
                ],
            },
        )
        report_path = self.root / "report.json"
        report = evaluate_detector(
            annotations_path=annotations_path,
            tile_manifest_path=tile_path,
            candidates_path=candidates_path,
            source_manifest_path=sources_path,
            split_plan_path=split_path,
            output_path=report_path,
            radii_meters=[50],
        )
        metric = report["metrics"][0]
        self.assertEqual(metric["counts"]["true_positives"], 1)
        self.assertEqual(metric["counts"]["false_positives"], 1)
        self.assertEqual(metric["counts"]["false_negatives"], 0)
        self.assertEqual(metric["precision"], 0.5)
        self.assertEqual(metric["recall"], 1.0)

        annotations = json.loads(annotations_path.read_text(encoding="utf-8"))
        annotations["reviewed_chips"] = ["train.jpg"]
        annotations["unreviewed_chips"] = ["eval.jpg"]
        self.write_json(annotations_path, annotations)
        with self.assertRaisesRegex(ValueError, "lacks complete reviewed-tile coverage"):
            evaluate_detector(
                annotations_path=annotations_path,
                tile_manifest_path=tile_path,
                candidates_path=candidates_path,
                source_manifest_path=sources_path,
                split_plan_path=split_path,
                output_path=self.root / "incomplete_report.json",
                radii_meters=[50],
            )

    def test_one_detection_cannot_count_as_two_matches(self) -> None:
        self.assertEqual(maximum_matches([(0, 0), (0, 0)], [(0, 0)], 1), 1)


if __name__ == "__main__":
    unittest.main()
