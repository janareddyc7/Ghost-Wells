"""Shared guards for whole-map training/evaluation partitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_split_plan(
    path: Path, source_manifest_path: Path, *, require_blind_review: bool = True
) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    sources = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1:
        raise ValueError("Unsupported split-plan schema")
    if plan.get("split_level") != "county":
        raise ValueError("Use county-level groups so no county leaks across the split")
    if plan.get("frozen_before_metrics") is not True:
        raise ValueError("Split plan must be frozen before looking at evaluation metrics")
    if require_blind_review and plan.get("review_inventory_blind_to_model_candidates") is not True:
        raise ValueError("Evaluation annotations must have been made blind to detector candidates")

    train = plan.get("training_source_ids")
    evaluation = plan.get("evaluation_source_ids")
    if (
        not isinstance(train, list)
        or not train
        or not all(isinstance(value, str) for value in train)
        or len(set(train)) != len(train)
    ):
        raise ValueError("Split plan needs unique training_source_ids")
    if (
        not isinstance(evaluation, list)
        or not evaluation
        or not all(isinstance(value, str) for value in evaluation)
        or len(set(evaluation)) != len(evaluation)
    ):
        raise ValueError("Split plan needs unique evaluation_source_ids")
    if set(train) & set(evaluation):
        raise ValueError("A source sheet cannot occur in both training and evaluation")

    sheet_rows = sources.get("sheets")
    if not isinstance(sheet_rows, list):
        raise ValueError("Source manifest has no sheet list")
    counties = {row["source_id"]: row["county"] for row in sheet_rows}
    all_ids = set(counties)
    if set(train) | set(evaluation) != all_ids:
        raise ValueError("Split plan must assign every source sheet exactly once")
    train_counties = {counties[source_id] for source_id in train}
    eval_counties = {counties[source_id] for source_id in evaluation}
    if train_counties & eval_counties:
        raise ValueError("County leakage detected across training/evaluation groups")
    return {
        **plan,
        "training_source_ids": sorted(train),
        "evaluation_source_ids": sorted(evaluation),
        "training_counties": sorted(train_counties),
        "evaluation_counties": sorted(eval_counties),
    }
