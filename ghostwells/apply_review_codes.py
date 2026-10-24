"""Apply a coded single-pass visual screen to a private candidate review queue.

This utility preserves the original decision overlay and records AI-screened
items with explicitly provisional statuses. It is not a ground-truth labeler.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CODE_TO_STATUS = {
    "S": "ai_screen_symbol_candidate",
    "R": "ai_screen_lookalike",
    "U": "ai_screen_uncertain",
}

STATUS_NOTES = {
    "S": (
        "AI visual screen: the target appears to align with a recurring open-circle, "
        "well-like map symbol. Provisional model-candidate triage only; independent human "
        "review is required."
    ),
    "R": (
        "AI visual screen: the target appears to align with contour, road, text, or other "
        "non-well map detail rather than an isolated well-like symbol. Provisional only; "
        "independent human review is required."
    ),
    "U": (
        "AI visual screen: the target is ambiguous at the available crop/contact-sheet scale. "
        "It remains uncertain; independent human review is required."
    ),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def apply_review_codes(
    *,
    manifest_path: Path,
    candidates_path: Path,
    source_decisions_path: Path,
    queue_path: Path,
    batch_manifest_path: Path,
    codebook_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Validate and apply compact S/R/U codes to every pending queue row."""
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing output file: {output_path}")

    batch_manifest = read_json(batch_manifest_path)
    source_decisions = read_json(source_decisions_path)
    codebook = read_json(codebook_path)
    if batch_manifest.get("schema_version") != 1:
        raise ValueError("Unsupported review-batch manifest schema")
    if batch_manifest.get("status") != "pending_visual_review":
        raise ValueError("Review-batch manifest is not a pending visual-review export")
    if source_decisions.get("schema_version") != 1 or not isinstance(
        source_decisions.get("decisions"), dict
    ):
        raise ValueError("Unsupported source decision overlay")
    if codebook.get("schema_version") != 1 or not isinstance(
        codebook.get("codes_by_sheet"), dict
    ):
        raise ValueError("Unsupported AI review codebook")
    if codebook.get("status") != "provisional_ai_visual_screen":
        raise ValueError("Codebook is not marked as a provisional AI visual screen")
    for field in ("reviewer_id", "reviewed_on", "review_method"):
        if not isinstance(codebook.get(field), str) or not codebook[field].strip():
            raise ValueError(f"Codebook is missing required provenance: {field}")

    expected_hashes = {
        "source_manifest_sha256": file_sha256(manifest_path),
        "candidate_json_sha256": file_sha256(candidates_path),
        "decision_json_sha256": file_sha256(source_decisions_path),
    }
    for key, expected in expected_hashes.items():
        if batch_manifest.get("input_hashes", {}).get(key) != expected:
            raise ValueError(f"Review batches were built from different inputs: {key}")

    with queue_path.open(newline="", encoding="utf-8") as stream:
        queue_rows = list(csv.DictReader(stream))
    if batch_manifest.get("pending_candidate_count") != len(queue_rows):
        raise ValueError("Review queue count does not match its batch manifest")
    if len({row.get("candidate_id") for row in queue_rows}) != len(queue_rows):
        raise ValueError("Duplicate candidate_id in review queue")

    rows_by_sheet: dict[str, list[dict[str, str]]] = defaultdict(list)
    rows_by_batch: dict[str, list[dict[str, str]]] = defaultdict(list)
    batch_names = set(batch_manifest.get("batches", []))
    batch_hashes: dict[str, str] = {}
    seen_batch_names: set[str] = set()
    cells_by_batch: dict[str, set[int]] = defaultdict(set)
    last_candidate_number_by_sheet: dict[str, int] = {}
    capacity = int(batch_manifest["grid"]["capacity"])
    for row in queue_rows:
        candidate_id = row.get("candidate_id", "")
        source_id, separator, suffix = candidate_id.partition(":")
        if not separator or len(suffix) != 4 or not suffix.isdigit():
            raise ValueError(f"Malformed candidate_id in review queue: {candidate_id}")
        if row.get("source_id") != source_id:
            raise ValueError(f"Candidate/source ID mismatch: {candidate_id}")
        rows_by_sheet[row["sheet"]].append(row)
        candidate_number = int(suffix)
        previous_number = last_candidate_number_by_sheet.get(row["sheet"])
        if previous_number is not None and candidate_number <= previous_number:
            raise ValueError(f"Candidate queue is not in stable per-sheet order: {candidate_id}")
        last_candidate_number_by_sheet[row["sheet"]] = candidate_number

        crop_relative = Path(row.get("crop_path", ""))
        if (
            crop_relative.is_absolute()
            or not crop_relative.parts
            or crop_relative.parts[0] != "crops"
            or ".." in crop_relative.parts
        ):
            raise ValueError(f"Unsafe candidate crop path: {row.get('crop_path')}")
        crop_path = queue_path.parent / crop_relative
        if file_sha256(crop_path) != row.get("crop_sha256"):
            raise ValueError(f"Candidate crop hash mismatch: {candidate_id}")

        batch_name = row.get("batch_file", "")
        if Path(batch_name).name != batch_name or batch_name not in batch_names:
            raise ValueError(f"Unknown/unsafe batch image in review queue: {batch_name}")
        seen_batch_names.add(batch_name)
        rows_by_batch[batch_name].append(row)
        try:
            cell = int(row["batch_cell"])
        except (KeyError, ValueError) as error:
            raise ValueError(f"Invalid contact-sheet cell for {candidate_id}") from error
        if not 1 <= cell <= capacity or cell in cells_by_batch[batch_name]:
            raise ValueError(f"Invalid or duplicate contact-sheet cell for {candidate_id}")
        cells_by_batch[batch_name].add(cell)

    if seen_batch_names != batch_names:
        raise ValueError("Batch manifest and review queue list different contact sheets")
    expected_batch_hashes = batch_manifest.get("contact_sheet_sha256")
    if not isinstance(expected_batch_hashes, dict) or set(expected_batch_hashes) != batch_names:
        raise ValueError("Batch manifest does not contain hashes for every contact sheet")
    if any(
        [int(row["batch_cell"]) for row in batch_rows]
        != list(range(1, len(batch_rows) + 1))
        for batch_rows in rows_by_batch.values()
    ):
        raise ValueError("Contact-sheet cells are not a contiguous 1-based sequence")
    for batch_name in sorted(batch_names):
        batch_path = batch_manifest_path.parent / batch_name
        actual_hash = file_sha256(batch_path)
        if expected_batch_hashes[batch_name] != actual_hash:
            raise ValueError(f"Contact-sheet hash mismatch: {batch_name}")
        batch_hashes[batch_name] = actual_hash

    codes_by_sheet = codebook["codes_by_sheet"]
    if set(codes_by_sheet) != set(rows_by_sheet):
        raise ValueError("Codebook sheet names do not match the review queue")

    counts: Counter[str] = Counter()
    new_decisions: dict[str, dict[str, Any]] = {}
    for sheet, sheet_rows in rows_by_sheet.items():
        raw_codes = codes_by_sheet[sheet]
        if isinstance(raw_codes, list) and all(isinstance(part, str) for part in raw_codes):
            codes = "".join(raw_codes)
        elif isinstance(raw_codes, str):
            codes = raw_codes
        else:
            raise ValueError(f"Codes for {sheet} must be a string or a list of strings")
        if len(codes) != len(sheet_rows):
            raise ValueError(
                f"Code count for {sheet} ({len(codes)}) does not match queued candidates "
                f"({len(sheet_rows)})"
            )
        invalid = sorted(set(codes) - set(CODE_TO_STATUS))
        if invalid:
            raise ValueError(f"Unsupported review code(s) for {sheet}: {invalid}")

        for row, code in zip(sheet_rows, codes, strict=True):
            candidate_id = row["candidate_id"]
            if candidate_id in source_decisions["decisions"]:
                raise ValueError(f"Queue candidate already has a source decision: {candidate_id}")
            status = CODE_TO_STATUS[code]
            counts[status] += 1
            new_decisions[candidate_id] = {
                "status": status,
                "note": STATUS_NOTES[code],
                "reviewer_id": codebook.get("reviewer_id", "codex_ai_visual_screen"),
                "review_method": codebook.get("review_method"),
                "review_confidence": "provisional",
                "independent_review_required": True,
                "contact_sheet": row["batch_file"],
                "contact_sheet_cell": int(row["batch_cell"]),
            }

    if len(new_decisions) != len(queue_rows):
        raise ValueError("Not every pending queue row received exactly one coded decision")

    result = dict(source_decisions)
    result["reviewed_on"] = codebook.get("reviewed_on")
    result["review_scope"] = (
        "Original decisions are preserved. Every candidate that was pending in the referenced "
        "queue received a single-pass AI visual screen. AI statuses are provisional and require "
        "independent human adjudication; they are not ground truth."
    )
    result["review_provenance"] = {
        "reviewer_id": codebook.get("reviewer_id"),
        "review_method": codebook.get("review_method"),
        "independently_adjudicated": False,
        "reviewed_pending_candidate_count": len(new_decisions),
        "status_counts": dict(sorted(counts.items())),
        "source_decisions_sha256": file_sha256(source_decisions_path),
        "review_queue_sha256": file_sha256(queue_path),
        "batch_manifest_sha256": file_sha256(batch_manifest_path),
        "codebook_sha256": file_sha256(codebook_path),
        "review_applier_sha256": file_sha256(Path(__file__).resolve()),
        "contact_sheet_sha256": batch_hashes,
        "limitations": codebook.get("limitations", []),
    }
    result["decisions"] = {**source_decisions["decisions"], **new_decisions}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return {
        "output_path": str(output_path),
        "reviewed_pending_candidate_count": len(new_decisions),
        "preserved_original_decision_count": len(source_decisions["decisions"]),
        "total_decision_count": len(result["decisions"]),
        "status_counts": dict(sorted(counts.items())),
        "independently_adjudicated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-decisions", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--batch-manifest", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            apply_review_codes(
                manifest_path=args.manifest,
                candidates_path=args.candidates,
                source_decisions_path=args.source_decisions,
                queue_path=args.queue,
                batch_manifest_path=args.batch_manifest,
                codebook_path=args.codebook,
                output_path=args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
