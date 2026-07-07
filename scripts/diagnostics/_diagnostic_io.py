"""
_diagnostic_io.py — shared data-availability helpers for diagnostic scripts.

All optional diagnostics should warn and skip (not crash) when inputs are absent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MESH_TIF_RE = re.compile(r"mesh_\d{8}\.tif$")


def warn_skip(step: str, reason: str) -> None:
    """Print a standard skip warning to stdout."""
    print(f"  WARNING: SKIP {step} — {reason}", flush=True)


def require_path(path: Path, step: str, *, kind: str = "file") -> bool:
    """Return False and warn if a required path is missing."""
    if kind == "file":
        ok = path.is_file()
        label = "file"
    elif kind == "dir":
        ok = path.is_dir()
        label = "directory"
    else:
        ok = path.exists()
        label = "path"
    if not ok:
        warn_skip(step, f"required {label} not found: {path}")
        return False
    return True


def count_mesh_tifs(mesh_dir: Path) -> int:
    """Count ``mesh_YYYYMMDD.tif`` under ``mesh_dir``."""
    if not mesh_dir.is_dir():
        return 0
    return sum(1 for p in mesh_dir.rglob("mesh_*.tif") if MESH_TIF_RE.search(p.name))


def require_mesh_tifs(mesh_dir: Path, step: str, *, min_count: int = 1) -> bool:
    """Return False and warn if fewer than ``min_count`` mesh TIFFs exist."""
    n = count_mesh_tifs(mesh_dir)
    if n < min_count:
        warn_skip(step, f"found {n} mesh TIFF(s) under {mesh_dir} (need ≥{min_count})")
        return False
    return True


def exit_if_missing(condition: bool, step: str, reason: str, *, code: int = 0) -> None:
    """Exit the process after warning when a required input is absent."""
    if not condition:
        warn_skip(step, reason)
        sys.exit(code)
