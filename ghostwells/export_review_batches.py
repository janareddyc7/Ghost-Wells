"""Export private, deterministic contact sheets for pending model candidates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import PIL
import pymupdf
from PIL import Image, ImageDraw, ImageFont

from ghostwells.build_dataset import file_sha256, render_crop
from ghostwells.candidate_review import zone


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_review_batches(
    *,
    manifest_path: Path,
    candidates_path: Path,
    decisions_path: Path,
    data_dir: Path,
    output_dir: Path,
    columns: int = 4,
    rows_per_sheet: int = 4,
    crop_size: int = 256,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    if min(columns, rows_per_sheet) < 1 or crop_size < 64 or crop_size % 2:
        raise ValueError("Grid dimensions must be positive and crop_size even and at least 64")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_data = json.loads(candidates_path.read_text(encoding="utf-8"))
    decision_data = json.loads(decisions_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    frame_path = project_root / "evidence" / "map_frame_bounds.json"
    frame_data = json.loads(frame_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or candidate_data.get("schema_version") != 1:
        raise ValueError("Unsupported source manifest or candidate schema")
    decisions = decision_data.get("decisions")
    if decision_data.get("schema_version") != 1 or not isinstance(decisions, dict):
        raise ValueError("Unsupported candidate decision schema")

    sources = {sheet["source_id"]: sheet for sheet in manifest["sheets"]}
    model_sheets = {sheet["source_id"]: sheet for sheet in candidate_data["sheets"]}
    if set(sources) != set(model_sheets) or set(sources) != set(frame_data["sheets"]):
        raise ValueError("Source, candidate, and frame manifests must cover the same sheets")
    if len(sources) != len(manifest["sheets"]) or len(model_sheets) != len(candidate_data["sheets"]):
        raise ValueError("Duplicate source_id in source or candidate manifest")

    legal_statuses = {
        "pending",
        "confirmed_symbol",
        "rejected_lookalike",
        "rejected_collar_or_page_furniture",
        "uncertain",
        "ai_screen_symbol_candidate",
        "ai_screen_lookalike",
        "ai_screen_uncertain",
        "independent_symbol_candidate",
        "independent_lookalike",
        "independent_uncertain",
    }
    known_candidate_ids = {
        f"{sheet['source_id']}:{index:04d}"
        for sheet in candidate_data["sheets"]
        for index, _ in enumerate(sheet["candidates"], start=1)
    }
    if set(decisions) - known_candidate_ids:
        raise ValueError("Decision overlay contains IDs absent from the candidate file")
    for candidate_id, decision in decisions.items():
        if decision.get("status") not in legal_statuses - {"pending"}:
            raise ValueError(f"Unsupported review status for {candidate_id}")

    scale = float(candidate_data["render_scale_pixels_per_pdf_point"])
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    crop_dir = output_dir / "crops"
    crop_dir.mkdir()
    index_rows: list[dict[str, Any]] = []
    batch_files: list[str] = []
    batch_capacity = columns * rows_per_sheet
    cell_width = crop_size + 20
    cell_height = crop_size + 42

    for source_id, source in sources.items():
        sheet = model_sheets[source_id]
        if sheet["source_sha256"] != source["sha256"]:
            raise ValueError(f"Source hash mismatch for {source['name']}")
        local_file = source["local_file"]
        if Path(local_file).name != local_file:
            raise ValueError(f"Unsafe source filename: {local_file}")
        pdf_path = data_dir / local_file
        if file_sha256(pdf_path) != source["sha256"]:
            raise ValueError(f"Source PDF hash mismatch: {source['name']}")
        if frame_data["sheets"][source_id]["name"] != source["name"]:
            raise ValueError(f"Map frame does not match source: {source['name']}")

        document = pymupdf.open(pdf_path)
        pending: list[dict[str, Any]] = []
        width, height = sheet["page_size_pixels"]
        bounds = frame_data["sheets"][source_id]["bounds"]
        buffer = float(frame_data["boundary_buffer_fraction"])
        for index, candidate in enumerate(sheet["candidates"], start=1):
            candidate_id = f"{source_id}:{index:04d}"
            if candidate_id in decisions:
                continue
            x, y = candidate["page_x"], candidate["page_y"]
            if not (0 <= x < width and 0 <= y < height):
                document.close()
                raise ValueError(f"Candidate outside source page: {candidate_id}")
            crop = render_crop(document[0], x, y, scale, crop_size)
            crop_name = f"{source_id}_{index:04d}.png"
            crop_path = crop_dir / crop_name
            crop.save(crop_path, format="PNG", optimize=False)
            pending.append(
                {
                    "candidate_id": candidate_id,
                    "source_id": source_id,
                    "sheet": source["name"],
                    "page_x": x,
                    "page_y": y,
                    "mask_area_pixels": candidate["mask_area_pixels"],
                    "screening_zone": zone(x / width, y / height, bounds, buffer),
                    "crop_path": f"crops/{crop_name}",
                    "crop_sha256": file_sha256(crop_path),
                    "crop_image": crop,
                }
            )
        document.close()

        for offset in range(0, len(pending), batch_capacity):
            batch_number = offset // batch_capacity + 1
            batch = pending[offset : offset + batch_capacity]
            canvas = Image.new(
                "RGB", (columns * cell_width, rows_per_sheet * cell_height), "white"
            )
            draw = ImageDraw.Draw(canvas)
            font = ImageFont.load_default()
            for position, item in enumerate(batch):
                col, row = position % columns, position // columns
                left, top = col * cell_width + 10, row * cell_height + 4
                suffix = item["candidate_id"].rsplit(":", 1)[1]
                draw.text(
                    (left, top),
                    f"{source['name']} {suffix} | area {item['mask_area_pixels']}",
                    fill="black",
                    font=font,
                )
                canvas.paste(item["crop_image"], (left, top + 18))
                draw.rectangle(
                    (left - 1, top + 17, left + crop_size, top + 18 + crop_size),
                    outline=(170, 170, 170),
                    width=1,
                )
                center_x = left + crop_size // 2
                center_y = top + 18 + crop_size // 2
                for dx1, dy1, dx2, dy2 in (
                    (-22, 0, -12, 0),
                    (12, 0, 22, 0),
                    (0, -22, 0, -12),
                    (0, 12, 0, 22),
                ):
                    draw.line(
                        (center_x + dx1, center_y + dy1, center_x + dx2, center_y + dy2),
                        fill=(235, 25, 25),
                        width=2,
                    )
                item["batch_file"] = f"{source_id}_batch_{batch_number:03d}.png"
                item["batch_cell"] = position + 1
                index_rows.append({key: value for key, value in item.items() if key != "crop_image"})
            batch_path = output_dir / f"{source_id}_batch_{batch_number:03d}.png"
            canvas.save(batch_path, format="PNG", optimize=False)
            batch_files.append(batch_path.name)

    write_csv(output_dir / "review_queue.csv", index_rows)
    result = {
        "schema_version": 1,
        "status": "pending_visual_review",
        "pending_candidate_count": len(index_rows),
        "sheet_count": len(sources),
        "batch_count": len(batch_files),
        "grid": {"columns": columns, "rows": rows_per_sheet, "capacity": batch_capacity},
        "crop_size_pixels": crop_size,
        "input_hashes": {
            "source_manifest_sha256": file_sha256(manifest_path),
            "candidate_json_sha256": file_sha256(candidates_path),
            "decision_json_sha256": file_sha256(decisions_path),
            "map_frame_bounds_sha256": file_sha256(frame_path),
            "exporter_sha256": file_sha256(Path(__file__).resolve()),
        },
        "runtime": {
            "python": sys.version.split()[0],
            "pymupdf": pymupdf.VersionBind,
            "pillow": PIL.__version__,
        },
        "batches": batch_files,
        "contact_sheet_sha256": {
            batch_name: file_sha256(output_dir / batch_name) for batch_name in batch_files
        },
        "warning": "Contact sheets support visual triage; they are not ground truth or independent review.",
    }
    (output_dir / "batch_manifest.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = export_review_batches(
        manifest_path=args.manifest,
        candidates_path=args.candidates,
        decisions_path=args.decisions,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
