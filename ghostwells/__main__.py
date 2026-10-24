"""Command-line entry point for reproducible research tasks."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ghostwells.evidence import verify_files
from ghostwells.model_candidates import detect_candidates
from ghostwells.tiling import create_tiles

REQUIRED_COLUMNS = {
    "sheet_id", "quadrangle", "county", "edition_year", "source_url",
    "review_status", "well_symbols", "lookalikes", "reviewer", "notes",
}
VALID_STATUSES = {"pending", "reviewed", "rejected"}


def read_sheets(path: Path) -> list[dict[str, str]]:
    """Read an inventory, rejecting malformed rows before any report is written."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Sheet inventory is empty")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    seen: set[tuple[str, str]] = set()
    for line, row in enumerate(rows, start=2):
        key = (row["sheet_id"].strip(), row["edition_year"].strip())
        if not all(key):
            raise ValueError(f"Line {line}: sheet_id and edition_year are required")
        if key in seen:
            raise ValueError(f"Line {line}: duplicate sheet_id and edition_year")
        seen.add(key)
        status = row["review_status"].strip().lower()
        if status not in VALID_STATUSES:
            raise ValueError(f"Line {line}: invalid review_status {status!r}")
        if status == "reviewed":
            if not row["source_url"].strip() or not row["reviewer"].strip():
                raise ValueError(f"Line {line}: reviewed rows need source_url and reviewer")
            for column in ("well_symbols", "lookalikes"):
                try:
                    count = int(row[column])
                except (TypeError, ValueError) as error:
                    raise ValueError(f"Line {line}: {column} must be a count") from error
                if count < 0:
                    raise ValueError(f"Line {line}: {column} cannot be negative")
        elif row["well_symbols"].strip() or row["lookalikes"].strip():
            raise ValueError(f"Line {line}: counts require reviewed status")
    return rows


def summarize(rows: list[dict[str, str]]) -> dict[str, object]:
    """Produce aggregate counts without copying precise locations or source notes."""
    statuses = Counter(row["review_status"].strip().lower() for row in rows)
    reviewed = [row for row in rows if row["review_status"].strip().lower() == "reviewed"]
    by_county: dict[str, dict[str, int]] = {}
    for row in reviewed:
        county = row["county"].strip() or "Unknown"
        item = by_county.setdefault(county, {"editions": 0, "well_symbols": 0, "lookalikes": 0})
        item["editions"] += 1
        item["well_symbols"] += int(row["well_symbols"])
        item["lookalikes"] += int(row["lookalikes"])
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_editions": len(rows),
        "statuses": {status: statuses[status] for status in sorted(VALID_STATUSES)},
        "reviewed_well_symbols": sum(int(row["well_symbols"]) for row in reviewed),
        "reviewed_lookalikes": sum(int(row["lookalikes"]) for row in reviewed),
        "by_county": dict(sorted(by_county.items())),
        "note": "Counts are map symbols observed by reviewers, not confirmed wells.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ghost Wells research commands")
    subcommands = parser.add_subparsers(dest="command", required=True)
    survey = subcommands.add_parser("survey", help="Summarize a reviewed sheet inventory")
    survey.add_argument("--input", type=Path, required=True)
    survey.add_argument("--output", type=Path, required=True)
    verify = subcommands.add_parser("verify", help="Check downloaded USGS scans against a manifest")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--data-dir", type=Path, required=True)
    tiles = subcommands.add_parser("tiles", help="Render local PDFs into overlapping review chips")
    tiles.add_argument("--manifest", type=Path, required=True)
    tiles.add_argument("--data-dir", type=Path, required=True)
    tiles.add_argument("--output-dir", type=Path, required=True)
    tiles.add_argument("--scale", type=float, default=2.5)
    tiles.add_argument("--tile-size", type=int, default=512)
    tiles.add_argument("--overlap", type=int, default=64)
    candidates = subcommands.add_parser(
        "candidates", help="Generate unreviewed well-symbol candidates with the published U-Net"
    )
    candidates.add_argument("--manifest", type=Path, required=True)
    candidates.add_argument("--data-dir", type=Path, required=True)
    candidates.add_argument("--model", type=Path, required=True)
    candidates.add_argument("--output", type=Path, required=True)
    candidates.add_argument("--scale", type=float, default=4.1666667)
    candidates.add_argument("--threshold", type=float, default=0.5)
    candidates.add_argument("--min-area", type=int, default=45)
    candidates.add_argument("--batch-size", type=int, default=8)
    candidates.add_argument("--sheet-id", action="append", default=[])
    args = parser.parse_args()

    if args.command == "survey":
        try:
            report = summarize(read_sheets(args.input))
        except (OSError, ValueError) as error:
            parser.error(str(error))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote survey report to {args.output}")
    elif args.command == "verify":
        try:
            errors = verify_files(args.manifest, args.data_dir)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            parser.error(str(error))
        if errors:
            parser.exit(1, "\n".join(errors) + "\n")
        print("All source scans match the evidence manifest")
    elif args.command == "tiles":
        try:
            result = create_tiles(
                args.manifest,
                args.data_dir,
                args.output_dir,
                scale=args.scale,
                tile_size=args.tile_size,
                overlap=args.overlap,
            )
        except (OSError, ValueError, RuntimeError) as error:
            parser.error(str(error))
        print(f"Wrote review chips and manifest to {result}")
    elif args.command == "candidates":
        try:
            result = detect_candidates(
                args.manifest,
                args.data_dir,
                args.model,
                args.output,
                scale=args.scale,
                threshold=args.threshold,
                min_area=args.min_area,
                batch_size=args.batch_size,
                sheet_ids=set(args.sheet_id) if args.sheet_id else None,
            )
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            parser.error(str(error))
        for sheet in result["sheets"]:
            print(f"{sheet['sheet']}: {len(sheet['candidates'])} unreviewed candidates")
        print(f"Wrote candidate set to {args.output}")


if __name__ == "__main__":
    main()
