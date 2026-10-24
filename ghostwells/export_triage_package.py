"""Bundle and verify the private model-ranked crops for local app triage."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

from ghostwells.build_dataset import file_sha256


QUEUE_NAME = "uncertain_crop_priority.csv"
REPORT_NAME = "ranker_run.json"
QUEUE_FIELDS = {
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
}


def export_triage_package(
    *, dataset_dir: Path, ranker_dir: Path, output_dir: Path
) -> dict[str, Any]:
    """Copy only ranked crops into an integrity-checked, local triage package."""
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing package: {output_dir}")

    queue_path = ranker_dir / QUEUE_NAME
    report_path = ranker_dir / REPORT_NAME
    if not queue_path.is_file() or not report_path.is_file():
        raise ValueError("Ranker output is missing its queue CSV or run report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("training_scope") != "frozen_imagenet_embedding_weighted_linear_probe_fit_only":
        raise ValueError("Ranker report does not identify the expected fit-only model")
    if (
        report.get("evaluation_ready") is not False
        or report.get("deployment_ready") is not False
        or report.get("validation_metrics") is not None
    ):
        raise ValueError("Ranker report must keep evaluation and deployment gates closed")
    queue_hash = file_sha256(queue_path)
    if report.get("uncertain_priority_csv_sha256") != queue_hash:
        raise ValueError("Ranker queue hash does not match its run report")

    with queue_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not QUEUE_FIELDS.issubset(reader.fieldnames):
            raise ValueError("Ranker queue is missing required triage columns")
        rows = list(reader)
    if not rows or len(rows) != report.get("uncertain_priority_count"):
        raise ValueError("Ranker queue count does not match its run report")

    dataset_root = dataset_dir.resolve()
    seen_samples: set[str] = set()
    crop_hashes: dict[str, str] = {}
    previous_score = float("inf")
    for index, row in enumerate(rows, start=1):
        sample_id = row.get("sample_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id) or sample_id in seen_samples:
            raise ValueError(f"Missing, unsafe, or duplicate sample ID at rank {index}")
        seen_samples.add(sample_id)
        if row.get("priority_rank") != str(index):
            raise ValueError("Ranker queue must have contiguous, ordered priority ranks")
        if row.get("source_review_status") not in {"ai_screen_uncertain", "uncertain"}:
            raise ValueError(f"Queue row is not an uncertain example: {sample_id}")
        try:
            score = float(row.get("uncalibrated_symbol_rank_score", ""))
        except ValueError as error:
            raise ValueError(f"Invalid uncalibrated score for {sample_id}") from error
        if not 0 <= score <= 1 or score > previous_score:
            raise ValueError(f"Invalid or out-of-order rank score for {sample_id}")
        previous_score = score
        relative_crop = Path(row.get("crop_path", ""))
        allowed_crop_names = {f"{sample_id}.png", f"negative_{sample_id}.png"}
        if (
            len(relative_crop.parts) != 2
            or relative_crop.parts[0] != "crops"
            or relative_crop.name not in allowed_crop_names
        ):
            raise ValueError(f"Unexpected crop path for {sample_id}")
        crop_path = (dataset_root / relative_crop).resolve()
        if not crop_path.is_relative_to(dataset_root) or not crop_path.is_file():
            raise ValueError(f"Missing or unsafe crop for {sample_id}")
        actual_crop_hash = file_sha256(crop_path)
        if actual_crop_hash != row.get("crop_sha256"):
            raise ValueError(f"Crop hash mismatch for {sample_id}")
        crop_hashes[relative_crop.as_posix()] = actual_crop_hash

    output_dir.mkdir(parents=True)
    (output_dir / "crops").mkdir()
    for relative_crop in crop_hashes:
        source = (dataset_root / relative_crop).resolve()
        shutil.copyfile(source, output_dir / relative_crop)
    shutil.copyfile(queue_path, output_dir / QUEUE_NAME)
    shutil.copyfile(report_path, output_dir / REPORT_NAME)

    package_manifest = {
        "schema_version": 1,
        "package_type": "private_local_model_triage_queue",
        "status": "uncalibrated_rank_only",
        "dataset_id": report.get("dataset_id"),
        "ranker_run_sha256": file_sha256(output_dir / REPORT_NAME),
        "queue_sha256": file_sha256(output_dir / QUEUE_NAME),
        "crop_count": len(crop_hashes),
        "crop_sha256": crop_hashes,
        "evaluation_ready": False,
        "deployment_ready": False,
        "limitations": [
            "Rank scores are uncalibrated review priorities, not probabilities.",
            "The model was fit with weak AI labels and has no independent validation result.",
            "A visually similar map mark is not confirmation of a physical well.",
        ],
    }
    (output_dir / "triage_package.json").write_text(
        json.dumps(package_manifest, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "package_path": str(output_dir),
        "dataset_id": package_manifest["dataset_id"],
        "crop_count": len(crop_hashes),
        "queue_sha256": package_manifest["queue_sha256"],
        "ranker_run_sha256": package_manifest["ranker_run_sha256"],
        "evaluation_ready": False,
        "deployment_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--ranker-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            export_triage_package(
                dataset_dir=args.dataset_dir,
                ranker_dir=args.ranker_dir,
                output_dir=args.output_dir,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
