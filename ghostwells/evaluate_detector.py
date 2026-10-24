"""Evaluate frozen detector candidates against a complete, held-out map inventory.

The annotation export and report contain precise page-pixel locations. Keep them
under ignored ``data/usgs/``; never publish the resulting private report.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ghostwells.build_dataset import file_sha256
from ghostwells.validation import load_split_plan


ALLOWED_LABELS = {
    "well_symbol",
    "benchmark",
    "tank",
    "windmill",
    "spot_elevation",
    "other_lookalike",
    "uncertain",
}


def maximum_matches(
    predictions: list[tuple[float, float]], truths: list[tuple[float, float]], radius: float
) -> int:
    """Return maximum one-to-one point matches within a radius (PDF points)."""
    neighbors: list[list[int]] = []
    for px, py in predictions:
        nearby = [
            (math.hypot(px - tx, py - ty), index)
            for index, (tx, ty) in enumerate(truths)
            if math.hypot(px - tx, py - ty) <= radius
        ]
        neighbors.append([index for _, index in sorted(nearby)])

    truth_to_prediction: dict[int, int] = {}

    def assign(prediction_index: int, visited: set[int]) -> bool:
        for truth_index in neighbors[prediction_index]:
            if truth_index in visited:
                continue
            visited.add(truth_index)
            previous = truth_to_prediction.get(truth_index)
            if previous is None or assign(previous, visited):
                truth_to_prediction[truth_index] = prediction_index
                return True
        return False

    return sum(assign(index, set()) for index in range(len(predictions)))


def evaluate_detector(
    *,
    annotations_path: Path,
    tile_manifest_path: Path,
    candidates_path: Path,
    source_manifest_path: Path,
    split_plan_path: Path,
    output_path: Path,
    radii_meters: list[float] | None = None,
) -> dict[str, Any]:
    """Validate blind full-sheet coverage and score one-to-one point matches."""
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing evaluation report: {output_path}")
    radii_meters = radii_meters or [50.0, 100.0, 200.0]
    if not radii_meters or any(radius <= 0 for radius in radii_meters):
        raise ValueError("Evaluation radii must be positive meters")

    annotation = json.loads(annotations_path.read_text(encoding="utf-8"))
    tile_manifest = json.loads(tile_manifest_path.read_text(encoding="utf-8"))
    candidate_data = json.loads(candidates_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    split_plan = load_split_plan(split_plan_path, source_manifest_path)

    if annotation.get("schema_version") != 1:
        raise ValueError("Unsupported map-annotation export schema")
    if annotation.get("coordinate_space") != "rendered_page_pixels":
        raise ValueError("Map annotations must use rendered-page pixel coordinates")
    if not isinstance(annotation.get("reviewer"), str) or not annotation["reviewer"].strip():
        raise ValueError("Map-annotation reviewer identity is missing")
    if annotation.get("review_inventory_blind_to_model_candidates") is not True:
        raise ValueError("Map inventory was not attested as blind to detector candidates")
    if candidate_data.get("schema_version") != 1 or not isinstance(
        candidate_data.get("sheets"), list
    ):
        raise ValueError("Unsupported detector candidate file")
    if tile_manifest.get("schema_version") != 1 or not isinstance(
        tile_manifest.get("chips"), list
    ):
        raise ValueError("Unsupported tile manifest")

    source_rows = {row["source_id"]: row for row in source_manifest["sheets"]}
    eval_ids = set(split_plan["evaluation_source_ids"])
    annotation_sheets = {row["source_id"]: row for row in annotation.get("sheets", [])}
    for source_id in eval_ids:
        source = source_rows[source_id]
        reviewed_source = annotation_sheets.get(source_id)
        if reviewed_source is None or reviewed_source.get("source_sha256") != source["sha256"]:
            raise ValueError(f"Annotations do not reference the verified source scan: {source_id}")

    chips = tile_manifest["chips"]
    chip_by_file = {row["image_file"]: row for row in chips}
    if len(chip_by_file) != len(chips):
        raise ValueError("Duplicate image filename in tile manifest")
    reviewed_rows = annotation.get("reviewed_chips")
    unreviewed_rows = annotation.get("unreviewed_chips")
    if not isinstance(reviewed_rows, list) or len(set(reviewed_rows)) != len(reviewed_rows):
        raise ValueError("Reviewed tile list is missing or contains duplicates")
    if not isinstance(unreviewed_rows, list) or len(set(unreviewed_rows)) != len(unreviewed_rows):
        raise ValueError("Unreviewed tile list is missing or contains duplicates")
    reviewed = set(reviewed_rows)
    unreviewed = set(unreviewed_rows)
    if reviewed & unreviewed or (reviewed | unreviewed) != set(chip_by_file):
        raise ValueError("Annotation export does not account for every tile exactly once")
    for source_id in eval_ids:
        required_tiles = {
            row["image_file"] for row in chips if row["source_id"] == source_id
        }
        if not required_tiles or not required_tiles.issubset(reviewed):
            raise ValueError(f"Held-out sheet lacks complete reviewed-tile coverage: {source_id}")
        if required_tiles & unreviewed:
            raise ValueError(f"Held-out sheet still has unreviewed tiles: {source_id}")

    truth_by_source: dict[str, list[tuple[float, float]]] = {source_id: [] for source_id in eval_ids}
    uncertain_count = Counter()
    for mark in annotation.get("marks", []):
        label = mark.get("label")
        if label not in ALLOWED_LABELS:
            raise ValueError(f"Unsupported annotation label: {label}")
        chip = chip_by_file.get(mark.get("chip"))
        if chip is None or mark["chip"] not in reviewed:
            raise ValueError("Annotation mark is not attached to a reviewed tile")
        source_id = chip["source_id"]
        if mark.get("sourceId") != source_id:
            raise ValueError("Annotation mark source does not match tile manifest")
        scale = float(mark.get("renderScale", 0))
        if not math.isclose(scale, float(chip["render_scale"]), rel_tol=0, abs_tol=1e-6):
            raise ValueError("Annotation render scale differs from its tile manifest")
        x, y = float(mark["pageX"]), float(mark["pageY"])
        origin_x, origin_y = chip["page_pixel_origin"]
        size_x, size_y = chip["image_size"]
        if not (origin_x <= x <= origin_x + size_x and origin_y <= y <= origin_y + size_y):
            raise ValueError("Annotation point lies outside its source tile")
        if source_id not in eval_ids:
            continue
        if label == "uncertain":
            uncertain_count[source_id] += 1
        elif label == "well_symbol":
            truth_by_source[source_id].append((x / scale, y / scale))

    if sum(uncertain_count.values()):
        raise ValueError(
            "Resolve uncertain marks on held-out sheets before reporting detector metrics"
        )
    if not any(truth_by_source.values()):
        raise ValueError("Held-out annotation inventory contains no well-symbol positives")

    candidate_scale = float(candidate_data.get("render_scale_pixels_per_pdf_point", 0))
    if candidate_scale <= 0:
        raise ValueError("Detector candidate file has no valid render scale")
    candidate_sheets = {row["source_id"]: row for row in candidate_data["sheets"]}
    if not eval_ids.issubset(candidate_sheets):
        raise ValueError("Detector outputs do not include every held-out source sheet")
    predictions_by_source = {
        source_id: [
            (float(item["page_x"]) / candidate_scale, float(item["page_y"]) / candidate_scale)
            for item in candidate_sheets[source_id]["candidates"]
        ]
        for source_id in eval_ids
    }
    if not all(source_rows[source_id].get("scale") for source_id in eval_ids):
        raise ValueError("Source manifest is missing map scale for a held-out sheet")

    results = []
    per_sheet = []
    for radius_m in sorted(set(float(value) for value in radii_meters)):
        sheet_counts: dict[str, dict[str, int]] = {}
        total = Counter()
        for source_id in sorted(eval_ids):
            scale_denominator = float(source_rows[source_id]["scale"])
            meters_per_pdf_point = scale_denominator * 0.0254 / 72.0
            radius_pdf_points = radius_m / meters_per_pdf_point
            predictions = predictions_by_source[source_id]
            truths = truth_by_source[source_id]
            true_positives = maximum_matches(predictions, truths, radius_pdf_points)
            counts = {
                "true_positives": true_positives,
                "false_positives": len(predictions) - true_positives,
                "false_negatives": len(truths) - true_positives,
                "prediction_count": len(predictions),
                "annotated_symbol_count": len(truths),
            }
            sheet_counts[source_id] = counts
            total.update(counts)

        tp, fp, fn = total["true_positives"], total["false_positives"], total["false_negatives"]
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
        results.append(
            {
                "match_radius_meters_at_printed_scale": radius_m,
                "counts": {key: total[key] for key in (
                    "true_positives", "false_positives", "false_negatives",
                    "prediction_count", "annotated_symbol_count"
                )},
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "per_sheet": sheet_counts,
            }
        )

    report = {
        "schema_version": 1,
        "evaluation_type": "frozen_pretrained_detector_against_complete_held_out_sheet_inventory",
        "split_plan": split_plan,
        "input_hashes": {
            "annotations_sha256": file_sha256(annotations_path),
            "tile_manifest_sha256": file_sha256(tile_manifest_path),
            "candidates_sha256": file_sha256(candidates_path),
            "source_manifest_sha256": file_sha256(source_manifest_path),
            "split_plan_sha256": file_sha256(split_plan_path),
        },
        "held_out_source_ids": sorted(eval_ids),
        "reviewer": annotation["reviewer"],
        "metrics": results,
        "limitations": [
            "Candidate outputs contain no confidence scores; average precision is unavailable.",
            "Distance radii use printed map scale and page coordinates, not validated georeferencing.",
            "Metrics apply only to these complete, annotated held-out sheets.",
            "A map symbol is not proof of a physical well or current field condition.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--tile-manifest", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, default=Path("evidence/pilot_sheets.json"))
    parser.add_argument("--split-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--radii-meters", type=float, nargs="+", default=[50, 100, 200])
    args = parser.parse_args()
    result = evaluate_detector(
        annotations_path=args.annotations,
        tile_manifest_path=args.tile_manifest,
        candidates_path=args.candidates,
        source_manifest_path=args.source_manifest,
        split_plan_path=args.split_plan,
        output_path=args.output,
        radii_meters=args.radii_meters,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
