from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts._io import (
    MESH_SOURCE_MANIFEST_FIELDS,
    classify_mesh_source_day,
    count_plain_and_compressed_sources,
    mesh_manifest_row,
    read_mesh_manifest_rows_by_date,
    upsert_mesh_manifest_row,
    write_mesh_manifest_rows,
)


def test_classify_mesh_source_day():
    assert classify_mesh_source_day(0, 0) == "missing_source"
    assert classify_mesh_source_day(5, 0) == "no_hail_pixels"
    assert classify_mesh_source_day(5, 10) == "ok"
    assert classify_mesh_source_day(5, 10, 2) == "ok_with_read_errors"
    assert classify_mesh_source_day(5, 0, 2) == "no_hail_pixels_with_read_errors"
    assert classify_mesh_source_day(3, 0, 3) == "error"


def test_count_plain_and_compressed_sources():
    keys = [
        "a.netcdf",
        "b.netcdf.gz",
        "c.netcdf.gz",
        "MRMS_MESH_00.50_20201014-120000.grib2.gz",
    ]
    plain, gz = count_plain_and_compressed_sources(keys)
    assert plain == 1
    assert gz == 2

    plain, gz = count_plain_and_compressed_sources(
        keys,
        plain_suffixes=(".grib2",),
        compressed_suffixes=(".grib2.gz",),
    )
    assert plain == 0
    assert gz == 1


def test_manifest_csv_roundtrip(tmp_path: Path):
    manifest = tmp_path / "manifest_stage02_mrms.csv"
    out = tmp_path / "mesh_20201014.tif"
    row = mesh_manifest_row(
        date(2020, 10, 14),
        out,
        tmp_path,
        source_files=12,
        plain_count=0,
        gz_count=12,
        source_pixels=100,
        active_cells=3,
        max_mesh_mm=45.2,
        status="ok",
        skipped=False,
        read_errors=0,
    )
    upsert_mesh_manifest_row(manifest, row)
    rows = read_mesh_manifest_rows_by_date(manifest)
    assert rows["2020-10-14"]["source_files"] == "12"
    assert rows["2020-10-14"]["status"] == "ok"
    assert list(rows["2020-10-14"].keys()) == MESH_SOURCE_MANIFEST_FIELDS

    write_mesh_manifest_rows(manifest, {})
    assert not manifest.exists() or manifest.read_text().count("\n") <= 1


def test_stage02_manifest_on_skip(load_script, monkeypatch, tmp_path):
    s = load_script("02_download_mrms_mesh.py")
    out = tmp_path / "2020" / "mesh_20201014.tif"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"\x00")  # existence check only; summarize is mocked

    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest_stage02_mrms.csv")
    monkeypatch.setattr(
        s,
        "list_mesh_keys_for_convective_day",
        lambda _s3, _day: ["k1.grib2.gz"],
    )
    monkeypatch.setattr(
        s,
        "summarize_mesh_output_raster",
        lambda _p, **kw: (5, 33.3),
    )

    result = s.process_day(None, date(2020, 10, 14), workers=1)
    assert result["skipped"] is True
    assert (tmp_path / "manifest_stage02_mrms.csv").exists()
