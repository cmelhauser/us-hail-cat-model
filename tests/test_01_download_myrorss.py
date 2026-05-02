import numpy as np
import gzip
from conftest import load_stage


def test_stage01_block_max_uses_maximum_not_sum():
    s = load_stage("01_download_myrorss.py")
    data = np.arange(16, dtype=np.float32).reshape(4, 4)
    out = s.block_max(data, 2)
    assert out.tolist() == [[5.0, 7.0], [13.0, 15.0]]


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
    s = load_stage("01_download_myrorss.py")
    assert s.classify_day(source_files=0, active_cells=0) == "missing_source"
    assert s.classify_day(source_files=296, active_cells=0) == "no_hail_pixels"
    assert s.classify_day(source_files=296, active_cells=12) == "ok"


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
