"""Export a provenance-checked private crop dataset from reviewed candidates.

This builds an audit/pilot export only. It intentionally does not assign model
splits or claim training readiness; candidate-only sampling and single-reviewer
labels are not a validated Ohio dataset.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

import pymupdf
import PIL
from PIL import Image

from ghostwells.candidate_review import zone


TRAIN_LABELS = {
    "confirmed_symbol": "well_symbol",
    "rejected_lookalike": "non_well_map_lookalike",
    "rejected_collar_or_page_furniture": "excluded_page_furniture",
    "uncertain": "uncertain",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render_crop(page: Any, x: int, y: int, scale: float, size: int) -> Image.Image:
    half = size // 2
    page_rect = page.rect
    wanted = pymupdf.Rect(
        (x - half) / scale,
        (y - half) / scale,
        (x + half) / scale,
        (y + half) / scale,
    )
    clipped = wanted & page_rect
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clipped, alpha=False)
    crop = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    padded = Image.new("RGB", (size, size), "white")
    paste_x = max(0, min(size - crop.width, pixmap.x - (x - half)))
    paste_y = max(0, min(size - crop.height, pixmap.y - (y - half)))
    padded.paste(crop, (paste_x, paste_y))
    return padded


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_dataset(
    *,
    manifest_path: Path,
    candidates_path: Path,
    decisions_path: Path,
    data_dir: Path,
    output_dir: Path,
    crop_size: int = 256,
    negative_queue_path: Path | None = None,
    negative_decisions_path: Path | None = None,
) -> dict[str, Any]:
    if crop_size < 64 or crop_size % 2:
        raise ValueError("crop_size must be an even integer of at least 64 pixels")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_data = json.loads(candidates_path.read_text(encoding="utf-8"))
    decision_data = json.loads(decisions_path.read_text(encoding="utf-8"))
    frame_path = Path(__file__).resolve().parents[1] / "evidence" / "map_frame_bounds.json"
    frame_data = json.loads(frame_path.read_text(encoding="utf-8"))
    if (negative_queue_path is None) != (negative_decisions_path is None):
        raise ValueError("Provide both negative review queue and decision overlay, or neither")
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sheets"), list):
        raise ValueError("Unsupported source manifest schema")
    if candidate_data.get("schema_version") != 1 or not isinstance(
        candidate_data.get("sheets"), list
    ):
        raise ValueError("Unsupported candidate schema")
    if decision_data.get("schema_version") != 1 or not isinstance(
        decision_data.get("decisions"), dict
    ):
        raise ValueError("Unsupported decision schema")
    if frame_data.get("schema_version") != 1 or not isinstance(frame_data.get("sheets"), dict):
        raise ValueError("Unsupported map-frame schema")

    source_by_id = {sheet["source_id"]: sheet for sheet in manifest["sheets"]}
    candidate_by_id = {sheet["source_id"]: sheet for sheet in candidate_data["sheets"]}
    if len(source_by_id) != len(manifest["sheets"]):
        raise ValueError("Duplicate source_id in source manifest")
    if set(candidate_by_id) != set(source_by_id):
        raise ValueError("Candidate source sheets do not match the evidence manifest")
    if set(frame_data["sheets"]) != set(source_by_id):
        raise ValueError("Map-frame source sheets do not match the evidence manifest")

    decisions: dict[str, dict[str, str]] = decision_data["decisions"]
    allowed_statuses = set(TRAIN_LABELS)
    known_candidate_ids = {
        f"{sheet['source_id']}:{index:04d}"
        for sheet in candidate_data["sheets"]
        for index, _ in enumerate(sheet["candidates"], start=1)
    }
    if set(decisions) - known_candidate_ids:
        raise ValueError(
            f"Review decisions refer to missing candidates: {sorted(set(decisions) - known_candidate_ids)}"
        )
    for candidate_id, decision in decisions.items():
        if decision.get("status") not in allowed_statuses:
            raise ValueError(f"Unsupported review status for {candidate_id}")
    model_hash = candidate_data.get("model_sha256")
    if not isinstance(model_hash, str) or len(model_hash) != 64:
        raise ValueError("Candidate file has no valid model SHA-256")

    input_hashes = {
        "source_manifest_sha256": file_sha256(manifest_path),
        "candidate_json_sha256": file_sha256(candidates_path),
        "decision_json_sha256": file_sha256(decisions_path),
        "map_frame_bounds_sha256": file_sha256(frame_path),
        "builder_sha256": file_sha256(Path(__file__).resolve()),
    }
    negative_manifest: dict[str, Any] | None = None
    negative_decisions: dict[str, dict[str, str]] = {}
    negative_rows: list[dict[str, str]] = []
    negative_default_note = ""
    if negative_queue_path is not None and negative_decisions_path is not None:
        negative_manifest_path = negative_queue_path.parent / "sample_manifest.json"
        negative_manifest = json.loads(negative_manifest_path.read_text(encoding="utf-8"))
        negative_decision_data = json.loads(negative_decisions_path.read_text(encoding="utf-8"))
        with negative_queue_path.open(newline="", encoding="utf-8") as stream:
            negative_rows = list(csv.DictReader(stream))
        if negative_manifest.get("schema_version") != 1 or negative_decision_data.get(
            "schema_version"
        ) != 1:
            raise ValueError("Unsupported model-negative sample schema")
        if negative_manifest.get("model_sha256") != model_hash:
            raise ValueError("Model-negative sample uses a different model")
        sample_set_id = negative_manifest.get("sample_set_id")
        if negative_decision_data.get("sample_set_id") != sample_set_id:
            raise ValueError("Negative review decisions belong to a different sample set")
        if negative_decision_data.get("all_queued_samples_reviewed") is not True:
            raise ValueError("Negative decision overlay does not attest to complete review")
        if negative_decision_data.get("default_status") != "no_well_symbol_visible":
            raise ValueError("Unsupported default negative-review status")
        if negative_manifest.get("selected_sample_count") != len(negative_rows):
            raise ValueError("Negative sample queue count does not match its manifest")
        if negative_manifest.get("status") != "pending_visual_review_not_negative_labels":
            raise ValueError("Negative sample manifest has an unexpected review state")
        if int(negative_manifest["sampling_config"]["crop_size_pixels"]) != crop_size:
            raise ValueError("Candidate and model-negative crop sizes differ")
        if negative_manifest["input_hashes"].get("negative_review_queue_sha256") != file_sha256(
            negative_queue_path
        ):
            raise ValueError("Negative sample queue hash mismatch")
        if negative_manifest["input_hashes"].get("source_manifest_sha256") != file_sha256(
            manifest_path
        ) or negative_manifest["input_hashes"].get("candidate_json_sha256") != file_sha256(
            candidates_path
        ):
            raise ValueError("Negative sample provenance does not match current input data")
        if negative_manifest["input_hashes"].get("map_frame_bounds_sha256") != file_sha256(
            frame_path
        ):
            raise ValueError("Negative sample uses different map-frame bounds")
        input_hashes["negative_review_queue_sha256"] = file_sha256(negative_queue_path)
        input_hashes["negative_review_decisions_sha256"] = file_sha256(negative_decisions_path)
        input_hashes["negative_sample_manifest_sha256"] = file_sha256(negative_manifest_path)
        negative_decisions = negative_decision_data.get("uncertain", {})
        negative_default_note = negative_decision_data.get("default_note", "")
        if (
            not isinstance(negative_decisions, dict)
            or not isinstance(negative_default_note, str)
            or not negative_default_note.strip()
        ):
            raise ValueError("Negative decision notes are missing or malformed")
        if any(
            not isinstance(note, str) or not note.strip() for note in negative_decisions.values()
        ):
            raise ValueError("Every uncertain negative sample requires a note")
        queue_ids = [row["sample_id"] for row in negative_rows]
        if len(queue_ids) != len(set(queue_ids)):
            raise ValueError("Duplicate sample_id in model-negative queue")
        if set(negative_decisions) - set(queue_ids):
            raise ValueError("Uncertain negative decisions refer to unknown sample IDs")
        exclusion_radius = int(
            negative_manifest["sampling_config"]["candidate_exclusion_radius_pixels"]
        )
        for row in negative_rows:
            source_id = row["source_id"]
            if source_id not in source_by_id:
                raise ValueError(f"Unknown source in negative sample: {source_id}")
            candidate_sheet = candidate_by_id[source_id]
            width, height = candidate_sheet["page_size_pixels"]
            x, y = int(row["page_x"]), int(row["page_y"])
            if zone(
                x / width,
                y / height,
                frame_data["sheets"][source_id]["bounds"],
                float(frame_data["boundary_buffer_fraction"]),
            ) != "map_interior_manual_review":
                raise ValueError(f"Model-negative sample falls outside buffered frame: {row['sample_id']}")
            nearest = min(
                (
                    math.hypot(x - candidate["page_x"], y - candidate["page_y"])
                    for candidate in candidate_sheet["candidates"]
                ),
                default=math.inf,
            )
            if nearest + 1e-6 < exclusion_radius:
                raise ValueError(f"Model-negative sample too close to candidate: {row['sample_id']}")
            if abs(nearest - float(row["nearest_model_candidate_distance_pixels"])) > 1.0:
                raise ValueError(f"Candidate distance audit mismatch: {row['sample_id']}")
            crop_relative_path = Path(row["crop_path"])
            if (
                crop_relative_path.is_absolute()
                or not crop_relative_path.parts
                or crop_relative_path.parts[0] != "crops"
                or ".." in crop_relative_path.parts
            ):
                raise ValueError(f"Unsafe negative crop path: {row['crop_path']}")
            source_crop = negative_queue_path.parent / crop_relative_path
            if file_sha256(source_crop) != row["crop_sha256"]:
                raise ValueError(f"Negative crop hash mismatch: {row['sample_id']}")
            with Image.open(source_crop) as crop_image:
                if crop_image.size != (crop_size, crop_size):
                    raise ValueError(f"Invalid negative crop dimensions: {row['sample_id']}")
    runtime = {
        "python": sys.version.split()[0],
        "pymupdf": pymupdf.VersionBind,
        "pillow": PIL.__version__,
    }
    build_identity = {
        **input_hashes,
        "runtime": runtime,
        "model_sha256": model_hash,
        "crop_size_pixels": crop_size,
        "render_scale_pixels_per_pdf_point": candidate_data[
            "render_scale_pixels_per_pdf_point"
        ],
    }
    dataset_id = canonical_sha256(build_identity)[:16]
    scale = float(candidate_data["render_scale_pixels_per_pdf_point"])

    # Validate all source files and render dimensions before creating output.
    for source_id, source in source_by_id.items():
        candidate_sheet = candidate_by_id[source_id]
        if candidate_sheet["source_sha256"] != source["sha256"]:
            raise ValueError(f"Source SHA mismatch in candidates: {source['name']}")
        if frame_data["sheets"][source_id]["name"] != source["name"]:
            raise ValueError(f"Map-frame sheet mismatch: {source['name']}")
        local_file = source["local_file"]
        if Path(local_file).name != local_file:
            raise ValueError(f"Unsafe local_file in source manifest: {local_file}")
        pdf_path = data_dir / local_file
        if file_sha256(pdf_path) != source["sha256"]:
            raise ValueError(f"Source PDF hash mismatch: {source['name']}")
        document = pymupdf.open(pdf_path)
        if len(document) != 1:
            document.close()
            raise ValueError(f"Expected one-page source PDF: {source['name']}")
        page = document[0]
        rendered_rect = page.rect * pymupdf.Matrix(scale, scale)
        actual_size = [math.ceil(rendered_rect.width), math.ceil(rendered_rect.height)]
        document.close()
        if actual_size != candidate_sheet["page_size_pixels"]:
            raise ValueError(
                f"Rendered page size mismatch for {source['name']}: "
                f"{actual_size} != {candidate_sheet['page_size_pixels']}"
            )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    (output_dir / "crops").mkdir()
    audit_rows: list[dict[str, Any]] = []
    reviewed_rows: list[dict[str, Any]] = []
    negative_review_rows: list[dict[str, Any]] = []

    try:
        for source_id, source in source_by_id.items():
            candidate_sheet = candidate_by_id[source_id]
            local_file = source["local_file"]
            pdf_path = data_dir / local_file

            document = pymupdf.open(pdf_path)
            page = document[0]
            width, height = candidate_sheet["page_size_pixels"]
            frame = frame_data["sheets"][source_id]
            frame_bounds = frame["bounds"]
            frame_buffer = float(frame_data["boundary_buffer_fraction"])

            for index, candidate in enumerate(candidate_sheet["candidates"], start=1):
                candidate_id = f"{source_id}:{index:04d}"
                decision = decisions.get(candidate_id)
                status = decision.get("status", "pending") if decision else "pending"
                note = decision.get("note", "") if decision else ""
                if status != "pending" and status not in allowed_statuses:
                    raise ValueError(f"Unsupported decision status for {candidate_id}: {status}")
                x, y = candidate["page_x"], candidate["page_y"]
                x_norm, y_norm = x / width, y / height
                sample_id = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:20]
                label = TRAIN_LABELS.get(status, "pending")
                crop_path: str | None = None

                if decision is not None:
                    crop = render_crop(page, x, y, scale, crop_size)
                    relative_path = f"crops/{sample_id}.png"
                    crop_file = output_dir / relative_path
                    crop.save(crop_file, format="PNG", optimize=False)
                    crop_path = relative_path
                    reviewed_rows.append(
                        {
                            "sample_id": sample_id,
                            "candidate_id": candidate_id,
                            "source_id": source_id,
                            "sheet": source["name"],
                            "county": source["county"],
                            "edition_year": source["year"],
                            "page_x": x,
                            "page_y": y,
                            "mask_area_pixels": candidate["mask_area_pixels"],
                            "review_status": status,
                            "label": label,
                            "training_eligible": False,
                            "training_eligibility_reason": "requires_independent_review",
                            "crop_path": relative_path,
                            "crop_sha256": file_sha256(crop_file),
                            "reviewer_note": note,
                        }
                    )

                audit_rows.append(
                    {
                        "candidate_id": candidate_id,
                        "source_id": source_id,
                        "sheet": source["name"],
                        "county": source["county"],
                        "edition_year": source["year"],
                        "page_x": x,
                        "page_y": y,
                        "mask_area_pixels": candidate["mask_area_pixels"],
                        "normalized_x": f"{x_norm:.6f}",
                        "normalized_y": f"{y_norm:.6f}",
                        "screening_zone": zone(x_norm, y_norm, frame_bounds, frame_buffer),
                        "review_status": status,
                        "label": label,
                        "crop_path": crop_path or "",
                        "reviewer_note": note,
                    }
                )
            document.close()
    except Exception:
        # Keep partial outputs recoverable and obvious rather than silently
        # deleting user data if a source or render check fails.
        raise

    negative_status_counts: dict[str, int] = {}
    if negative_queue_path is not None:
        for row in negative_rows:
            sample_id = row["sample_id"]
            is_uncertain = sample_id in negative_decisions
            status = "uncertain" if is_uncertain else "reviewed_no_well_symbol_visible"
            label = "uncertain" if is_uncertain else "background_no_well_symbol_seen"
            note = negative_decisions[sample_id] if is_uncertain else negative_default_note
            relative_path = f"crops/negative_{sample_id}.png"
            crop_path = output_dir / relative_path
            shutil.copyfile(negative_queue_path.parent / row["crop_path"], crop_path)
            negative_review_rows.append(
                {
                    "sample_id": sample_id,
                    "source_id": row["source_id"],
                    "sheet": row["sheet"],
                    "county": row["county"],
                    "edition_year": row["edition_year"],
                    "grid_row": row["grid_row"],
                    "grid_column": row["grid_column"],
                    "page_x": row["page_x"],
                    "page_y": row["page_y"],
                    "nearest_model_candidate_distance_pixels": row[
                        "nearest_model_candidate_distance_pixels"
                    ],
                    "review_status": status,
                    "label": label,
                    "training_eligible": False,
                    "crop_path": relative_path,
                    "crop_sha256": file_sha256(crop_path),
                    "reviewer_note": note,
                }
            )
            negative_status_counts[status] = negative_status_counts.get(status, 0) + 1

    audit_fields = list(audit_rows[0]) if audit_rows else []
    reviewed_fields = list(reviewed_rows[0]) if reviewed_rows else []
    write_csv(output_dir / "candidate_audit.csv", audit_rows, audit_fields)
    write_csv(output_dir / "reviewed_examples.csv", reviewed_rows, reviewed_fields)
    negative_fields = list(negative_review_rows[0]) if negative_review_rows else []
    if negative_queue_path is not None:
        write_csv(output_dir / "negative_review_examples.csv", negative_review_rows, negative_fields)
    output_hashes = {
        "candidate_audit_csv_sha256": file_sha256(output_dir / "candidate_audit.csv"),
        "reviewed_examples_csv_sha256": file_sha256(output_dir / "reviewed_examples.csv"),
        "negative_review_examples_csv_sha256": (
            file_sha256(output_dir / "negative_review_examples.csv")
            if negative_queue_path is not None
            else None
        ),
        "crop_inventory_sha256": canonical_sha256(
            sorted(
                [row["crop_sha256"] for row in reviewed_rows]
                + [row["crop_sha256"] for row in negative_review_rows]
            )
        ),
    }

    counts: dict[str, int] = {}
    candidate_status_counts: dict[str, int] = {}
    positive_sheets: set[str] = set()
    for row in audit_rows:
        status = row["review_status"]
        candidate_status_counts[status] = candidate_status_counts.get(status, 0) + 1
    for row in reviewed_rows:
        status = row["review_status"]
        counts[status] = counts.get(status, 0) + 1
        if status == "confirmed_symbol":
            positive_sheets.add(row["source_id"])
    eligible_positive = counts.get("confirmed_symbol", 0)
    eligible_negative = counts.get("rejected_lookalike", 0)
    manifest_out = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "dataset_type": "private_reviewed_candidate_crop_pilot",
        "status": "not_training_ready",
        "training_ready": False,
        "training_readiness_reason": (
            "All labels are single-reviewer and require independent adjudication; only three "
            "candidate positives across two sheets are confirmed. No split is assigned."
        ),
        "input_hashes": input_hashes,
        "runtime": runtime,
        "output_hashes": output_hashes,
        "model_sha256": model_hash,
        "map_frame_bounds_sha256": input_hashes["map_frame_bounds_sha256"],
        "crop_size_pixels": crop_size,
        "render_scale_pixels_per_pdf_point": scale,
        "source_sheet_count": len(source_by_id),
        "candidate_count": len(audit_rows),
        "reviewed_crop_count": len(reviewed_rows),
        "negative_sample_crop_count": len(negative_review_rows),
        "total_materialized_crop_count": len(reviewed_rows) + len(negative_review_rows),
        "status_counts": counts,
        "candidate_status_counts": candidate_status_counts,
        "negative_sample_status_counts": negative_status_counts,
        "provisional_observation_counts": {
            "single_review_candidate_well_symbol": eligible_positive,
            "single_review_candidate_lookalike": eligible_negative,
            "single_review_candidate_collar_or_page_furniture": counts.get(
                "rejected_collar_or_page_furniture", 0
            ),
            "single_review_candidate_uncertain": counts.get("uncertain", 0),
            "pending_candidates": candidate_status_counts.get("pending", 0),
            "single_review_spatial_sample_no_well_symbol_visible": negative_status_counts.get(
                "reviewed_no_well_symbol_visible", 0
            ),
            "single_review_spatial_sample_uncertain": negative_status_counts.get("uncertain", 0),
        },
        "training_eligible_example_count": 0,
        "positive_source_sheet_count": len(positive_sheets),
        "split_policy": "No split assigned; future split must group by sheet/county.",
        "limitations": [
            "Labels are from one visual reviewer and have not been independently adjudicated.",
            "Reviewed crops are selected from model candidates, not a representative sample.",
            "The model-negative grid is a sparse single-reviewer screen and cannot estimate recall.",
            "Model-negative crops are not marked training-eligible until independently reviewed.",
            "Candidate detections may duplicate a physical symbol; no geospatial or symbol deduplication was done.",
            "Pixel crops are not georeferenced well locations and do not establish field conditions.",
        ],
    }
    (output_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest_out, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="Official source manifest")
    parser.add_argument("--candidates", type=Path, required=True, help="Private model candidate JSON")
    parser.add_argument("--decisions", type=Path, required=True, help="Private review decision JSON")
    parser.add_argument("--data-dir", type=Path, required=True, help="Directory containing source PDFs")
    parser.add_argument("--output-dir", type=Path, required=True, help="New private output directory")
    parser.add_argument("--crop-size", type=int, default=256, help="Square crop edge in pixels")
    parser.add_argument("--negative-queue", type=Path, help="Optional spatial model-negative sample CSV")
    parser.add_argument("--negative-decisions", type=Path, help="Optional review sidecar for the negative sample")
    args = parser.parse_args()
    result = build_dataset(
        manifest_path=args.manifest,
        candidates_path=args.candidates,
        decisions_path=args.decisions,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        crop_size=args.crop_size,
        negative_queue_path=args.negative_queue,
        negative_decisions_path=args.negative_decisions,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
