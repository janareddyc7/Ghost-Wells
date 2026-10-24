"""Create local, overlapping image chips for human map review."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def create_tiles(
    manifest_path: Path,
    data_dir: Path,
    output_dir: Path,
    *,
    scale: float = 2.5,
    tile_size: int = 512,
    overlap: int = 64,
) -> Path:
    """Render each GeoPDF into page-pixel chips and write a review manifest.

    Coordinates in the output refer only to pixels in the rendered PDF page;
    they are not ground coordinates. The collars are retained for provenance,
    but reviewers must label features only inside the map neatline.
    """
    try:
        import pymupdf
    except ImportError as error:
        raise RuntimeError("Tile generation requires PyMuPDF; install requirements-research.txt") from error

    if scale <= 0:
        raise ValueError("scale must be positive")
    if tile_size <= 0 or overlap < 0 or overlap >= tile_size:
        raise ValueError("tile_size must be positive and overlap must be smaller than tile_size")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sheets"), list):
        raise ValueError("Unsupported evidence manifest")

    output_dir.mkdir(parents=True, exist_ok=True)
    step = tile_size - overlap
    chips: list[dict[str, object]] = []
    for sheet in manifest["sheets"]:
        filename = sheet["local_file"]
        if Path(filename).name != filename or not filename.lower().endswith(".pdf"):
            raise ValueError(f"Unsafe local_file: {filename}")
        pdf_path = data_dir / filename
        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)
        document = pymupdf.open(pdf_path)
        if len(document) != 1:
            raise ValueError(f"Expected one-page map PDF: {filename}")
        page = document[0]
        width_px = round(page.rect.width * scale)
        height_px = round(page.rect.height * scale)
        for top in range(0, height_px, step):
            for left in range(0, width_px, step):
                chip_width = min(tile_size, width_px - left)
                chip_height = min(tile_size, height_px - top)
                rect = pymupdf.Rect(
                    left / scale,
                    top / scale,
                    (left + chip_width) / scale,
                    (top + chip_height) / scale,
                )
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale), clip=rect, alpha=False
                )
                scale_milli = round(scale * 1000)
                chip_name = f"{sheet['source_id']}__s{scale_milli:04d}__x{left:05d}_y{top:05d}.jpg"
                chip_path = output_dir / chip_name
                pixmap.save(chip_path, jpg_quality=90)
                chips.append(
                    {
                        "chip_id": chip_name.removesuffix(".jpg"),
                        "source_id": sheet["source_id"],
                        "quadrangle": sheet["name"],
                        "county": sheet["county"],
                        "edition_year": sheet["year"],
                        "source_file": filename,
                        "image_file": chip_name,
                        "page_pixel_origin": [left, top],
                        "image_size": [chip_width, chip_height],
                        "render_scale": scale,
                    }
                )
        document.close()

    tile_manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "coordinate_space": "rendered_page_pixels",
        "scale_pixels_per_pdf_point": scale,
        "tile_size_pixels": tile_size,
        "overlap_pixels": overlap,
        "review_guidance": "Mark map symbols only inside the map neatline; exclude collars, legends, marginal labels, and duplicate overlap marks.",
        "chips": chips,
    }
    target = output_dir / "tile_manifest.json"
    target.write_text(json.dumps(tile_manifest, indent=2) + "\n", encoding="utf-8")
    queue = {
        "schema_version": 1,
        "coordinate_space": "rendered_page_pixels",
        "status": "pending_human_review",
        "reviewed_chip_count": 0,
        "chip_count": len(chips),
        "chips": [
            {"chip_id": chip["chip_id"], "source_id": chip["source_id"], "status": "pending"}
            for chip in chips
        ],
        "note": "No symbols are inferred by this queue. Mark chips reviewed only after visual inspection.",
    }
    (output_dir / "review_queue.json").write_text(
        json.dumps(queue, indent=2) + "\n", encoding="utf-8"
    )
    return target
