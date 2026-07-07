import numpy as np
import gzip
from conftest import load_stage


def test_stage01_block_max_uses_maximum_not_sum():
    s = load_stage("01_download_myrorss.py")
    data = np.arange(16, dtype=np.float32).reshape(4, 4)
    out = s.block_max(data, 2)
    assert out.tolist() == [[5.0, 7.0], [13.0, 15.0]]


def test_stage01_qa_cap_is_300_mm():
    s = load_stage("01_download_myrorss.py")
    assert s.QA_MAX_HAIL_MM == 300.0


def test_stage01_sanitize_mesh_array_removes_nonfinite_negative_and_above_cap():
    s = load_stage("01_download_myrorss.py")
    data = np.array([[0.0, 1.0, np.inf], [np.nan, -1.0, 301.0]], dtype=np.float32)
    repaired, n_bad = s.sanitize_mesh_array(data)
    assert n_bad == 4
    assert repaired.tolist() == [[0.0, 1.0, 0.0], [0.0, 0.0, 0.0]]


def test_stage01_iter_dates_inclusive():
    from datetime import date
    s = load_stage("01_download_myrorss.py")
    days = list(s.iter_dates(date(2000, 1, 1), date(2000, 1, 3)))
    assert [d.isoformat() for d in days] == ["2000-01-01", "2000-01-02", "2000-01-03"]


def test_stage01_lists_plain_and_gzipped_netcdf_keys():
    s = load_stage("01_download_myrorss.py")

    class FakePaginator:
        def paginate(self, **kwargs):
            return [{
                "Contents": [
                    {"Key": "2000/01/02/MESH/00.25/a.netcdf.gz"},
                    {"Key": "2000/01/02/MESH/00.25/b.netcdf"},
                    {"Key": "2000/01/02/MESH/00.25/c.txt"},
                ]
            }]

    class FakeS3:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator()

    from datetime import date
    assert s.list_mesh_keys(FakeS3(), date(2000, 1, 2)) == [
        "2000/01/02/MESH/00.25/a.netcdf.gz",
        "2000/01/02/MESH/00.25/b.netcdf",
    ]


def test_stage01_decodes_plain_and_gzipped_netcdf_payloads():
    s = load_stage("01_download_myrorss.py")
    payload = b"netcdf bytes"
    assert s.decode_netcdf_object("x.netcdf", payload) == payload
    assert s.decode_netcdf_object("x.netcdf.gz", gzip.compress(payload)) == payload


def test_stage01_classifies_missing_source_separately_from_no_hail():
    from scripts._io import classify_mesh_source_day

    assert classify_mesh_source_day(source_files=0, active_cells=0) == "missing_source"
    assert classify_mesh_source_day(source_files=296, active_cells=0) == "no_hail_pixels"
    assert classify_mesh_source_day(source_files=296, active_cells=12) == "ok"


def test_stage01_manifest_row_counts_source_formats():
    from datetime import date
    from pathlib import Path

    s = load_stage("01_download_myrorss.py")
    row = s.manifest_row(
        date(1998, 4, 24),
        s.OUT_DIR / "1998" / "mesh_19980424.tif",
        [
            "1998/04/24/MESH/00.25/a.netcdf",
            "1998/04/24/MESH/00.25/b.netcdf.gz",
        ],
        source_pixels=123,
        active_cells=45,
        max_mesh_mm=12.3,
        status="ok",
    )

    assert row["date"] == "1998-04-24"
    assert row["output_path"] == str(Path("data/historical/mesh_0.05deg/1998/mesh_19980424.tif"))
    assert row["source_files"] == 2
    assert row["plain_netcdf_files"] == 1
    assert row["gz_netcdf_files"] == 1
    assert row["source_valid_pixels"] == 123
    assert row["active_cells_0p05"] == 45
    assert row["status"] == "ok"


def test_stage01_sparse_updates_use_wdss_pixel_axes():
    """pixel_x = row (lat), pixel_y = col (lon) per WDSS-II SparseLatLonGrid."""
    import os
    import tempfile

    import netCDF4 as nc

    s = load_stage("01_download_myrorss.py")
    from scripts._io import latlon_to_grid

    def native_indices(lat: float, lon: float) -> tuple[int, int]:
        px = int((s.NATIVE_LAT_ORIGIN - lat) / s.NATIVE_DX)
        py = int((lon - s.NATIVE_LON_ORIGIN) / s.NATIVE_DX)
        return px, py

    ok_px, ok_py = native_indices(34.98, -97.48)
    fl_px, fl_py = native_indices(27.48, -81.48)
    px = np.array([ok_px, fl_px], dtype=np.int16)
    py = np.array([ok_py, fl_py], dtype=np.int16)
    mesh = np.array([40.0, 35.0], dtype=np.float32)

    fd, tmp = tempfile.mkstemp(suffix=".nc")
    os.close(fd)
    try:
        with nc.Dataset(tmp, "w") as ds:
            ds.createDimension("pixel", len(px))
            ds.createVariable("pixel_x", "i2", ("pixel",))[:] = px
            ds.createVariable("pixel_y", "i2", ("pixel",))[:] = py
            v = ds.createVariable("MESH", "f4", ("pixel",))
            v[:] = mesh
            ds.Latitude = 55.005
            ds.Longitude = -130.005
            ds.LatGridSpacing = 0.01
            ds.LonGridSpacing = 0.01
            ds.MissingData = -99900.0

        with open(tmp, "rb") as f:
            r, c, v, n = s.sparse_updates_from_netcdf_bytes(f.read())
    finally:
        os.unlink(tmp)

    assert n == 2
    ok_r, ok_c = latlon_to_grid(34.98, -97.48)
    fl_r, fl_c = latlon_to_grid(27.48, -81.48)
    conus_ok_r = ok_px - s.CONUS_ROW_START
    conus_ok_c = ok_py - s.CONUS_COL_START
    conus_fl_r = fl_px - s.CONUS_ROW_START
    conus_fl_c = fl_py - s.CONUS_COL_START
    assert (conus_ok_r, conus_ok_c) in set(zip(r.tolist(), c.tolist()))
    assert (conus_fl_r, conus_fl_c) in set(zip(r.tolist(), c.tolist()))
    # Florida cell must land east of 95°W on the 0.01° native grid.
    assert fl_py > (-95.0 - s.NATIVE_LON_ORIGIN) / s.NATIVE_DX
