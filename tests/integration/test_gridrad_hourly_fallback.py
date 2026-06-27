"""
Integration: GridRad V4.2 hourly fallback (d841001) through 04b download → 04c discovery.

Exercises the severe-first adaptive download path and staged-file discovery without
real THREDDS/NetCDF I/O.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.integration


def _fake_catalog_session(b04, *, v31_xml: str, v42_xml: str):
    """Return a session mock that serves empty V3.1 and populated V4.2 month catalogs."""

    class Resp:
        status_code = 200

        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, url, timeout=60, stream=False):
            if b04.DS_HOURLY in url:
                return Resp(v31_xml)
            if b04.DS_HOURLY_V42 in url:
                return Resp(v42_xml)
            if "d841006" in url:
                return Resp("<?xml version='1.0'?><catalog xmlns='http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0'/>")
            raise AssertionError(f"unexpected catalog url: {url}")

        def close(self):
            return None

    return FakeSession()


def test_adaptive_download_stages_v42_then_04c_discovers_hourly_v42(
    load_script, tmp_path, monkeypatch
):
    """04b adaptive (no severe) → staged d841001 files → 04c gridrad-hourly-v42."""
    b04 = load_script("04b_download_gridrad.py")
    c04 = load_script("04c_fill_gridrad_gap.py")

    hr_base = tmp_path / "gridrad"
    sev_base = tmp_path / "gridrad_severe"
    monkeypatch.setattr(b04, "GRIDRAD_DIR", hr_base)
    monkeypatch.setattr(b04, "GRIDRAD_SEV_DIR", sev_base)
    monkeypatch.setattr(c04, "GRIDRAD_DIR", hr_base)
    monkeypatch.setattr(c04, "GRIDRAD_SEV", sev_base)

    day = date(2018, 5, 10)
    empty = """<?xml version="1.0"?><catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"><dataset name="root"/></catalog>"""
    v42 = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0">
  <dataset name="root">
    <dataset name="nexrad_3d_v4_2_20180510T120000Z.nc" />
    <dataset name="nexrad_3d_v4_2_20180510T130000Z.nc" />
    <dataset name="nexrad_3d_v4_2_20180510T140000Z.nc" />
  </dataset>
</catalog>"""

    def fake_download(session, item, *, connect_timeout, read_timeout):
        item.out_path.parent.mkdir(parents=True, exist_ok=True)
        item.out_path.write_bytes(b"stub")
        return item, "downloaded"

    monkeypatch.setattr(b04, "_download_one", fake_download)

    stats = b04.download_for_day_adaptive(
        _fake_catalog_session(b04, v31_xml=empty, v42_xml=v42),
        day,
        catalog_timeout=(10.0, 10.0),
        connect_timeout=10.0,
        read_timeout=10.0,
        max_workers=1,
    )
    assert stats["source_mode"] == "hourly-only"
    assert stats["downloaded"] == 3

    files, source = c04.find_gridrad_files(day)
    assert source == "gridrad-hourly-v42"
    assert len(files) == 3
    assert all(p.parent.name == "20180510" for p in files)


def test_adaptive_severe_gap_fill_pulls_v42_hourly_2018(load_script, tmp_path, monkeypatch):
    """Partial severe coverage + V4.2 hourly fill is visible to 04c find_gridrad_files."""
    b04 = load_script("04b_download_gridrad.py")
    c04 = load_script("04c_fill_gridrad_gap.py")

    hr_base = tmp_path / "gridrad"
    sev_base = tmp_path / "gridrad_severe"
    monkeypatch.setattr(b04, "GRIDRAD_DIR", hr_base)
    monkeypatch.setattr(b04, "GRIDRAD_SEV_DIR", sev_base)
    monkeypatch.setattr(c04, "GRIDRAD_DIR", hr_base)
    monkeypatch.setattr(c04, "GRIDRAD_SEV", sev_base)

    day = date(2018, 6, 1)
    sev_stage = sev_base / "by_convective_day" / "20180601"
    hr_stage = hr_base / "by_convective_day" / "20180601"
    sev_stage.mkdir(parents=True)
    hr_stage.mkdir(parents=True)

    (sev_stage / "nexrad_3d_v4_2_20180601T130000Z.nc").write_bytes(b"s")
    for hour in (15, 16, 17):
        (hr_stage / f"nexrad_3d_v4_2_20180601T{hour:02d}0000Z.nc").write_bytes(b"h")

    files, source = c04.find_gridrad_files(day)
    assert source == "gridrad-severe-5min+hourly-fill"
    names = {p.name for p in files}
    assert "nexrad_3d_v4_2_20180601T130000Z.nc" in names
    assert "nexrad_3d_v4_2_20180601T150000Z.nc" in names

    # Eligibility helper used by 04b planning should allow V4.2 for this day.
    assert b04._v42_hourly_eligible(day)
    assert b04.DS_HOURLY_V42 in b04._hourly_dataset_ids(day)


def test_v42_not_eligible_off_season_integration(load_script):
    """Mar 2018 has no V4.2 dataset in the 04b planning chain."""
    b04 = load_script("04b_download_gridrad.py")
    day = date(2018, 3, 15)
    assert not b04._v42_hourly_eligible(day)
    assert b04._hourly_dataset_ids(day) == [b04.DS_HOURLY]
