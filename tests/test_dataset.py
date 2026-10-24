"""Integration tests for reproducible private crop-pilot construction."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from ghostwells.apply_independent_review import apply_independent_review
from ghostwells.apply_review_codes import apply_review_codes
from ghostwells.build_dataset import build_dataset
from ghostwells.export_review_batches import export_review_batches
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

    def test_review_batch_export_contains_only_pending_candidates(self) -> None:
        output = self.root / "review-batches"
        result = export_review_batches(
            manifest_path=self.manifest_path,
            candidates_path=self.candidates_path,
            decisions_path=self.decisions_path,
            data_dir=self.root,
            output_dir=output,
        )
        self.assertEqual(result["pending_candidate_count"], 5)
        self.assertEqual(result["batch_count"], 5)
        with (output / "review_queue.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["candidate_id"] != "5a8a257be4b00f54eb3c0935:0001" for row in rows))
        self.assertEqual(len(list((output / "crops").glob("*.png"))), 5)

    def test_provisional_ai_screen_is_traceable_and_never_training_eligible(self) -> None:
        review_dir = self.root / "review-batches"
        export_review_batches(
            manifest_path=self.manifest_path,
            candidates_path=self.candidates_path,
            decisions_path=self.decisions_path,
            data_dir=self.root,
            output_dir=review_dir,
        )
        queue_path = review_dir / "review_queue.csv"
        with queue_path.open(newline="", encoding="utf-8") as stream:
            queue_rows = list(csv.DictReader(stream))
        codes_by_sheet = {
            sheet: ["S" * sum(row["sheet"] == sheet for row in queue_rows)]
            for sheet in sorted({row["sheet"] for row in queue_rows})
        }
        codebook_path = self.root / "ai_review_codes.json"
        self.write_json(
            codebook_path,
            {
                "schema_version": 1,
                "reviewer_id": "codex_ai_visual_screen",
                "reviewed_on": "2026-10-24",
                "review_method": "single_pass_4x4_source_crop_contact_sheet",
                "status": "provisional_ai_visual_screen",
                "codes_by_sheet": codes_by_sheet,
                "limitations": ["Synthetic integration-test labels."],
            },
        )
        decisions_path = self.root / "ai_decisions.json"
        result = apply_review_codes(
            manifest_path=self.manifest_path,
            candidates_path=self.candidates_path,
            source_decisions_path=self.decisions_path,
            queue_path=queue_path,
            batch_manifest_path=review_dir / "batch_manifest.json",
            codebook_path=codebook_path,
            output_path=decisions_path,
        )
        self.assertEqual(result["reviewed_pending_candidate_count"], 5)
        self.assertEqual(result["preserved_original_decision_count"], 1)
        self.assertFalse(result["independently_adjudicated"])

        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))["decisions"]
        original_id = next(iter(json.loads(self.decisions_path.read_text(encoding="utf-8"))["decisions"]))
        self.assertEqual(decisions[original_id]["status"], "confirmed_symbol")
        ai_decisions = [item for key, item in decisions.items() if key != original_id]
        self.assertTrue(all(item["status"] == "ai_screen_symbol_candidate" for item in ai_decisions))
        self.assertTrue(all(item["independent_review_required"] for item in ai_decisions))

        dataset_path = self.root / "ai-review-dataset"
        dataset = build_dataset(
            manifest_path=self.manifest_path,
            candidates_path=self.candidates_path,
            decisions_path=decisions_path,
            data_dir=self.root,
            output_dir=dataset_path,
        )
        self.assertFalse(dataset["training_ready"])
        self.assertEqual(dataset["training_eligible_example_count"], 0)
        self.assertEqual(dataset["reviewed_crop_count"], 6)
        self.assertEqual(dataset["provisional_training_candidate_count"], 5)
        with (dataset_path / "provisional_training_candidates.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            training_rows = list(csv.DictReader(stream))
        self.assertEqual(len(training_rows), 5)
        self.assertTrue(all(row["training_use"] == "exploratory_only" for row in training_rows))
        self.assertTrue(all(row["evaluation_use"] == "prohibited" for row in training_rows))

        invalid_codebook = json.loads(codebook_path.read_text(encoding="utf-8"))
        first_sheet = next(iter(invalid_codebook["codes_by_sheet"]))
        invalid_codebook["codes_by_sheet"][first_sheet] = []
        invalid_codebook_path = self.root / "invalid_ai_review_codes.json"
        self.write_json(invalid_codebook_path, invalid_codebook)
        invalid_output = self.root / "invalid-ai-decisions.json"
        with self.assertRaisesRegex(ValueError, "does not match queued candidates"):
            apply_review_codes(
                manifest_path=self.manifest_path,
                candidates_path=self.candidates_path,
                source_decisions_path=self.decisions_path,
                queue_path=queue_path,
                batch_manifest_path=review_dir / "batch_manifest.json",
                codebook_path=invalid_codebook_path,
                output_path=invalid_output,
            )
        self.assertFalse(invalid_output.exists())

        batch_manifest_path = review_dir / "batch_manifest.json"
        contact_sheet_hashes = {
            name: hashlib.sha256((review_dir / name).read_bytes()).hexdigest()
            for name in json.loads(batch_manifest_path.read_text(encoding="utf-8"))["batches"]
        }
        review_export_path = self.root / "independent-review.json"
        review_rows = []
        for index, row in enumerate(queue_rows):
            choice = "symbol_candidate"
            if index == 1:
                choice = "lookalike"
            elif index == 2:
                choice = "uncertain"
            review_rows.append(
                {
                    "candidate_id": row["candidate_id"],
                    "source_id": row["source_id"],
                    "sheet": row["sheet"],
                    "decision": choice,
                    "decided_at_utc": "2026-10-24T12:00:00Z",
                    "crop_sha256": row["crop_sha256"],
                    "contact_sheet": row["batch_file"],
                    "contact_sheet_cell": int(row["batch_cell"]),
                }
            )
        self.write_json(
            review_export_path,
            {
                "schema_version": 1,
                "review_type": "independent_blind_candidate_adjudication",
                "reviewer_id": "independent-test-reviewer",
                "independent_of_ai_screen_attested": True,
                "all_queued_candidates_reviewed": True,
                "reviewed_count": len(review_rows),
                "pending_count": 0,
                "queue_sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
                "batch_manifest_sha256": hashlib.sha256(batch_manifest_path.read_bytes()).hexdigest(),
                "contact_sheet_sha256": contact_sheet_hashes,
                "decisions": review_rows,
            },
        )
        independently_reviewed_path = self.root / "independently-reviewed-decisions.json"
        review_result = apply_independent_review(
            ai_decisions_path=decisions_path,
            queue_path=queue_path,
            batch_manifest_path=batch_manifest_path,
            review_path=review_export_path,
            output_path=independently_reviewed_path,
        )
        self.assertEqual(review_result["applied_count"], 5)
        self.assertTrue(review_result["complete"])
        independently_reviewed = json.loads(
            independently_reviewed_path.read_text(encoding="utf-8")
        )
        first_reviewed = independently_reviewed["decisions"][review_rows[0]["candidate_id"]]
        self.assertEqual(first_reviewed["status"], "independent_symbol_candidate")
        self.assertEqual(first_reviewed["ai_visual_screen"]["status"], "ai_screen_symbol_candidate")
        self.assertEqual(first_reviewed["reviewer_id"], "independent-test-reviewer")

        independent_dataset_path = self.root / "independent-review-dataset"
        independent_dataset = build_dataset(
            manifest_path=self.manifest_path,
            candidates_path=self.candidates_path,
            decisions_path=independently_reviewed_path,
            data_dir=self.root,
            output_dir=independent_dataset_path,
        )
        self.assertTrue(independent_dataset["training_ready"])
        self.assertTrue(independent_dataset["exploratory_fit_ready"])
        self.assertFalse(independent_dataset["evaluation_ready"])
        self.assertEqual(independent_dataset["training_eligible_example_count"], 4)
        self.assertEqual(independent_dataset["independent_training_example_count"], 4)

        invalid_review = json.loads(review_export_path.read_text(encoding="utf-8"))
        invalid_review["decisions"][0]["crop_sha256"] = "0" * 64
        invalid_review_path = self.root / "invalid-independent-review.json"
        self.write_json(invalid_review_path, invalid_review)
        rejected_review_output = self.root / "rejected-review-overlay.json"
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            apply_independent_review(
                ai_decisions_path=decisions_path,
                queue_path=queue_path,
                batch_manifest_path=batch_manifest_path,
                review_path=invalid_review_path,
                output_path=rejected_review_output,
            )
        self.assertFalse(rejected_review_output.exists())

        invalid_contact_review = json.loads(review_export_path.read_text(encoding="utf-8"))
        first_batch = next(iter(invalid_contact_review["contact_sheet_sha256"]))
        invalid_contact_review["contact_sheet_sha256"][first_batch] = "0" * 64
        invalid_contact_path = self.root / "invalid-contact-sheet-review.json"
        self.write_json(invalid_contact_path, invalid_contact_review)
        rejected_contact_output = self.root / "rejected-contact-review-overlay.json"
        with self.assertRaisesRegex(ValueError, "contact-sheet hashes differ"):
            apply_independent_review(
                ai_decisions_path=decisions_path,
                queue_path=queue_path,
                batch_manifest_path=batch_manifest_path,
                review_path=invalid_contact_path,
                output_path=rejected_contact_output,
            )
        self.assertFalse(rejected_contact_output.exists())

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
