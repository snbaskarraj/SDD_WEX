"""Repository paths. Override the parquet directory with FLEETLINE_DATA_DIR."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_PATH = ROOT / "semantic" / "metrics.yaml"


def data_dir() -> Path:
    override = os.environ.get("FLEETLINE_DATA_DIR")
    if override:
        return Path(override)
    return ROOT / "data"
