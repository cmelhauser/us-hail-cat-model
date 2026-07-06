"""
_pipeline_cleanup.py — Remove generated pipeline outputs from a given stage onward.

Used by ``run_pipeline.py --clean-from`` and ``scripts/rerun_stage05.py``.
Preserves calibration artifacts (``data/analysis/calibration/``) and topography
source inputs (``data/analysis/topography/``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

try:
    from _config import (
        ANALYSIS,
        CDF_DIR,
        DATA_ROOT,
        DOCS_FIG,
        EVENTS_DIR,
        HISTORICAL,
        LOG_ROOT,
        MASK_DIR,
        MESH_CLIMO_DIR,
        MESH_CORR_DIR,
        OCC_DIR,
        REPO_ROOT,
        STOCHASTIC,
    )
except ImportError:  # pragma: no cover
    from scripts._config import (
        ANALYSIS,
        CDF_DIR,
        DATA_ROOT,
        DOCS_FIG,
        EVENTS_DIR,
        HISTORICAL,
        LOG_ROOT,
        MASK_DIR,
        MESH_CLIMO_DIR,
        MESH_CORR_DIR,
        OCC_DIR,
        REPO_ROOT,
        STOCHASTIC,
    )

# Ordered stage IDs for ``clean_from_stage`` slicing.
STAGE_ORDER: tuple[str, ...] = (
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "11b",
    "12",
    "13",
    "14",
)

# Paths removed when cleaning from the given stage (inclusive).
STAGE_OUTPUT_PATHS: dict[str, tuple[Path, ...]] = {
    "05": (MESH_CORR_DIR,),
    "06": (
        HISTORICAL / "validation",
        DOCS_FIG / "analysis",
    ),
    "07": (MESH_CLIMO_DIR,),
    "08": (EVENTS_DIR,),
    "09": (CDF_DIR,),
    "10": (),  # writes into CDF_DIR (cleared at 09)
    "11": (OCC_DIR,),
    "11b": (),  # topography source is retained under ANALYSIS/topography/source
    "12": (MASK_DIR,),
    "13": (
        STOCHASTIC,
        DOCS_FIG / "stochastic",
    ),
    "14": (
        DOCS_FIG / "historical",
    ),
}

# Optional diagnostics tied to Stage 05+ QA (not upstream ingest).
STAGE05_PLUS_DIAGNOSTICS: tuple[Path, ...] = (
    ANALYSIS / "radar_artifacts",
    ANALYSIS / "hail_day_climatology",
)

STAGE05_LOCK = LOG_ROOT / "stage05.lock"
STAGE05_PID = LOG_ROOT / "stage05.pid"


def paths_from_stage(stage_id: str, *, include_diagnostics: bool = True) -> list[Path]:
    """Return unique output paths to remove from ``stage_id`` through stage 14."""
    if stage_id not in STAGE_ORDER:
        raise ValueError(f"Unknown stage {stage_id!r}; expected one of {STAGE_ORDER}")
    start = STAGE_ORDER.index(stage_id)
    out: list[Path] = []
    for sid in STAGE_ORDER[start:]:
        out.extend(STAGE_OUTPUT_PATHS.get(sid, ()))
    if include_diagnostics and stage_id == "05":
        out.extend(STAGE05_PLUS_DIAGNOSTICS)
    # Preserve order, drop duplicates.
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def clean_from_stage(stage_id: str, *, dry_run: bool = False, include_diagnostics: bool = True) -> list[Path]:
    """Delete all generated outputs from ``stage_id`` onward. Returns removed paths."""
    removed: list[Path] = []
    for path in paths_from_stage(stage_id, include_diagnostics=include_diagnostics):
        if not path.exists():
            continue
        if dry_run:
            removed.append(path)
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path)
    return removed
