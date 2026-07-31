"""GridRad (Stage 04c) one-day-per-task fan-out helpers.

Dates and CLI flags must stay aligned with ``scripts/04c_fill_gridrad_gap.py``.
Staging for each day lives on EFS under ``data/`` (~8–12 GiB peak); Fargate
ephemeral storage is not the GridRad scratch volume.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from collections.abc import Iterable

# Mirror scripts/04c_fill_gridrad_gap.py GAP_START / GAP_END.
GRIDRAD_GAP_START = date(2012, 1, 1)
GRIDRAD_GAP_END = date(2020, 10, 13)

HAIL_CONTAINER_NAME = "hail"


def parse_iso_date(value: str) -> date:
    """Parse YYYY-MM-DD into a ``date``."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_convective_days(start: date, end: date) -> list[date]:
    """Inclusive convective-day range (calendar dates used as day labels)."""
    if end < start:
        return []
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def resolve_gap_window(
    *,
    from_date: date | None = None,
    until_date: date | None = None,
) -> tuple[date, date]:
    """Clamp an optional window to the GridRad gap [GAP_START, GAP_END]."""
    start = from_date or GRIDRAD_GAP_START
    end = until_date or GRIDRAD_GAP_END
    start = max(start, GRIDRAD_GAP_START)
    end = min(end, GRIDRAD_GAP_END)
    if end < start:
        raise ValueError(
            f"GridRad window empty after clamp: from={from_date} until={until_date} "
            f"(gap {GRIDRAD_GAP_START} → {GRIDRAD_GAP_END})"
        )
    return start, end


def day_task_name(day: date) -> str:
    """Stable ECS startedBy / outcome label for one convective day."""
    return f"download_gridrad_{day.strftime('%Y%m%d')}"


@dataclass(frozen=True)
class GridradDayCommand:
    """Command array for one Stage 04c Fargate task (python entrypoint)."""

    day: date
    argv: list[str]

    @property
    def task_name(self) -> str:
        return day_task_name(self.day)


def build_day_command(
    day: date,
    *,
    with_04b_download: bool = True,
    workers: int = 1,
    download_workers: int = 1,
    missing_only: bool = True,
) -> GridradDayCommand:
    """Build ``scripts/04c_fill_gridrad_gap.py`` argv for a single day."""
    ymd = day.isoformat()
    argv = [
        "scripts/04c_fill_gridrad_gap.py",
        "--workers",
        str(max(1, workers)),
        "--04b-download-workers",
        str(max(1, download_workers)),
        "--from-date",
        ymd,
        "--until-date",
        ymd,
    ]
    if with_04b_download:
        argv.append("--with-04b-download")
    if missing_only:
        argv.append("--missing-only")
    return GridradDayCommand(day=day, argv=argv)


def build_manifest_rebuild_command() -> list[str]:
    """Post-fan-out command: rebuild 04c manifest + ``gridrad_days.txt``."""
    return ["scripts/04c_fill_gridrad_gap.py", "--manifest-only"]


def plan_day_commands(
    days: Iterable[date],
    *,
    with_04b_download: bool = True,
    workers: int = 1,
    download_workers: int = 1,
    missing_only: bool = True,
) -> list[GridradDayCommand]:
    return [
        build_day_command(
            day,
            with_04b_download=with_04b_download,
            workers=workers,
            download_workers=download_workers,
            missing_only=missing_only,
        )
        for day in days
    ]
