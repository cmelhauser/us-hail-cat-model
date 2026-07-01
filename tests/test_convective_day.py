"""Unit tests for 12 UTC → 12 UTC convective-day helpers in scripts/_io.py."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from scripts._config import CONVECTIVE_DAY_START_HOUR_UTC, MODEL_VERSION
from scripts._io import (
    calendar_days_for_convective_day,
    convective_day_window_tag,
    convective_day_window_utc,
    filter_keys_for_convective_day,
    observation_in_convective_day,
    observation_utc_to_convective_day,
    parse_observation_utc_from_name,
)

UTC = timezone.utc


def test_model_version_and_convective_hour() -> None:
    assert MODEL_VERSION == "2.2.1"
    assert CONVECTIVE_DAY_START_HOUR_UTC == 12


@pytest.mark.parametrize(
    "obs, expected",
    [
        (datetime(2016, 7, 21, 8, 0, tzinfo=UTC), date(2016, 7, 20)),
        (datetime(2016, 7, 21, 12, 0, tzinfo=UTC), date(2016, 7, 21)),
        (datetime(2016, 7, 22, 11, 59, tzinfo=UTC), date(2016, 7, 21)),
        (datetime(2016, 7, 22, 12, 0, tzinfo=UTC), date(2016, 7, 22)),
    ],
)
def test_observation_utc_to_convective_day(obs: datetime, expected: date) -> None:
    assert observation_utc_to_convective_day(obs) == expected


def test_convective_day_window_bounds() -> None:
    start, end = convective_day_window_utc(date(2016, 7, 21))
    assert start == datetime(2016, 7, 21, 12, 0, tzinfo=UTC)
    assert end == datetime(2016, 7, 22, 12, 0, tzinfo=UTC)
    assert observation_in_convective_day(start, date(2016, 7, 21))
    assert not observation_in_convective_day(end, date(2016, 7, 21))


def test_calendar_days_for_convective_day() -> None:
    assert calendar_days_for_convective_day(date(2016, 7, 21)) == (
        date(2016, 7, 21),
        date(2016, 7, 22),
    )


def test_parse_observation_utc_from_name_formats() -> None:
    assert parse_observation_utc_from_name("nexrad_3d_v4_2_20160721T153000Z.nc") == datetime(
        2016, 7, 21, 15, 30, tzinfo=UTC
    )
    assert parse_observation_utc_from_name("20160721-153000.netcdf") == datetime(
        2016, 7, 21, 15, 30, tzinfo=UTC
    )
    assert parse_observation_utc_from_name(
        "MRMS_MESH_00.50_20160721-153000.grib2.gz"
    ) == datetime(2016, 7, 21, 15, 30, tzinfo=UTC)


def test_filter_keys_for_convective_day() -> None:
    keys = [
        "20160721/MESH/00.25/20160721-110000.netcdf",
        "20160721/MESH/00.25/20160721-130000.netcdf",
        "20160722/MESH/00.25/20160722-110000.netcdf",
    ]
    out = filter_keys_for_convective_day(keys, date(2016, 7, 21))
    assert len(out) == 2
    assert keys[1] in out
    assert keys[2] in out


def test_convective_day_window_tag() -> None:
    tag = convective_day_window_tag(date(2016, 7, 21))
    assert "2016-07-21T12:00:00+00:00" in tag
    assert "2016-07-22T12:00:00+00:00" in tag
