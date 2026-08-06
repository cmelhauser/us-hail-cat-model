"""Tests for hail_aws.gridrad_fanout."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

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


def _stage04c_gap_dates() -> dict[str, date]:
    """Read numeric stage constants without importing the executable script."""
    stage_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "04c_fill_gridrad_gap.py"
    )
    tree = ast.parse(stage_path.read_text())
    dates = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if (
            isinstance(target, ast.Name)
            and target.id in {"GAP_START", "GAP_END"}
            and isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "date"
        ):
            dates[target.id] = date(
                *(ast.literal_eval(arg) for arg in value.args)
            )
    return dates


def test_aws_gap_dates_match_stage04c() -> None:
    stage_dates = _stage04c_gap_dates()
    assert stage_dates == {
        "GAP_START": GRIDRAD_GAP_START,
        "GAP_END": GRIDRAD_GAP_END,
    }


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
