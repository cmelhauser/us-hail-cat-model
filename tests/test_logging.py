"""Tests for scripts/_logging.py."""

from __future__ import annotations

from pathlib import Path

from scripts._logging import get_logger, get_pipeline_logger


def test_get_pipeline_logger(tmp_path: Path):
    logger = get_pipeline_logger(tmp_path)
    assert logger.name == "run_pipeline"
    logger.info("pipeline test message")
    log_file = tmp_path / "run_pipeline.log"
    assert log_file.is_file()


def test_get_logger_reuses_handlers(tmp_path: Path):
    a = get_logger("stage_test_once", tmp_path)
    b = get_logger("stage_test_once", tmp_path)
    assert a is b
