"""
_logging.py — Shared logging configuration for all pipeline stages.

Replaces the per-stage `log()` helper (print + manual file append) with a
properly configured Python `logging` setup that supports:

  - Level filtering (DEBUG / INFO / WARNING / ERROR / CRITICAL)
  - Structured timestamps
  - Simultaneous stderr + rotating file output
  - A single configuration call per stage

Usage in stage scripts:
    from _logging import get_logger
    from _config import LOG_ROOT

    log = get_logger("05_apply_mesh_bias_correction", LOG_ROOT)
    log.info("Processing year %d", year)
    log.warning("Fewer than %d exceedances in region %d", MIN_OBS, reg)
    log.error("Missing file: %s", path)

Migration note (v2.1 → v2.2):
    During the v2.1 run period, stage scripts still use print-based log().
    When each stage is next touched, replace:

        def log(msg):
            line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
            print(line, flush=True)
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a") as f:
                f.write(line + "\\n")

    With:

        from _logging import get_logger
        from _config import LOG_ROOT
        _log = get_logger("NN_stage_name", LOG_ROOT)
        log = _log.info   # drop-in replacement for call sites using log(msg)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(
    stage_name: str,
    log_dir: Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configure and return a stage-level logger.

    Calling this function multiple times with the same ``stage_name`` returns
    the same logger object without re-adding handlers (idempotent).

    Parameters
    ----------
    stage_name:
        Identifier for the stage, e.g. ``"05_apply_mesh_bias_correction"``.
        Used as the logger name and the log file stem.
    log_dir:
        Directory for the log file. If *None*, only stderr is used.
        The directory is created on first write if it does not exist.
    level:
        Logging level. Defaults to ``logging.INFO``. Set to
        ``logging.DEBUG`` for verbose diagnostics.

    Returns
    -------
    logging.Logger
        Configured logger. Typical usage: ``log = get_logger(...).info``
        for a drop-in replacement of the legacy ``log()`` helper.
    """
    logger = logging.getLogger(stage_name)

    if logger.handlers:
        # Already configured — return as-is (idempotent)
        return logger

    logger.setLevel(level)

    # --- stderr handler ---
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(_FORMATTER)
    logger.addHandler(stderr_handler)

    # --- file handler ---
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{stage_name}.log"
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(_FORMATTER)
        logger.addHandler(file_handler)

    # Prevent log records from propagating to the root logger
    logger.propagate = False

    return logger


def get_pipeline_logger(log_dir: Path | None = None) -> logging.Logger:
    """Convenience wrapper for the top-level run_pipeline logger."""
    return get_logger("run_pipeline", log_dir=log_dir)


__all__ = ["get_logger", "get_pipeline_logger"]
