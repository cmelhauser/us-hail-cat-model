"""Coverage for scripts/_logging.py."""

from __future__ import annotations

from scripts._logging import get_logger, get_pipeline_logger


def test_get_pipeline_logger(tmp_path):
    log = get_pipeline_logger(tmp_path)
    assert log.name == "run_pipeline"
    log.info("hello")
    # idempotent
    assert get_pipeline_logger(tmp_path) is log
