"""Train a frozen-pretrained visual-embedding ranker from mixed weak labels.

The ImageNet EfficientNet backbone remains frozen. Only a regularized linear
probe is fit, with provenance weights from ``prepare_weak_fit``. No validation
or evaluation metrics are produced; uncertain examples receive a private
priority score for later review, not a probability of being a real well.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from torch import nn
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0

from ghostwells.build_dataset import file_sha256
from ghostwells.prepare_weak_fit import read_csv
from ghostwells.train_patch_classifier import read_weak_fit_rows


def make_features(
    rows: list[dict[str, str]], dataset_dir: Path, backbone: nn.Module, transform: Any, device: torch.device
) -> torch.Tensor:
    tensors = []
    for row in rows:
        relative = Path(row["crop_path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError(f"Unsafe image path in ranker input: {row['sample_id']}")
        image_path = (dataset_dir / relative).resolve()
        if not image_path.is_relative_to(dataset_dir.resolve()) or not image_path.is_file():
            raise ValueError(f"Missing or unsafe ranker crop: {row['sample_id']}")
        if file_sha256(image_path) != row["crop_sha256"]:
            raise ValueError(f"Ranker crop hash mismatch: {row['sample_id']}")
        with Image.open(image_path) as image:
            tensors.append(transform(image.convert("RGB")))
    batches = []
    backbone.eval()
    with torch.inference_mode():
        for start in range(0, len(tensors), 32):
            batch = torch.stack(tensors[start : start + 32]).to(device)
            batches.append(backbone(batch).flatten(1).cpu())
    return torch.cat(batches, dim=0)


def train_embedding_ranker(
    *, dataset_dir: Path, output_dir: Path, seed: int = 42
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing training output: {output_dir}")
    torch.manual_seed(seed)
    torch.set_num_threads(min(4, torch.get_num_threads()))
    manifest, fit_rows = read_weak_fit_rows(dataset_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    weights = EfficientNet_B0_Weights.DEFAULT
    backbone_model = efficientnet_b0(weights=weights)
    transform = weights.transforms()
    backbone = nn.Sequential(backbone_model.features, backbone_model.avgpool).to(device)
    backbone.requires_grad_(False)
    train_features = make_features(fit_rows, dataset_dir, backbone, transform, device)
    labels = torch.tensor(
        [1.0 if row["training_label"] == "candidate_well_symbol" else 0.0 for row in fit_rows],
        dtype=torch.float32,
    )
    raw_weights = torch.tensor([float(row["label_weight"]) for row in fit_rows])
    sample_weights = raw_weights / raw_weights.mean()

    probe = nn.Linear(train_features.shape[1], 1)
    nn.init.zeros_(probe.weight)
    nn.init.zeros_(probe.bias)
    optimizer = torch.optim.LBFGS(
        probe.parameters(), lr=0.5, max_iter=250, line_search_fn="strong_wolfe"
    )
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    def closure() -> torch.Tensor:
        optimizer.zero_grad()
        logits = probe(train_features).squeeze(1)
        data_loss = (loss_fn(logits, labels) * sample_weights).mean()
        regularization = 0.01 * probe.weight.square().sum() / 2.0
        loss = data_loss + regularization
        loss.backward()
        return loss

    optimizer.step(closure)
    with torch.inference_mode():
        logits = probe(train_features).squeeze(1)
        weighted_loss = float((loss_fn(logits, labels) * sample_weights).mean().item())
        fit_predictions = logits >= 0
        weighted_accuracy = float(
            ((fit_predictions == labels.bool()).float() * sample_weights).sum().item()
            / sample_weights.sum().item()
        )

    # Reuse fitted embeddings; extract only rows previously excluded as
    # uncertain or out-of-frame to create a review-priority queue.
    audit_rows = read_csv(dataset_dir / "reviewed_examples.csv")
    expected_audit_hash = manifest.get("output_hashes", {}).get("reviewed_examples_csv_sha256")
    if not isinstance(expected_audit_hash, str) or file_sha256(dataset_dir / "reviewed_examples.csv") != expected_audit_hash:
        raise ValueError("Candidate audit CSV differs from the dataset manifest")
    uncertain_rows = [
        row
        for row in audit_rows
        if row["review_status"] in {"ai_screen_uncertain", "uncertain"}
    ]
    negative_path = dataset_dir / "negative_review_examples.csv"
    expected_negative_hash = manifest.get("output_hashes", {}).get("negative_review_examples_csv_sha256")
    if not isinstance(expected_negative_hash, str) or file_sha256(negative_path) != expected_negative_hash:
        raise ValueError("Spatial review CSV differs from the dataset manifest")
    negative_rows = read_csv(negative_path)
    uncertain_rows.extend(row for row in negative_rows if row["review_status"] == "uncertain")
    uncertain_features = make_features(uncertain_rows, dataset_dir, backbone, transform, device)
    with torch.inference_mode():
        scores = torch.sigmoid(probe(uncertain_features).squeeze(1)).tolist()

    output_dir.mkdir(parents=True)
    checkpoint_path = output_dir / "efficientnet_b0_embedding_ranker.pt"
    torch.save(
        {
            "schema_version": 1,
            "backbone": "torchvision.efficientnet_b0",
            "backbone_weights": weights.name,
            "backbone_state_dict": backbone.state_dict(),
            "probe_state_dict": probe.state_dict(),
            "input_size": [224, 224],
            "output_semantics": "uncalibrated rank score; not probability or well verification",
        },
        checkpoint_path,
    )
    queue_path = output_dir / "uncertain_crop_priority.csv"
    ranked = sorted(zip(uncertain_rows, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    queue_fields = [
        "priority_rank",
        "sample_id",
        "candidate_id",
        "source_id",
        "sheet",
        "county",
        "source_review_status",
        "uncalibrated_symbol_rank_score",
        "crop_path",
        "crop_sha256",
    ]
    with queue_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=queue_fields)
        writer.writeheader()
        for rank, (row, score) in enumerate(ranked, start=1):
            writer.writerow(
                {
                    "priority_rank": rank,
                    "sample_id": row.get("sample_id", ""),
                    "candidate_id": row.get("candidate_id", ""),
                    "source_id": row["source_id"],
                    "sheet": row["sheet"],
                    "county": row["county"],
                    "source_review_status": row["review_status"],
                    "uncalibrated_symbol_rank_score": f"{score:.8f}",
                    "crop_path": row["crop_path"],
                    "crop_sha256": row["crop_sha256"],
                }
            )

    class_counts = Counter(row["training_label"] for row in fit_rows)
    provenance_counts = Counter(row["label_provenance"] for row in fit_rows)
    record = {
        "schema_version": 1,
        "training_scope": "frozen_imagenet_embedding_weighted_linear_probe_fit_only",
        "dataset_id": manifest["dataset_id"],
        "dataset_manifest_sha256": file_sha256(dataset_dir / "dataset_manifest.json"),
        "fit_table_sha256": file_sha256(dataset_dir / "weak_supervision_training_examples.csv"),
        "checkpoint_sha256": file_sha256(checkpoint_path),
        "uncertain_priority_csv_sha256": file_sha256(queue_path),
        "fit_example_count": len(fit_rows),
        "fit_class_counts": dict(sorted(class_counts.items())),
        "fit_provenance_counts": dict(sorted(provenance_counts.items())),
        "weighted_in_sample_loss": weighted_loss,
        "weighted_in_sample_accuracy": weighted_accuracy,
        "uncertain_priority_count": len(uncertain_rows),
        "backbone": "EfficientNet-B0 ImageNet1K_V1, frozen",
        "probe": "L2-regularized logistic linear probe on 1280-dimensional pooled embeddings",
        "sample_weights": manifest["weak_supervision"]["sample_weights"],
        "training_device": str(device),
        "seed": seed,
        "validation_metrics": None,
        "evaluation_ready": False,
        "deployment_ready": False,
        "limitations": [
            "Training targets include weak AI labels and a sparse single-reviewer set.",
            "In-sample weighted measures are not estimates of generalization.",
            "Priority scores are uncalibrated and must not be described as probabilities.",
            "The ranker identifies visual resemblance to its fit labels; it does not confirm a physical well.",
        ],
    }
    (output_dir / "ranker_run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {"model_path": str(checkpoint_path), "priority_queue_path": str(queue_path), **record}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(train_embedding_ranker(dataset_dir=args.dataset_dir, output_dir=args.output_dir, seed=args.seed), indent=2))


if __name__ == "__main__":
    main()
