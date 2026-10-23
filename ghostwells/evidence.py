"""Validate downloaded source scans against the committed evidence manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def verify_files(manifest_path: Path, data_dir: Path) -> list[str]:
    """Return one error per missing or changed source file; no network access."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sheets"), list):
        raise ValueError("Unsupported evidence manifest")
    errors: list[str] = []
    for sheet in manifest["sheets"]:
        filename = sheet["local_file"]
        if Path(filename).name != filename or not filename.lower().endswith(".pdf"):
            raise ValueError(f"Unsafe local_file: {filename}")
        path = data_dir / filename
        if not path.is_file():
            errors.append(f"Missing: {filename}")
            continue
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != sheet["sha256"].lower():
            errors.append(f"SHA-256 mismatch: {filename}")
    return errors
