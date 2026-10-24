"""Run the published historical-map U-Net and emit unreviewed candidates."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import ndimage


def _image_array(page: object, scale: float) -> np.ndarray:
    import pymupdf

    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )[:, :, :3]


def _predict_page(model: object, image: np.ndarray, threshold: float, batch_size: int) -> np.ndarray:
    import tensorflow as tf

    height, width = image.shape[:2]
    size = 256
    stride = 231  # 25-pixel overlap, matching the published inference notebook.
    positions = [
        (top, left)
        for top in range(0, height, stride)
        for left in range(0, width, stride)
    ]
    mask = np.zeros((height, width), dtype=np.uint8)
    for start in range(0, len(positions), batch_size):
        batch_positions = positions[start : start + batch_size]
        batch = np.full((len(batch_positions), size, size, 3), 255, dtype=np.uint8)
        for index, (top, left) in enumerate(batch_positions):
            crop = image[top : top + size, left : left + size]
            batch[index, : crop.shape[0], : crop.shape[1]] = crop
        inputs = tf.keras.applications.resnet.preprocess_input(batch.astype(np.float32))
        predictions = model.predict(inputs, verbose=0)
        for prediction, (top, left) in zip(predictions, batch_positions, strict=True):
            binary = prediction[:, :, 0] >= threshold
            end_y = min(top + size, height)
            end_x = min(left + size, width)
            mask[top:end_y, left:end_x] |= binary[: end_y - top, : end_x - left]
    return mask


def detect_candidates(
    manifest_path: Path,
    data_dir: Path,
    model_path: Path,
    output_path: Path,
    *,
    scale: float = 4.1666667,
    threshold: float = 0.5,
    min_area: int = 45,
    batch_size: int = 8,
    sheet_ids: set[str] | None = None,
) -> dict[str, object]:
    """Detect pixel-mask components. Output is model candidates, not confirmed wells."""
    import pymupdf
    import tensorflow as tf

    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    if not 0 < threshold < 1 or min_area < 1 or batch_size < 1:
        raise ValueError("threshold must be between 0 and 1; area and batch size must be positive")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sheets"), list):
        raise ValueError("Unsupported evidence manifest")

    digest = hashlib.sha256()
    with model_path.open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(block)
    model_hash = digest.hexdigest()
    model = tf.keras.models.load_model(model_path, compile=False)
    result: dict[str, object] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "partial_inference",
        "model_source": "Ciulla et al. (2024), DOE/NETL EDX DOI 10.18141/2452768",
        "model_sha256": model_hash,
        "render_scale_pixels_per_pdf_point": scale,
        "render_dpi": scale * 72,
        "patch_size_pixels": 256,
        "patch_overlap_pixels": 25,
        "probability_threshold": threshold,
        "minimum_component_area_pixels": min_area,
        "coordinate_space": "rendered_page_pixels",
        "sheets": [],
        "note": "Model outputs are candidate symbols only. They are not complete annotations, confirmed wells, or georeferenced locations; Ohio performance has not been validated.",
    }
    sheets = result["sheets"]
    for sheet in manifest["sheets"]:
        if sheet_ids and sheet["source_id"] not in sheet_ids:
            continue
        pdf_name = sheet["local_file"]
        if Path(pdf_name).name != pdf_name:
            raise ValueError(f"Unsafe local_file: {pdf_name}")
        document = pymupdf.open(data_dir / pdf_name)
        if len(document) != 1:
            raise ValueError(f"Expected one-page map PDF: {pdf_name}")
        image = _image_array(document[0], scale)
        mask = _predict_page(model, image, threshold, batch_size)
        labels, count = ndimage.label(mask, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
        objects = ndimage.find_objects(labels, max_label=count)
        candidates: list[dict[str, int]] = []
        for label_id, region in enumerate(objects, start=1):
            if region is None:
                continue
            component = labels[region] == label_id
            area = int(component.sum())
            if area < min_area:
                continue
            local_y, local_x = ndimage.center_of_mass(component)
            candidates.append(
                {
                    "page_x": int(round(region[1].start + local_x)),
                    "page_y": int(round(region[0].start + local_y)),
                    "mask_area_pixels": area,
                }
            )
        sheet_result = (
            {
                "source_id": sheet["source_id"],
                "sheet": sheet["name"],
                "county": sheet["county"],
                "edition_year": sheet["year"],
                "source_sha256": sheet["sha256"],
                "page_size_pixels": [int(image.shape[1]), int(image.shape[0])],
                "candidates": candidates,
            }
        )
        sheets.append(sheet_result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"{sheet['name']}: {len(candidates)} unreviewed candidates", flush=True)
        document.close()

    result["status"] = "unreviewed_model_candidates"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
