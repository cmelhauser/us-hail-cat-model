"""Coverage tests for Stage 04a — mocked CDS, isotherm compute, validation."""

from __future__ import annotations

from pathlib import Path

import sys

import numpy as np
import pytest
import xarray as xr

pytestmark = pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")


def _pressure_chunk(path: Path, year: int, *, levels=(1000, 900)) -> None:
    times = np.array([f"{year}-{m:02d}-01" for m in range(1, 13)], dtype="datetime64[ns]")
    temp = np.zeros((12, len(levels), 1, 1), dtype=np.float32)
    geop = np.zeros((12, len(levels), 1, 1), dtype=np.float32)
    for m in range(12):
        # Cross 0°C between levels for interpolation
        temp[m, 0, 0, 0] = 280.0
        temp[m, 1, 0, 0] = 268.0
        geop[m, :, 0, 0] = np.array([500.0, 2500.0]) * 9.80665
    xr.Dataset(
        {
            "t": (["time", "pressure_level", "latitude", "longitude"], temp),
            "z": (["time", "pressure_level", "latitude", "longitude"], geop),
        },
        coords={
            "time": times,
            "pressure_level": list(levels),
            "latitude": [40.0],
            "longitude": [-100.0],
        },
    ).to_netcdf(path)


def test_stage04a_cds_error_helpers(load_script):
    s = load_script("04a_download_era5_isotherms.py")
    assert s._is_cds_cost_limit_error(Exception("cost limits exceeded"))
    assert s._is_cds_cost_limit_error(Exception("request is too large"))
    assert s._is_cds_licence_error(Exception("licence not accepted"))
    with pytest.raises(RuntimeError, match="licence"):
        s._raise_cds_licence_error("http://example.com")


def test_stage04a_retrieve_chunk_existing_and_download(load_script, tmp_path, monkeypatch):
    s = load_script("04a_download_era5_isotherms.py")
    target = tmp_path / "chunk.nc"
    _pressure_chunk(target, 1991)
    assert s._retrieve_era5_chunk(None, ["1991"], ["01"], target) == target

    empty = tmp_path / "empty.nc"
    empty.write_bytes(b"")
    fresh = tmp_path / "fresh.nc"

    class FakeClient:
        def retrieve(self, dataset, request, path):
            _pressure_chunk(Path(path), 1992)

    s._retrieve_era5_chunk(FakeClient(), ["1992"], ["01"], fresh)
    assert fresh.stat().st_size > 0

    class LicClient:
        def retrieve(self, dataset, request, path):
            raise Exception("licence not accepted for dataset")

    with pytest.raises(RuntimeError, match="licence"):
        s._retrieve_era5_chunk(LicClient(), ["1993"], ["01"], tmp_path / "lic.nc")


def test_stage04a_download_temperature_and_surface(load_script, tmp_path, monkeypatch):
    s = load_script("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)

    raw = tmp_path / "era5_monthly_temp_plevels_conus.nc"
    raw.write_bytes(b"x")
    monkeypatch.setattr(s, "CLIM_YEARS", ["1991"])
    assert s.download_era5_temperature() == [raw]

    raw.unlink()
    monkeypatch.setattr(s, "CLIM_YEARS", ["1991", "1992"])

    class FakeClient:
        def retrieve(self, dataset, request, path):
            year = request["year"][0]
            _pressure_chunk(Path(path), int(year))

    import sys
    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": FakeClient})

    chunks = s.download_era5_temperature()
    assert len(chunks) == 2

    sfc = tmp_path / "era5_surface_geopotential_conus.nc"
    sfc.write_bytes(b"exists")
    assert s.download_era5_surface_geopotential() == sfc

    sfc.unlink()

    class SfcClient:
        def retrieve(self, dataset, request, path):
            xr.Dataset(
                {"z": (["latitude", "longitude"], np.array([[5000.0]], dtype=np.float32))},
                coords={"latitude": [40.0], "longitude": [-100.0]},
            ).to_netcdf(path)

    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": SfcClient})
    out = s.download_era5_surface_geopotential()
    assert out.exists()


def test_stage04a_load_pressure_missing_month(load_script, tmp_path):
    s = load_script("04a_download_era5_isotherms.py")
    p = tmp_path / "partial.nc"
    times = np.array(["1991-01-01"], dtype="datetime64[ns]")
    xr.Dataset(
        {
            "t": (["time", "pressure_level", "latitude", "longitude"], np.zeros((1, 2, 1, 1))),
            "z": (["time", "pressure_level", "latitude", "longitude"], np.zeros((1, 2, 1, 1))),
        },
        coords={
            "time": times,
            "pressure_level": [1000, 900],
            "latitude": [40.0],
            "longitude": [-100.0],
        },
    ).to_netcdf(p)
    with pytest.raises(ValueError, match="missing month"):
        s._load_pressure_climatology([p])

    with pytest.raises(ValueError, match="No ERA5"):
        s._load_pressure_climatology([])


def test_stage04a_compute_isotherm_heights_and_validate(load_script, tmp_path, monkeypatch):
    s = load_script("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)
    monkeypatch.setattr(s, "OUT_FILE", tmp_path / "era5_monthly_isotherms_conus.nc")

    p1 = tmp_path / "y1.nc"
    p2 = tmp_path / "y2.nc"
    _pressure_chunk(p1, 1991)
    _pressure_chunk(p2, 1992)
    sfc = tmp_path / "sfc.nc"
    xr.Dataset(
        {"z": (["latitude", "longitude"], np.array([[100.0]], dtype=np.float32))},
        coords={"latitude": [40.0], "longitude": [-100.0]},
    ).to_netcdf(sfc)

    s.compute_isotherm_heights([p1, p2], sfc)
    assert s.OUT_FILE.exists()

    assert s.validate_outputs() is True

    bad = tmp_path / "bad.nc"
    xr.Dataset(
        {"h_0C_km": (["month", "latitude", "longitude"], np.full((12, 1, 1), np.nan))},
        coords={"month": np.arange(1, 13), "latitude": [40.0], "longitude": [-100.0]},
    ).to_netcdf(bad)
    monkeypatch.setattr(s, "OUT_FILE", bad)
    assert s.validate_outputs() is False

    monkeypatch.setattr(s, "OUT_FILE", tmp_path / "missing.nc")
    assert s.validate_outputs() is False


def test_stage04a_time_dim_valid_time(load_script, tmp_path):
    s = load_script("04a_download_era5_isotherms.py")
    p = tmp_path / "vt.nc"
    xr.Dataset(
        {
            "t": (["valid_time", "pressure_level", "latitude", "longitude"], np.zeros((1, 2, 1, 1))),
            "z": (["valid_time", "pressure_level", "latitude", "longitude"], np.zeros((1, 2, 1, 1))),
        },
        coords={
            "valid_time": np.array(["1991-01-01"], dtype="datetime64[ns]"),
            "pressure_level": [1000, 900],
            "latitude": [40.0],
            "longitude": [-100.0],
        },
    ).to_netcdf(p)
    assert s._time_dim_name(xr.open_dataset(p)) == "valid_time"


def test_stage04a_main_branches(load_script, tmp_path, monkeypatch):
    s = load_script("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)
    monkeypatch.setattr(s, "OUT_FILE", tmp_path / "out.nc")
    monkeypatch.setattr(s, "download_era5_temperature", lambda: [tmp_path / "p.nc"])
    monkeypatch.setattr(s, "download_era5_surface_geopotential", lambda: tmp_path / "s.nc")
    monkeypatch.setattr(s, "compute_isotherm_heights", lambda *_a, **_k: None)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)

    xr.Dataset(
        {
            "h_0C_km": (["month", "latitude", "longitude"], np.full((12, 1, 1), 3.0)),
            "h_m20C_km": (["month", "latitude", "longitude"], np.full((12, 1, 1), 6.0)),
        },
        coords={"month": np.arange(1, 13), "latitude": [40.0], "longitude": [-100.0]},
    ).to_netcdf(tmp_path / "out.nc")

    with pytest.raises(SystemExit) as exc:
        monkeypatch.setattr(sys, "argv", ["04a", "--validate"])
        s.main()
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        monkeypatch.setattr(sys, "argv", ["04a"])
        s.main()
    assert exc.value.code == 0

    monkeypatch.setattr(s, "validate_outputs", lambda: False)
    with pytest.raises(SystemExit) as exc:
        monkeypatch.setattr(sys, "argv", ["04a", "--validate"])
        s.main()
    assert exc.value.code == 1
