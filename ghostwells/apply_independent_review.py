"""Merge an independently attested blind review into a private AI review overlay.

The importer validates exact queue, crop, contact-sheet, and reviewer provenance.
It records map-symbol decisions only; it cannot confirm a physical well.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


DECISION_TO_STATUS = {
    "symbol_candidate": "independent_symbol_candidate",
    "lookalike": "independent_lookalike",
    "uncertain": "independent_uncertain",
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


def apply_independent_review(
    *,
    ai_decisions_path: Path,
    queue_path: Path,
    batch_manifest_path: Path,
    review_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Validate an exported blind review and add it without losing the AI pass."""
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing output file: {output_path}")

    ai_data = read_json(ai_decisions_path)
    batch_manifest = read_json(batch_manifest_path)
    review_data = read_json(review_path)
    ai_provenance = ai_data.get("review_provenance", {})
    if ai_data.get("schema_version") != 1 or not isinstance(ai_data.get("decisions"), dict):
        raise ValueError("Unsupported AI decision overlay")
    if batch_manifest.get("schema_version") != 1 or not isinstance(
        batch_manifest.get("batches"), list
    ):
        raise ValueError("Unsupported review batch manifest")
    if review_data.get("schema_version") != 1:
        raise ValueError("Unsupported independent review schema")
    if review_data.get("review_type") != "independent_blind_candidate_adjudication":
        raise ValueError("Review export is not a blind candidate adjudication")
    if review_data.get("independent_of_ai_screen_attested") is not True:
        raise ValueError("Reviewer did not attest to an independent blind review")
    reviewer_id = review_data.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("Independent reviewer ID is missing")
    if reviewer_id.strip() == ai_provenance.get("reviewer_id"):
        raise ValueError("AI reviewer cannot adjudicate its own screening pass")

    queue_hash = file_sha256(queue_path)
    batch_manifest_hash = file_sha256(batch_manifest_path)
    if queue_hash != ai_provenance.get("review_queue_sha256"):
        raise ValueError("Review queue does not match the original AI screen")
    if review_data.get("queue_sha256") != queue_hash:
        raise ValueError("Independent review references a different queue")
    if review_data.get("batch_manifest_sha256") != batch_manifest_hash:
        raise ValueError("Independent review references a different batch manifest")

    with queue_path.open(newline="", encoding="utf-8") as stream:
        queue_rows = list(csv.DictReader(stream))
    queue_by_id = {row["candidate_id"]: row for row in queue_rows}
    if len(queue_by_id) != len(queue_rows):
        raise ValueError("Duplicate candidate ID in the original review queue")
    if len(queue_rows) != ai_provenance.get("reviewed_pending_candidate_count"):
        raise ValueError("Review queue count differs from the AI decision overlay")

    review_rows = review_data.get("decisions")
    if not isinstance(review_rows, list) or len(review_rows) != len(queue_rows):
        raise ValueError("Independent review must include every queue ID, including pending items")
    review_by_id: dict[str, dict[str, Any]] = {}
    status_counts: Counter[str] = Counter()
    for review_row in review_rows:
        if not isinstance(review_row, dict):
            raise ValueError("Malformed independent-review decision row")
        candidate_id = review_row.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id not in queue_by_id:
            raise ValueError(f"Unknown candidate in independent review: {candidate_id}")
        if candidate_id in review_by_id:
            raise ValueError(f"Duplicate independent-review decision: {candidate_id}")
        source_row = queue_by_id[candidate_id]
        expected = {
            "source_id": source_row["source_id"],
            "sheet": source_row["sheet"],
            "crop_sha256": source_row["crop_sha256"],
            "contact_sheet": source_row["batch_file"],
            "contact_sheet_cell": int(source_row["batch_cell"]),
        }
        if any(review_row.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Candidate provenance mismatch: {candidate_id}")
        choice = review_row.get("decision")
        if choice != "pending" and choice not in DECISION_TO_STATUS:
            raise ValueError(f"Unsupported independent-review choice for {candidate_id}")
        note = review_row.get("review_note", "")
        if not isinstance(note, str):
            raise ValueError(f"Invalid independent-review note: {candidate_id}")
        review_by_id[candidate_id] = review_row
        status_counts[str(choice)] += 1

    if set(review_by_id) != set(queue_by_id):
        raise ValueError("Independent review does not cover the exact candidate queue")
    reviewed_count = len(queue_rows) - status_counts.get("pending", 0)
    if review_data.get("reviewed_count") != reviewed_count:
        raise ValueError("Independent-review completed count does not match its decision rows")
    if review_data.get("pending_count") != status_counts.get("pending", 0):
        raise ValueError("Independent-review pending count does not match its decision rows")
    all_reviewed = status_counts.get("pending", 0) == 0
    if review_data.get("all_queued_candidates_reviewed") is not all_reviewed:
        raise ValueError("Independent-review completion flag does not match its decision rows")

    expected_batch_names = set(batch_manifest["batches"])
    manifest_batch_hashes = batch_manifest.get("contact_sheet_sha256")
    supplied_batch_hashes = review_data.get("contact_sheet_sha256")
    ai_batch_hashes = ai_provenance.get("contact_sheet_sha256")
    if (
        not isinstance(manifest_batch_hashes, dict)
        or set(manifest_batch_hashes) != expected_batch_names
        or manifest_batch_hashes != ai_batch_hashes
    ):
        raise ValueError("Batch manifest contact-sheet hashes differ from the AI screen")
    if (
        not isinstance(supplied_batch_hashes, dict)
        or set(supplied_batch_hashes) != expected_batch_names
        or supplied_batch_hashes != manifest_batch_hashes
    ):
        raise ValueError("Independent-review contact-sheet hashes differ from the original batch")
    for batch_name in expected_batch_names:
        batch_path = batch_manifest_path.parent / batch_name
        if file_sha256(batch_path) != supplied_batch_hashes[batch_name]:
            raise ValueError(f"Contact sheet changed since independent review: {batch_name}")

    decisions = dict(ai_data["decisions"])
    applied_count = 0
    for candidate_id, review_row in review_by_id.items():
        choice = review_row["decision"]
        if choice == "pending":
            continue
        original = decisions.get(candidate_id)
        if not isinstance(original, dict) or not str(original.get("status", "")).startswith(
            "ai_screen_"
        ):
            raise ValueError(f"Candidate has no provisional AI status to adjudicate: {candidate_id}")
        updated = dict(original)
        updated["ai_visual_screen"] = {
            "status": original["status"],
            "note": original.get("note", ""),
            "reviewer_id": original.get("reviewer_id"),
            "review_method": original.get("review_method"),
            "review_confidence": original.get("review_confidence"),
        }
        updated.update(
            {
                "status": DECISION_TO_STATUS[choice],
                "note": review_row.get("review_note", ""),
                "reviewer_id": reviewer_id.strip(),
                "review_method": "independent_blind_candidate_adjudication",
                "review_confidence": "independent_visual_review",
                "independent_review_required": False,
                "independent_review_decided_at_utc": review_row.get("decided_at_utc"),
            }
        )
        decisions[candidate_id] = updated
        applied_count += 1

    result = dict(ai_data)
    result["decisions"] = decisions
    result["independent_review_provenance"] = {
        "reviewer_id": reviewer_id.strip(),
        "review_type": review_data["review_type"],
        "blind_review_attested": True,
        "complete": all_reviewed,
        "reviewed_count": reviewed_count,
        "pending_count": status_counts.get("pending", 0),
        "applied_count": applied_count,
        "choice_counts": dict(sorted(status_counts.items())),
        "review_export_sha256": file_sha256(review_path),
        "queue_sha256": queue_hash,
        "batch_manifest_sha256": batch_manifest_hash,
        "contact_sheet_sha256": supplied_batch_hashes,
        "importer_sha256": file_sha256(Path(__file__).resolve()),
        "limitation": "A map-symbol decision is not physical-well verification or ground truth.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return {
        "output_path": str(output_path),
        "reviewer_id": reviewer_id.strip(),
        "reviewed_count": reviewed_count,
        "pending_count": status_counts.get("pending", 0),
        "applied_count": applied_count,
        "complete": all_reviewed,
        "choice_counts": dict(sorted(status_counts.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai-decisions", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--batch-manifest", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            apply_independent_review(
                ai_decisions_path=args.ai_decisions,
                queue_path=args.queue,
                batch_manifest_path=args.batch_manifest,
                review_path=args.review,
                output_path=args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
