"""Tests for hail_aws.gridrad_fanout."""

from __future__ import annotations

from datetime import date

import pytest

from hail_aws.gridrad_fanout import (
    GRIDRAD_GAP_END,
    GRIDRAD_GAP_START,
    build_day_command,
    build_manifest_rebuild_command,
    day_task_name,
    iter_convective_days,
    plan_day_commands,
    resolve_gap_window,
)


def test_iter_and_resolve_window() -> None:
    assert iter_convective_days(date(2015, 5, 20), date(2015, 5, 19)) == []
    days = iter_convective_days(date(2015, 5, 20), date(2015, 5, 21))
    assert days == [date(2015, 5, 20), date(2015, 5, 21)]
    start, end = resolve_gap_window()
    assert start == GRIDRAD_GAP_START and end == GRIDRAD_GAP_END
    start, end = resolve_gap_window(
        from_date=date(2015, 1, 1), until_date=date(2015, 1, 2)
    )
    assert start == date(2015, 1, 1) and end == date(2015, 1, 2)


def test_resolve_empty_window() -> None:
    with pytest.raises(ValueError, match="empty"):
        resolve_gap_window(from_date=date(2020, 10, 13), until_date=date(2012, 1, 1))


def test_build_commands() -> None:
    cmd = build_day_command(date(2015, 5, 20))
    assert cmd.task_name == day_task_name(date(2015, 5, 20))
    assert cmd.argv[0] == "scripts/04c_fill_gridrad_gap.py"
    assert "--with-04b-download" in cmd.argv
    assert "--missing-only" in cmd.argv
    assert "--from-date" in cmd.argv
    bare = build_day_command(
        date(2015, 5, 20),
        with_04b_download=False,
        missing_only=False,
    )
    assert "--with-04b-download" not in bare.argv
    assert "--missing-only" not in bare.argv
    assert build_manifest_rebuild_command() == [
        "scripts/04c_fill_gridrad_gap.py",
        "--manifest-only",
    ]
    planned = plan_day_commands([date(2015, 5, 20), date(2015, 5, 21)])
    assert len(planned) == 2
