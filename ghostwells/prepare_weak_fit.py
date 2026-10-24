"""Assemble a provenance-preserving, weak-supervision fit table.

This is an exploratory training input only. It deliberately leaves the
human-reviewed readiness and evaluation gates closed.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ghostwells.build_dataset import file_sha256


HUMAN_POSITIVE = {"confirmed_symbol", "independent_symbol_candidate"}
HUMAN_NEGATIVE = {"rejected_lookalike", "independent_lookalike"}
AI_POSITIVE = {"ai_screen_symbol_candidate"}
AI_NEGATIVE = {"ai_screen_lookalike"}
WEIGHTS = {
    "human_candidate_review": 1.0,
    "ai_visual_screen_weak_label": 0.05,
    "human_spatial_sample_negative": 0.25,
}
FIELDS = [
    "sample_id",
    "candidate_id",
    "source_id",
    "sheet",
    "county",
    "edition_year",
    "training_label",
    "label_provenance",
    "label_weight",
    "source_review_status",
    "evaluation_use",
    "crop_path",
    "crop_sha256",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def prepare_weak_fit(dataset_dir: Path) -> dict[str, Any]:
    manifest_path = dataset_dir / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_path = dataset_dir / "weak_supervision_training_examples.csv"
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing weak-fit table: {output_path}")
    output_hashes = manifest.get("output_hashes", {})
    inputs = {
        "reviewed_examples.csv": "reviewed_examples_csv_sha256",
        "provisional_training_candidates.csv": "provisional_training_candidates_csv_sha256",
        "negative_review_examples.csv": "negative_review_examples_csv_sha256",
    }
    for filename, hash_key in inputs.items():
        expected = output_hashes.get(hash_key)
        path = dataset_dir / filename
        if not isinstance(expected, str) or file_sha256(path) != expected:
            raise ValueError(f"Dataset input hash mismatch: {filename}")

    reviewed_rows = read_csv(dataset_dir / "reviewed_examples.csv")
    provisional_rows = read_csv(dataset_dir / "provisional_training_candidates.csv")
    negative_rows = read_csv(dataset_dir / "negative_review_examples.csv")
    provisional_by_id = {row["candidate_id"]: row for row in provisional_rows}
    if len(provisional_by_id) != len(provisional_rows):
        raise ValueError("Duplicate candidate IDs in provisional AI fit table")
    ai_candidate_ids = {
        row["candidate_id"]
        for row in reviewed_rows
        if row["review_status"] in AI_POSITIVE | AI_NEGATIVE
    }
    if ai_candidate_ids != set(provisional_by_id):
        raise ValueError("The complete provisional AI set does not match the candidate audit")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in reviewed_rows:
        status = item["review_status"]
        if status in HUMAN_POSITIVE | HUMAN_NEGATIVE:
            label = "candidate_well_symbol" if status in HUMAN_POSITIVE else "candidate_lookalike"
            provenance = "human_candidate_review"
            weight = WEIGHTS[provenance]
        elif status in AI_POSITIVE | AI_NEGATIVE:
            weak = provisional_by_id.get(item["candidate_id"])
            expected_label = (
                "candidate_well_symbol" if status in AI_POSITIVE else "candidate_lookalike"
            )
            if weak is None or weak["weak_label"] != expected_label:
                raise ValueError(f"AI weak-label provenance mismatch: {item['candidate_id']}")
            if weak["crop_sha256"] != item["crop_sha256"]:
                raise ValueError(f"AI crop hash mismatch: {item['candidate_id']}")
            label = expected_label
            provenance = "ai_visual_screen_weak_label"
            weight = WEIGHTS[provenance]
        else:
            # Uncertain, page-furniture, and pending labels stay in the audit
            # tables but are not silently converted into classifier targets.
            continue
        sample_id = item["sample_id"]
        if sample_id in seen:
            raise ValueError(f"Duplicate candidate sample in weak-fit set: {sample_id}")
        seen.add(sample_id)
        rows.append(
            {
                "sample_id": sample_id,
                "candidate_id": item["candidate_id"],
                "source_id": item["source_id"],
                "sheet": item["sheet"],
                "county": item["county"],
                "edition_year": item["edition_year"],
                "training_label": label,
                "label_provenance": provenance,
                "label_weight": f"{weight:.4f}",
                "source_review_status": status,
                "evaluation_use": "prohibited",
                "crop_path": item["crop_path"],
                "crop_sha256": item["crop_sha256"],
            }
        )

    for item in negative_rows:
        if item["review_status"] != "reviewed_no_well_symbol_visible":
            continue
        sample_id = item["sample_id"]
        if sample_id in seen:
            raise ValueError(f"Duplicate sample in weak-fit set: {sample_id}")
        seen.add(sample_id)
        rows.append(
            {
                "sample_id": sample_id,
                "candidate_id": "",
                "source_id": item["source_id"],
                "sheet": item["sheet"],
                "county": item["county"],
                "edition_year": item["edition_year"],
                "training_label": "candidate_lookalike",
                "label_provenance": "human_spatial_sample_negative",
                "label_weight": f"{WEIGHTS['human_spatial_sample_negative']:.4f}",
                "source_review_status": item["review_status"],
                "evaluation_use": "prohibited",
                "crop_path": item["crop_path"],
                "crop_sha256": item["crop_sha256"],
            }
        )

    class_counts = Counter(row["training_label"] for row in rows)
    if set(class_counts) != {"candidate_well_symbol", "candidate_lookalike"}:
        raise ValueError("Weak-fit assembly needs both symbol and non-symbol examples")
    for row in rows:
        crop_path = Path(row["crop_path"])
        if crop_path.is_absolute() or ".." in crop_path.parts:
            raise ValueError(f"Unsafe crop path: {row['crop_path']}")
        crop_file = (dataset_dir / crop_path).resolve()
        if not crop_file.is_relative_to(dataset_dir.resolve()) or not crop_file.is_file():
            raise ValueError(f"Missing or unsafe crop: {row['crop_path']}")
        if file_sha256(crop_file) != row["crop_sha256"]:
            raise ValueError(f"Crop hash mismatch: {row['sample_id']}")

    write_csv(output_path, rows)
    provenance_counts = Counter(row["label_provenance"] for row in rows)
    weighted_class_mass: dict[str, float] = Counter()
    for row in rows:
        weighted_class_mass[row["training_label"]] += float(row["label_weight"])
    weak_fit = {
        "status": "weak_label_exploratory_fit_ready",
        "training_ready": False,
        "weak_supervision_fit_ready": True,
        "evaluation_ready": False,
        "deployment_ready": False,
        "table": output_path.name,
        "table_sha256": file_sha256(output_path),
        "example_count": len(rows),
        "class_counts": dict(sorted(class_counts.items())),
        "provenance_counts": dict(sorted(provenance_counts.items())),
        "weighted_class_mass": {
            key: round(value, 4) for key, value in sorted(weighted_class_mass.items())
        },
        "sample_weights": WEIGHTS,
        "excluded_uncertain_and_out_of_frame_count": (
            len(reviewed_rows) + len(negative_rows) - len(rows)
        ),
        "limitations": [
            "AI weak labels are correlated with the existing candidate detector and may teach imitation rather than independent recognition.",
            "Human-labeled examples are a small single-reviewer set; spatial negatives are sparse and sampled away from candidate detections.",
            "This fit uses all six pilot sheets and creates no independent evaluation set or generalization estimate.",
            "Do not use this classifier for deployment or make accuracy claims from its in-sample history.",
        ],
    }
    manifest["weak_supervision"] = weak_fit
    # Keep the stronger, human-reviewed and evaluation gates explicitly shut.
    manifest["status"] = "weak_label_exploratory_fit_ready"
    manifest["training_ready"] = False
    manifest["evaluation_ready"] = False
    manifest.setdefault("output_hashes", {})[
        "weak_supervision_training_examples_csv_sha256"
    ] = weak_fit["table_sha256"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return weak_fit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_weak_fit(args.dataset_dir), indent=2))


if __name__ == "__main__":
    main()
