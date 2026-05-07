#!/usr/bin/env python3
"""
04b_fill_gridrad_gap.py — Deprecated wrapper (use Stage 04c)
============================================================
This script used to be the GridRad gap-fill compute stage.

Stage numbering was updated:
- **04b**: `scripts/04b_download_gridrad.py` (download GridRad inputs)
- **04c**: `scripts/04c_fill_gridrad_gap.py` (compute SHI → MESH75 gap-fill)

This file remains only for backward compatibility and delegates to Stage 04c.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_TARGET = Path(__file__).with_name("04c_fill_gridrad_gap.py")


def main(argv: list[str] | None = None) -> None:
    spec = importlib.util.spec_from_file_location("stage04c_fill_gridrad_gap", _TARGET)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.main(argv)


if __name__ == "__main__":
    main()

