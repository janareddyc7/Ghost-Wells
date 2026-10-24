"""Create a deterministic, spatially stratified queue of model-negative map chips."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import PIL
import pymupdf

from ghostwells.build_dataset import file_sha256, render_crop
from ghostwells.candidate_review import zone


def stable_rng(seed: str, source_id: str, row: int, column: int) -> random.Random:
    token = f"{seed}|{source_id}|{row}|{column}".encode("utf-8")
    stream_seed = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return random.Random(stream_seed)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sample_negatives(
    *,
    manifest_path: Path,
    candidates_path: Path,
    data_dir: Path,
    output_dir: Path,
    seed: str = "ghost-wells-grid-v1",
    grid_rows: int = 4,
    grid_columns: int = 4,
    crop_size: int = 256,
    exclusion_radius: int = 256,
    attempts_per_cell: int = 500,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    if min(grid_rows, grid_columns, crop_size, exclusion_radius, attempts_per_cell) < 1:
        raise ValueError("Grid sizes, crop size, exclusion radius, and attempts must be positive")
    if crop_size % 2:
        raise ValueError("crop_size must be even")
    if exclusion_radius < math.ceil(crop_size * math.sqrt(2) / 2):
        raise ValueError("exclusion_radius must clear the full crop half-diagonal")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_data = json.loads(candidates_path.read_text(encoding="utf-8"))
    frame_path = Path(__file__).resolve().parents[1] / "evidence" / "map_frame_bounds.json"
    frame_data = json.loads(frame_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or candidate_data.get("schema_version") != 1:
        raise ValueError("Unsupported source or candidate schema")

    sources = {sheet["source_id"]: sheet for sheet in manifest["sheets"]}
    model_sheets = {sheet["source_id"]: sheet for sheet in candidate_data["sheets"]}
    if set(sources) != set(model_sheets) or set(sources) != set(frame_data["sheets"]):
        raise ValueError("Source, candidate, and frame manifests must cover the same sheets")
    model_hash = candidate_data.get("model_sha256")
    if not isinstance(model_hash, str) or len(model_hash) != 64:
        raise ValueError("Candidate file has no valid model SHA-256")

    scale = float(candidate_data["render_scale_pixels_per_pdf_point"])
    radius_sq = exclusion_radius**2
    input_hashes = {
        "source_manifest_sha256": file_sha256(manifest_path),
        "candidate_json_sha256": file_sha256(candidates_path),
        "map_frame_bounds_sha256": file_sha256(frame_path),
        "builder_sha256": file_sha256(Path(__file__).resolve()),
    }
    runtime = {
        "python": sys.version.split()[0],
        "pymupdf": pymupdf.VersionBind,
        "pillow": PIL.__version__,
    }
    config = {
        "seed": seed,
        "grid_rows": grid_rows,
        "grid_columns": grid_columns,
        "crop_size_pixels": crop_size,
        "candidate_exclusion_radius_pixels": exclusion_radius,
        "attempts_per_cell": attempts_per_cell,
        "render_scale_pixels_per_pdf_point": scale,
    }
    sample_set_id = hashlib.sha256(
        json.dumps({**input_hashes, **config, "runtime": runtime}, sort_keys=True).encode()
    ).hexdigest()[:16]

    # Validate every scan before materializing the sample batch.
    for source_id, source in sources.items():
        if model_sheets[source_id]["source_sha256"] != source["sha256"]:
            raise ValueError(f"Source SHA mismatch for {source['name']}")
        local_file = source["local_file"]
        if Path(local_file).name != local_file:
            raise ValueError(f"Unsafe local_file in manifest: {local_file}")
        pdf_path = data_dir / local_file
        if file_sha256(pdf_path) != source["sha256"]:
            raise ValueError(f"Source PDF hash mismatch: {source['name']}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    (output_dir / "crops").mkdir()
    rows_out: list[dict[str, Any]] = []
    cell_results: list[dict[str, Any]] = []

    for source_id, source in sources.items():
        sheet = model_sheets[source_id]
        width, height = sheet["page_size_pixels"]
        frame = frame_data["sheets"][source_id]
        bounds = frame["bounds"]
        boundary_buffer = float(frame_data["boundary_buffer_fraction"])
        detections = [(c["page_x"], c["page_y"]) for c in sheet["candidates"]]
        chosen: list[tuple[int, int]] = []
        for row_index in range(grid_rows):
            for column_index in range(grid_columns):
                left = (column_index + 0.12) * width / grid_columns
                right = (column_index + 0.88) * width / grid_columns
                top = (row_index + 0.12) * height / grid_rows
                bottom = (row_index + 0.88) * height / grid_rows
                rng = stable_rng(seed, source_id, row_index, column_index)
                selected: tuple[int, int] | None = None
                best_distance = -1.0
                for _ in range(attempts_per_cell):
                    x = round(rng.uniform(left, right))
                    y = round(rng.uniform(top, bottom))
                    if zone(x / width, y / height, bounds, boundary_buffer) != (
                        "map_interior_manual_review"
                    ):
                        continue
                    distances = [(x - px) ** 2 + (y - py) ** 2 for px, py in detections]
                    nearest_sq = min(distances, default=math.inf)
                    if nearest_sq < radius_sq:
                        continue
                    if any(
                        abs(x - qx) < crop_size and abs(y - qy) < crop_size
                        for qx, qy in chosen
                    ):
                        continue
                    selected = (x, y)
                    best_distance = math.sqrt(nearest_sq)
                    break

                cell_info: dict[str, Any] = {
                    "source_id": source_id,
                    "sheet": source["name"],
                    "grid_row": row_index,
                    "grid_column": column_index,
                    "selected": selected is not None,
                }
                if selected is None:
                    cell_info["reason"] = "no_clear_interior_location_found"
                    cell_results.append(cell_info)
                    continue

                x, y = selected
                chosen.append(selected)
                sample_key = f"{sample_set_id}:{source_id}:{row_index}:{column_index}"
                sample_id = hashlib.sha256(sample_key.encode()).hexdigest()[:20]
                pdf_path = data_dir / source["local_file"]
                document = pymupdf.open(pdf_path)
                crop = render_crop(document[0], x, y, scale, crop_size)
                document.close()
                relative_path = f"crops/{sample_id}.png"
                crop_path = output_dir / relative_path
                crop.save(crop_path, format="PNG", optimize=False)
                row_data = {
                    "sample_id": sample_id,
                    "source_id": source_id,
                    "sheet": source["name"],
                    "county": source["county"],
                    "edition_year": source["year"],
                    "grid_row": row_index,
                    "grid_column": column_index,
                    "page_x": x,
                    "page_y": y,
                    "normalized_x": f"{x / width:.6f}",
                    "normalized_y": f"{y / height:.6f}",
                    "nearest_model_candidate_distance_pixels": round(best_distance, 2),
                    "crop_size_pixels": crop_size,
                    "crop_path": relative_path,
                    "crop_sha256": file_sha256(crop_path),
                    "review_status": "pending_negative_review",
                    "label": "unlabeled",
                    "reviewer_note": "",
                }
                rows_out.append(row_data)
                cell_results.append(cell_info)

    write_csv(output_dir / "negative_review_queue.csv", rows_out)
    actual_hashes = {**input_hashes, "negative_review_queue_sha256": file_sha256(output_dir / "negative_review_queue.csv")}
    queue_manifest = {
        "schema_version": 1,
        "sample_set_id": sample_set_id,
        "status": "pending_visual_review_not_negative_labels",
        "sampling_method": "One deterministic jittered point per grid cell, accepted only inside the buffered map frame and outside candidate exclusion radius.",
        "input_hashes": actual_hashes,
        "model_sha256": model_hash,
        "runtime": runtime,
        "sampling_config": config,
        "sheet_count": len(sources),
        "grid_cell_count": grid_rows * grid_columns * len(sources),
        "selected_sample_count": len(rows_out),
        "unfilled_cells": [cell for cell in cell_results if not cell["selected"]],
        "limitations": [
            "Selected points are model-negative locations, not confirmed negative examples until a person inspects each crop.",
            "A sparse grid is a quality-control sample, not a precise recall estimate or exhaustive search.",
            "One crop may contain multiple map symbols; record symbol presence and type, not just the center pixel.",
            "Page-pixel samples are not georeferenced locations.",
        ],
    }
    (output_dir / "sample_manifest.json").write_text(
        json.dumps(queue_manifest, indent=2) + "\n", encoding="utf-8"
    )
    return queue_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", default="ghost-wells-grid-v1")
    parser.add_argument("--grid-rows", type=int, default=4)
    parser.add_argument("--grid-columns", type=int, default=4)
    parser.add_argument("--crop-size", type=int, default=256)
    parser.add_argument("--exclusion-radius", type=int, default=256)
    args = parser.parse_args()
    result = sample_negatives(
        manifest_path=args.manifest,
        candidates_path=args.candidates,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        seed=args.seed,
        grid_rows=args.grid_rows,
        grid_columns=args.grid_columns,
        crop_size=args.crop_size,
        exclusion_radius=args.exclusion_radius,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
