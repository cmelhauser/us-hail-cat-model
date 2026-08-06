"""Tests for scripts/06_validate_mesh_vs_spc.py."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from conftest import load_stage


@pytest.fixture
def s06():
    return load_stage("06_validate_mesh_vs_spc.py")


def _write_spc_csv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    header: str = "lat,lon,size,time",
    leading_comment: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="latin-1") as f:
        if leading_comment:
            f.write("# SPC hail reports\n")
        f.write(header + "\n")
        if header.startswith("lat"):
            writer = csv.DictWriter(f, fieldnames=["lat", "lon", "size", "time"])
            writer.writeheader()
            writer.writerows(rows)
        else:
            for row in rows:
                f.write(f"{row['lat']},{row['lon']},{row['size']},{row['time']}\n")


def _write_mesh_tif(path: Path, value: float = 30.0, shape: tuple[int, int] = (3, 3)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros(shape, dtype=np.float32)
    data[1, 1] = value
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-100, 40, 0.05, 0.05),
    ) as dst:
        dst.write(data, 1)


def test_stage06_latlon_to_grid_inside_and_outside(s06):
    row, col = s06.latlon_to_grid(40.0, -100.0)
    assert 0 <= row < s06.NROWS
    assert 0 <= col < s06.NCOLS
    assert s06.latlon_to_grid(10.0, -100.0) == (-1, -1)


def test_stage06_parse_spc_csv_parses_valid_and_skips_invalid(tmp_path, s06):
    path = tmp_path / "200515_rpts_hail.csv"
    _write_spc_csv(
        path,
        [
            {"lat": "40.0", "lon": "-100.0", "size": "100", "time": "1800"},
            {"lat": "10.0", "lon": "-100.0", "size": "100", "time": "1200"},
            {"lat": "bad", "lon": "-100.0", "size": "100", "time": "1200"},
        ],
        leading_comment=True,
    )
    reports = s06.parse_spc_csv(path)
    assert len(reports) == 1
    lat, lon, size_in, hour = reports[0]
    assert lat == 40.0 and lon == -100.0 and size_in == 1.0 and hour == 18

    alt = tmp_path / "alt.csv"
    alt.write_text("Lat,Lon,Size,Time\n35.0,-95.0,150,0300\n", encoding="latin-1")
    alt_reports = s06.parse_spc_csv(alt)
    assert alt_reports[0][2] == 1.5
    assert alt_reports[0][3] == 3

    assert s06.parse_spc_csv(tmp_path / "missing.csv") == []
    (tmp_path / "broken.csv").write_bytes(b"\xff\xfe")
    assert s06.parse_spc_csv(tmp_path / "broken.csv") == []


def test_stage06_load_mesh_raster_missing_and_present(tmp_path, s06, monkeypatch):
    monkeypatch.setattr(s06, "MESH_DIR", tmp_path)
    assert s06.load_mesh_raster("20200601") is None
    _write_mesh_tif(tmp_path / "2020" / "mesh_20200601.tif", value=42.0)
    arr = s06.load_mesh_raster("20200601")
    assert arr is not None
    assert float(arr[1, 1]) == 42.0


def test_stage06_build_pairs_matches_reports_to_mesh(tmp_path, s06, monkeypatch):
    spc_dir = tmp_path / "spc"
    mesh_dir = tmp_path / "mesh"
    monkeypatch.setattr(s06, "SPC_DIR", spc_dir)
    monkeypatch.setattr(s06, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s06, "latlon_to_grid", lambda lat, lon: (1, 1))

    _write_spc_csv(
        spc_dir / "200515_rpts_hail.csv",
        [{"lat": "40.0", "lon": "-100.0", "size": "125", "time": "1500"}],
    )
    _write_mesh_tif(mesh_dir / "2020" / "mesh_20200515.tif", value=50.8)

    pairs = s06.build_pairs()
    assert len(pairs) == 1
    assert pairs[0]["spc_size_in"] == 1.25
    assert pairs[0]["mesh75_mm"] == 50.8
    assert pairs[0]["date"] == "20200515"


def test_stage06_build_pairs_skips_out_of_grid_and_empty_reports(tmp_path, s06, monkeypatch):
    spc_dir = tmp_path / "spc"
    mesh_dir = tmp_path / "mesh"
    monkeypatch.setattr(s06, "SPC_DIR", spc_dir)
    monkeypatch.setattr(s06, "MESH_DIR", mesh_dir)

    _write_spc_csv(
        spc_dir / "200515_rpts_hail.csv",
        [
            {"lat": "21.0", "lon": "-100.0", "size": "100", "time": "1200"},
            {"lat": "bad", "lon": "-100.0", "size": "100", "time": "1200"},
        ],
    )
    _write_spc_csv(spc_dir / "notadate_rpts_hail.csv", [])
    (spc_dir / "200516_rpts_hail.csv").write_text("lat,lon,size,time\n", encoding="latin-1")
    _write_mesh_tif(mesh_dir / "2020" / "mesh_20200515.tif")

    assert s06.build_pairs() == []


def test_stage06_make_figures_includes_detection_bins(tmp_path, s06, monkeypatch):
    fig_dir = tmp_path / "figures"
    monkeypatch.setattr(s06, "FIG_DIR", fig_dir)
    pairs = [
        {"spc_size_in": 1.05 + 0.01 * i, "mesh75_in": 1.0, "mesh75_mm": 25.4}
        for i in range(12)
    ]
    s06.make_figures(pairs)
    assert (fig_dir / "detection_by_size.png").exists()


def test_stage06_make_figures_skips_sparse_detection_bins(tmp_path, s06, monkeypatch):
    fig_dir = tmp_path / "figures"
    monkeypatch.setattr(s06, "FIG_DIR", fig_dir)
    pairs = [{"spc_size_in": 0.6, "mesh75_in": 0.5, "mesh75_mm": 12.7} for _ in range(5)]
    s06.make_figures(pairs)
    assert (fig_dir / "detection_by_size.png").exists()


def test_stage06_build_pairs_skips_missing_raster_and_bad_filenames(tmp_path, s06, monkeypatch):
    spc_dir = tmp_path / "spc"
    mesh_dir = tmp_path / "mesh"
    monkeypatch.setattr(s06, "SPC_DIR", spc_dir)
    monkeypatch.setattr(s06, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s06, "latlon_to_grid", lambda lat, lon: (1, 1))

    _write_spc_csv(
        spc_dir / "badname.csv",
        [{"lat": "40.0", "lon": "-100.0", "size": "100", "time": "1200"}],
    )
    _write_spc_csv(
        spc_dir / "200515_rpts_hail.csv",
        [{"lat": "40.0", "lon": "-100.0", "size": "100", "time": "1200"}],
    )
    assert s06.build_pairs() == []


def test_stage06_build_pairs_progress_and_cache_eviction(tmp_path, s06, monkeypatch):
    spc_dir = tmp_path / "spc"
    monkeypatch.setattr(s06, "SPC_DIR", spc_dir)
    monkeypatch.setattr(s06, "MESH_DIR", tmp_path / "mesh")
    monkeypatch.setattr(s06, "latlon_to_grid", lambda lat, lon: (1, 1))
    monkeypatch.setattr(
        s06,
        "load_mesh_raster",
        lambda date_str: np.full((3, 3), 25.4, dtype=np.float32),
    )

    for i in range(502):
        day = f"{i % 28 + 1:02d}"
        month = f"{i % 12 + 1:02d}"
        yy = i % 80
        _write_spc_csv(
            spc_dir / f"{yy:02d}{month}{day}_rpts_hail.csv",
            [{"lat": "40.0", "lon": "-100.0", "size": "100", "time": "1200"}],
        )

    pairs = s06.build_pairs()
    assert len(pairs) == 502


def test_stage06_calibration_reports_bias(s06):
    pairs = [
        {"spc_size_in": 1.0, "mesh75_in": 1.2, "mesh75_mm": 30.48},
        {"spc_size_in": 1.25, "mesh75_in": 1.0, "mesh75_mm": 25.4},
        {"spc_size_in": 0.5, "mesh75_in": 0.0, "mesh75_mm": 0.0},
    ]
    cal = s06.compute_calibration(pairs)
    severe_bin = [r for r in cal if r.get("bin") == '1.00-1.50"'][0]
    assert severe_bin["n"] == 2
    assert "bias_in" in severe_bin
    empty_bin = [r for r in cal if r.get("bin") == '0.75-1.00"'][0]
    assert empty_bin["n"] == 0


def test_stage06_compute_spatial_bias(s06):
    pairs = [
        {"lat": 40.2, "lon": -100.3, "spc_size_in": 1.0, "mesh75_in": 1.2},
        {"lat": 40.8, "lon": -100.7, "spc_size_in": 2.0, "mesh75_in": 0.0},
    ]
    spatial = s06.compute_spatial_bias(pairs)
    assert len(spatial) == 1
    assert spatial[0]["n_reports"] == 1
    assert spatial[0]["mean_ratio"] == pytest.approx(1.2)


def test_stage06_write_summary_and_validate(tmp_path, s06, monkeypatch):
    out_dir = tmp_path / "validation"
    monkeypatch.setattr(s06, "OUT_DIR", out_dir)
    pairs = [
        {
            "date": "20200101",
            "lat": 40.0,
            "lon": -100.0,
            "spc_size_in": 1.5,
            "mesh75_in": 1.2,
            "mesh75_mm": 30.0,
            "hour": 23,
        },
        {
            "date": "20200102",
            "lat": 41.0,
            "lon": -99.0,
            "spc_size_in": 0.5,
            "mesh75_in": 1.1,
            "mesh75_mm": 28.0,
            "hour": 10,
        },
    ]
    cal = s06.compute_calibration(pairs)
    s06.write_summary(pairs, cal)
    summary = (out_dir / "validation_summary.txt").read_text()
    assert "Total report–MESH pairs: 2" in summary
    assert "Severe hail" in summary

    assert s06.validate_outputs() is False
    (out_dir / "mesh_vs_spc_pairs.csv").write_text("x")
    (out_dir / "calibration_report.csv").write_text("x")
    assert s06.validate_outputs() is True
    (out_dir / "validation_summary.txt").write_text("")
    assert s06.validate_outputs() is False


def test_stage06_make_figures_writes_pngs(tmp_path, s06, monkeypatch):
    fig_dir = tmp_path / "figures"
    monkeypatch.setattr(s06, "FIG_DIR", fig_dir)
    pairs = []
    for size in np.linspace(0.8, 3.0, 15):
        pairs.append(
            {
                "spc_size_in": float(size),
                "mesh75_in": float(size) * 0.9,
                "mesh75_mm": float(size) * 25.4,
            }
        )
    s06.make_figures(pairs)
    assert (fig_dir / "mesh_vs_spc_scatter.png").exists()
    assert (fig_dir / "detection_by_size.png").exists()


def test_stage06_make_figures_skips_when_matplotlib_missing(s06, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "matplotlib":
            raise ImportError("no matplotlib")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    s06.make_figures([{"spc_size_in": 1.0, "mesh75_in": 1.0, "mesh75_mm": 25.4}])


def test_stage06_main_validate_and_no_pairs(tmp_path, s06, monkeypatch):
    monkeypatch.setattr(s06, "SPC_DIR", tmp_path / "spc")
    monkeypatch.setattr(s06, "MESH_DIR", tmp_path / "mesh")
    monkeypatch.setattr(s06, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(sys, "argv", ["06_validate_mesh_vs_spc.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s06.main()
    assert exc.value.code == 1

    monkeypatch.setattr(sys, "argv", ["06_validate_mesh_vs_spc.py"])
    with pytest.raises(SystemExit) as exc:
        s06.main()
    assert exc.value.code == 1


def test_stage06_main_full_pipeline(tmp_path, s06, monkeypatch):
    spc_dir = tmp_path / "spc"
    mesh_dir = tmp_path / "mesh"
    out_dir = tmp_path / "validation"
    fig_dir = tmp_path / "figures"
    monkeypatch.setattr(s06, "SPC_DIR", spc_dir)
    monkeypatch.setattr(s06, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s06, "OUT_DIR", out_dir)
    monkeypatch.setattr(s06, "FIG_DIR", fig_dir)
    monkeypatch.setattr(s06, "latlon_to_grid", lambda lat, lon: (1, 1))

    _write_spc_csv(
        spc_dir / "200515_rpts_hail.csv",
        [{"lat": "40.0", "lon": "-100.0", "size": "125", "time": "1500"}],
    )
    _write_mesh_tif(mesh_dir / "2020" / "mesh_20200515.tif")

    monkeypatch.setattr(sys, "argv", ["06_validate_mesh_vs_spc.py"])
    with pytest.raises(SystemExit) as exc:
        s06.main()
    assert exc.value.code == 0
    assert (out_dir / "mesh_vs_spc_pairs.csv").exists()
    assert (out_dir / "calibration_report.csv").exists()
    assert (out_dir / "spatial_bias_1deg.csv").exists()
    assert (fig_dir / "mesh_vs_spc_scatter.png").exists()
