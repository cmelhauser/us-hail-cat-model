import numpy as np
from conftest import load_stage


def test_stage04b_shi_column_increases_with_reflectivity():
    s = load_stage("04c_fill_gridrad_gap.py")
    heights = np.array([1, 2, 3, 4, 5, 6, 7], dtype=float)
    low = np.array([30, 35, 40, 42, 45, 45, 45], dtype=float)
    high = low + 10
    assert s.compute_shi_column(high, heights, 2.0, 5.0) > s.compute_shi_column(low, heights, 2.0, 5.0)


def test_stage04b_shi_uses_single_temperature_weight():
    s = load_stage("04c_fill_gridrad_gap.py")
    z = np.array([50.0])
    height = np.array([3.5])
    h0, hm20 = 2.0, 5.0
    weight = 0.5
    expected = 0.1 * weight * s.E_COEFF * (10.0 ** (s.E_EXPONENT * 50.0)) * 1000.0
    assert np.isclose(s.compute_shi_column(z, height, h0, hm20), expected)


def test_stage04b_shi_uses_actual_vertical_spacing():
    s = load_stage("04c_fill_gridrad_gap.py")
    z = np.full(3, 50.0)
    uniform = s.compute_shi_column(z, np.array([4.0, 5.0, 6.0]), 2.0, 3.0)
    nonuniform = s.compute_shi_column(z, np.array([4.0, 5.0, 7.0]), 2.0, 3.0)
    assert nonuniform > uniform


def test_stage04b_climo_freezing_levels_are_ordered():
    s = load_stage("04c_fill_gridrad_gap.py")
    h0, hm20 = s._get_freezing_levels_climo(35.0, 5)
    assert 0.5 < h0 < hm20 < 12.0


def test_stage04b_uses_shared_300mm_qa_cap():
    s = load_stage("04c_fill_gridrad_gap.py")
    repaired, n_bad = s.sanitize_hail_values(np.array([[0.0, 299.0, 301.0]], dtype=np.float32))
    assert s.QA_MAX_HAIL_MM == 300.0
    assert n_bad == 1
    assert repaired.tolist() == [[0.0, 299.0, 0.0]]


def test_stage04c_loads_sparse_reflectivity_weight():
    s = load_stage("04c_fill_gridrad_gap.py")

    class Dataset:
        def __init__(self):
            self.variables = {
                "wReflectivity": np.array([1.75], dtype=np.float32),
                "index": np.array([3], dtype=np.int64),
                "Altitude": np.array([1.0, 2.0], dtype=np.float32),
                "Latitude": np.array([35.0], dtype=np.float32),
                "Longitude": np.array([-97.0, -96.0], dtype=np.float32),
            }

    weight = s._load_indexed_3d(Dataset(), "wReflectivity")
    assert weight.shape == (2, 1, 2)
    assert weight[1, 0, 1] == 1.75


def test_stage04c_all_files_fail_returns_day_error(tmp_path, monkeypatch):
    from datetime import date
    from pathlib import Path

    s = load_stage("04c_fill_gridrad_gap.py")
    day = date(2015, 5, 20)
    out = tmp_path / "mesh_20150520.tif"
    nc_files = [tmp_path / "a.nc", tmp_path / "b.nc"]
    for p in nc_files:
        p.write_text("x")

    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    monkeypatch.setattr(
        s,
        "find_gridrad_files",
        lambda _day: (nc_files, "gridrad-hourly"),
    )
    monkeypatch.setattr(
        s,
        "temporal_coverage_summary",
        lambda *_a, **_k: {
            "source_first_utc": "",
            "source_last_utc": "",
            "source_max_gap_minutes": None,
            "temporal_coverage_status": "unknown",
        },
    )
    monkeypatch.setattr(s, "mesh_path_for_convective_day", lambda *_a, **_k: out)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")

    def boom(*_a, **_k):
        raise RuntimeError("read failed")

    monkeypatch.setattr(s, "process_gridrad_file", boom)
    result = s.process_day(day)
    assert "error" in result
    assert result["errors"] == 2
    assert not out.exists()
    rows = s.read_mesh_manifest_rows_by_date(s.MANIFEST_FILE)
    assert rows[day.isoformat()]["status"] == "error"


def test_stage04c_resume_preserves_manifest_provenance(tmp_path, monkeypatch):
    from datetime import date

    s = load_stage("04c_fill_gridrad_gap.py")
    day = date(2015, 5, 21)
    out = tmp_path / "mesh_20150521.tif"
    out.write_bytes(b"tif")
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    prior = s.mesh_manifest_row(
        day,
        out,
        s.REPO_ROOT,
        source_files=4,
        plain_count=3,
        gz_count=1,
        source_pixels=12,
        active_cells=8,
        max_mesh_mm=55.0,
        status="ok",
        skipped=False,
        read_errors=0,
        source_first_utc="2015-05-21T12:00:00Z",
        source_last_utc="2015-05-22T11:00:00Z",
        source_max_gap_minutes=60.0,
        temporal_coverage_status="complete",
    )
    s.upsert_manifest_row(prior)

    row = s.manifest_row_for_day(
        day,
        out,
        [],
        source_pixels=None,
        active_cells=10,
        max_mesh_mm=40.0,
        skipped=True,
        prior_row=prior,
    )
    assert row["status"] == "ok"
    assert row["source_files"] == 4
    assert row["active_cells_0p05"] == 10
    assert row["max_mesh_mm"] == 40.0
    assert row["temporal_coverage_status"] == "complete"

    unknown = s.manifest_row_for_day(
        day,
        out,
        [],
        source_pixels=None,
        active_cells=10,
        max_mesh_mm=40.0,
        skipped=True,
        prior_row=None,
    )
    assert unknown["status"] == "unknown_after_cleanup"
