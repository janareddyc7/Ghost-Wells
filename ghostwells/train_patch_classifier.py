"""Fit an exploratory candidate-patch classifier from reviewed private crops.

This runner intentionally creates no validation split and reports no evaluation
metrics. Evaluation must use complete, held-out map sheets through
``ghostwells.evaluate_detector``.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ghostwells.build_dataset import file_sha256
from ghostwells.validation import load_split_plan


LABEL_TO_INT = {"candidate_well_symbol": 1, "candidate_lookalike": 0}


def read_fit_rows(dataset_dir: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Validate the fit-only CSV, image hashes, and dataset readiness gate."""
    manifest_path = dataset_dir / "dataset_manifest.json"
    examples_path = dataset_dir / "independent_training_examples.csv"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("training_ready") is not True or manifest.get("status") != "exploratory_fit_ready":
        raise ValueError("Dataset is not marked exploratory_fit_ready after blind human review")
    if manifest.get("evaluation_ready") is not False:
        raise ValueError("Fit-only dataset must explicitly keep evaluation_ready false")
    expected_csv_hash = manifest.get("output_hashes", {}).get(
        "independent_training_examples_csv_sha256"
    )
    if not isinstance(expected_csv_hash, str) or file_sha256(examples_path) != expected_csv_hash:
        raise ValueError("Independent training CSV is missing or differs from its manifest hash")

    with examples_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("No independently reviewed fit examples are available")

    counts: Counter[str] = Counter()
    for row in rows:
        label = row.get("training_label", "")
        if label not in LABEL_TO_INT:
            raise ValueError(f"Unsupported fit label: {label}")
        if row.get("training_eligible", "").lower() != "true":
            raise ValueError("Training CSV contains a row not marked training_eligible")
        if row.get("evaluation_use") != "prohibited":
            raise ValueError("Training CSV does not prohibit evaluation use")
        if row.get("label_provenance") != "independent_blind_human_review":
            raise ValueError("Fit label is not from the recorded blind human review")
        relative = Path(row.get("crop_path", ""))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("Unsafe crop path in independent training CSV")
        crop_path = (dataset_dir / relative).resolve()
        if not crop_path.is_relative_to(dataset_dir.resolve()) or not crop_path.is_file():
            raise ValueError(f"Training crop is missing or escapes dataset directory: {relative}")
        if file_sha256(crop_path) != row.get("crop_sha256"):
            raise ValueError(f"Training crop hash mismatch: {row.get('sample_id')}")
        counts[label] += 1
    if set(counts) != set(LABEL_TO_INT):
        raise ValueError("Fit-only training requires both clear symbol and lookalike classes")
    return manifest, rows


def train_patch_classifier(
    *,
    dataset_dir: Path,
    split_plan_path: Path,
    source_manifest_path: Path,
    output_dir: Path,
    epochs: int = 20,
    batch_size: int = 32,
    seed: int = 42,
) -> dict[str, Any]:
    """Train on whole-county fit rows; do not create validation metrics."""
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing training output: {output_dir}")
    if epochs < 1 or batch_size < 1:
        raise ValueError("epochs and batch_size must be positive")
    manifest, all_rows = read_fit_rows(dataset_dir)
    split_plan = load_split_plan(
        split_plan_path, source_manifest_path, require_blind_review=False
    )
    training_ids = set(split_plan["training_source_ids"])
    rows = [row for row in all_rows if row["source_id"] in training_ids]
    if not rows:
        raise ValueError("No reviewed fit examples belong to the training counties")
    counts: Counter[str] = Counter()
    for row in rows:
        label = row.get("training_label", "")
        counts[label] += 1
    if set(counts) != set(LABEL_TO_INT):
        raise ValueError("Fit-only training requires both clear symbol and lookalike classes")
    if min(counts.values()) < 2:
        raise ValueError("Fit-only training requires at least two examples in each class")

    try:
        import tensorflow as tf
    except ImportError as error:
        raise RuntimeError("Training requires TensorFlow; install requirements-training.txt") from error

    tf.keras.utils.set_random_seed(seed)
    try:
        tf.config.experimental.enable_op_determinism()
    except (AttributeError, RuntimeError):
        pass

    paths = [str((dataset_dir / row["crop_path"]).resolve()) for row in rows]
    labels = [LABEL_TO_INT[row["training_label"]] for row in rows]
    image_size = int(manifest.get("crop_size_pixels", 256))
    dataset = tf.data.Dataset.from_tensor_slices((paths, labels))

    def load_image(path: Any, label: Any) -> tuple[Any, Any]:
        image = tf.io.decode_png(tf.io.read_file(path), channels=3)
        image = tf.image.resize(image, (image_size, image_size))
        image = tf.cast(image, tf.float32) / 255.0
        return image, tf.cast(label, tf.float32)

    dataset = (
        dataset.shuffle(len(rows), seed=seed, reshuffle_each_iteration=True)
        .map(load_image, num_parallel_calls=tf.data.AUTOTUNE)
        .batch(batch_size)
        .prefetch(tf.data.AUTOTUNE)
    )

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input((image_size, image_size, 3)),
            tf.keras.layers.Conv2D(32, 5, strides=2, padding="same", activation="relu"),
            tf.keras.layers.MaxPooling2D(),
            tf.keras.layers.Conv2D(64, 3, padding="same", activation="relu"),
            tf.keras.layers.MaxPooling2D(),
            tf.keras.layers.Conv2D(128, 3, padding="same", activation="relu"),
            tf.keras.layers.GlobalAveragePooling2D(),
            tf.keras.layers.Dropout(0.25),
            tf.keras.layers.Dense(1),
        ],
        name="ghost_wells_candidate_patch_classifier",
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss=tf.keras.losses.BinaryCrossentropy(from_logits=True),
        metrics=[tf.keras.metrics.BinaryAccuracy(name="in_sample_accuracy", threshold=0.0)],
    )
    history = model.fit(dataset, epochs=epochs, verbose=2)

    output_dir.mkdir(parents=True)
    model_path = output_dir / "candidate_patch_classifier.keras"
    model.save(model_path)
    counts = dict(sorted(Counter(row["training_label"] for row in rows).items()))
    training_record = {
        "schema_version": 1,
        "training_scope": "exploratory_candidate_patch_classifier_fit_only",
        "dataset_id": manifest["dataset_id"],
        "dataset_manifest_sha256": file_sha256(dataset_dir / "dataset_manifest.json"),
        "training_csv_sha256": file_sha256(dataset_dir / "independent_training_examples.csv"),
        "fit_example_count": len(rows),
        "fit_class_counts": counts,
        "fit_source_ids": sorted({row["source_id"] for row in rows}),
        "evaluation_source_ids_excluded_from_fit": split_plan["evaluation_source_ids"],
        "split_plan_sha256": file_sha256(split_plan_path),
        "model_sha256": file_sha256(model_path),
        "architecture": "small convolutional binary classifier; 256px RGB input",
        "optimizer": "Adam",
        "learning_rate": 1e-3,
        "epochs": epochs,
        "batch_size": batch_size,
        "seed": seed,
        "training_history_in_sample_only": {
            key: [float(value) for value in values]
            for key, values in history.history.items()
        },
        "validation_metrics": None,
        "evaluation_ready": False,
        "limitations": [
            "Fit-only experiment on a model-selected candidate sample; not a full-sheet detector.",
            "In-sample training history is not an estimate of generalization.",
            "Use complete, untouched map sheets for any detector evaluation.",
            "A map-symbol label does not verify a physical well or current field condition.",
        ],
    }
    record_path = output_dir / "training_run.json"
    record_path.write_text(json.dumps(training_record, indent=2) + "\n", encoding="utf-8")
    return {"model_path": str(model_path), "record_path": str(record_path), **training_record}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--split-plan", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, default=Path("evidence/pilot_sheets.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(
        json.dumps(
            train_patch_classifier(
                dataset_dir=args.dataset_dir,
                split_plan_path=args.split_plan,
                source_manifest_path=args.source_manifest,
                output_dir=args.output_dir,
                epochs=args.epochs,
                batch_size=args.batch_size,
                seed=args.seed,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
