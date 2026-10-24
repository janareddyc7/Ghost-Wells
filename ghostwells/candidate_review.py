"""Build a private, auditable review queue from raw model candidates.

This utility does not promote candidates to wells. It applies manually traced,
per-sheet rectangular neatlines with an uncertainty buffer. Exterior detections
are prioritized for collar/page-furniture review, never automatically discarded.
The bounds are screening geometry, not a georeference.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def zone(x: float, y: float, bounds: dict[str, float], buffer: float) -> str:
    """Classify map interior, uncertain frame edge, or exterior for review."""
    if (
        x < bounds["left"] - buffer
        or x > bounds["right"] + buffer
        or y < bounds["top"] - buffer
        or y > bounds["bottom"] + buffer
    ):
        return "collar_or_page_furniture_manual_review"
    if (
        x < bounds["left"] + buffer
        or x > bounds["right"] - buffer
        or y < bounds["top"] + buffer
        or y > bounds["bottom"] - buffer
    ):
        return "frame_edge_manual_review"
    return "map_interior_manual_review"


def build_queue(
    input_path: Path,
    output_path: Path,
    decisions_path: Path | None = None,
) -> dict[str, int]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    frame_path = Path(__file__).resolve().parents[1] / "evidence" / "map_frame_bounds.json"
    frame_data = json.loads(frame_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("sheets"), list):
        raise ValueError("Unsupported candidate JSON schema")
    if frame_data.get("schema_version") != 1 or not isinstance(frame_data.get("sheets"), dict):
        raise ValueError("Unsupported map-frame schema")
    buffer = float(frame_data["boundary_buffer_fraction"])
    expected_ids = {sheet["source_id"] for sheet in payload["sheets"]}
    configured_ids = set(frame_data["sheets"])
    if expected_ids != configured_ids:
        raise ValueError("Candidate sheets do not match configured map-frame source IDs")

    decisions: dict[str, dict[str, str]] = {}
    if decisions_path is not None and decisions_path.is_file():
        decision_data = json.loads(decisions_path.read_text(encoding="utf-8"))
        if decision_data.get("schema_version") != 1 or not isinstance(
            decision_data.get("decisions"), dict
        ):
            raise ValueError("Unsupported candidate-decision schema")
        decisions = decision_data["decisions"]

    rows: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for sheet in payload["sheets"]:
        frame = frame_data["sheets"][sheet["source_id"]]
        if frame["name"] != sheet["sheet"]:
            raise ValueError(f"Map-frame sheet mismatch for source {sheet['source_id']}")
        bounds = frame["bounds"]
        width, height = sheet["page_size_pixels"]
        for index, candidate in enumerate(sheet["candidates"], start=1):
            x_px, y_px = candidate["page_x"], candidate["page_y"]
            if not (0 <= x_px < width and 0 <= y_px < height):
                raise ValueError(f"Candidate outside page bounds: {sheet['sheet']} #{index}")
            x_norm, y_norm = x_px / width, y_px / height
            candidate_id = f"{sheet['source_id']}:{index:04d}"
            seen_ids.add(candidate_id)
            decision = decisions.get(candidate_id, {})
            if decision.get("status", "pending") not in {
                "pending",
                "rejected_collar_or_page_furniture",
                "rejected_lookalike",
                "confirmed_symbol",
                "uncertain",
                "ai_screen_symbol_candidate",
                "ai_screen_lookalike",
                "ai_screen_uncertain",
                "independent_symbol_candidate",
                "independent_lookalike",
                "independent_uncertain",
            }:
                raise ValueError(f"Unsupported review status for {candidate_id}")
            rows.append(
                {
                    "source_id": sheet["source_id"],
                    "sheet": sheet["sheet"],
                    "candidate_id": candidate_id,
                    "page_x": x_px,
                    "page_y": y_px,
                    "normalized_x": f"{x_norm:.6f}",
                    "normalized_y": f"{y_norm:.6f}",
                    "mask_area_pixels": candidate["mask_area_pixels"],
                    "screening_zone": zone(x_norm, y_norm, bounds, buffer),
                    "review_status": decision.get("status", "pending"),
                    "reviewer_note": decision.get("note", ""),
                }
            )

    unknown_decisions = set(decisions) - seen_ids
    if unknown_decisions:
        raise ValueError(f"Decision IDs absent from candidate input: {sorted(unknown_decisions)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ["source_id", "sheet", "candidate_id"]
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = {"total": len(rows)}
    for row in rows:
        key = str(row["screening_zone"])
        summary[key] = summary.get(key, 0) + 1
        status_key = f"status_{row['review_status']}"
        summary[status_key] = summary.get(status_key, 0) + 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Private raw candidate JSON")
    parser.add_argument("output", type=Path, help="Private CSV review queue")
    parser.add_argument(
        "--decisions", type=Path, help="Optional private JSON overlay of human review decisions"
    )
    args = parser.parse_args()
    summary = build_queue(args.input, args.output, args.decisions)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
