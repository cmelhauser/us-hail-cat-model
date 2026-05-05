from conftest import load_stage
import numpy as np
import pytest
import xarray as xr

pytestmark = pytest.mark.filterwarnings("ignore:numpy.ndarray size changed:RuntimeWarning")


def test_stage04a_pressure_levels_span_melting_layer():
    s = load_stage("04a_download_era5_isotherms.py")
    levels = [int(x) for x in s.PRESSURE_LEVELS]
    assert min(levels) <= 200
    assert max(levels) >= 1000
    assert len(levels) >= 20


def test_stage04a_streams_pressure_chunk_climatology(tmp_path):
    s = load_stage("04a_download_era5_isotherms.py")
    files = []
    for offset, year in enumerate([1991, 1992]):
        path = tmp_path / f"era5_{year}.nc"
        times = np.array([f"{year}-{month:02d}-01" for month in range(1, 13)], dtype="datetime64[ns]")
        temp = np.zeros((12, 2, 1, 1), dtype=np.float32)
        geop = np.zeros((12, 2, 1, 1), dtype=np.float32)
        for month in range(12):
            temp[month, :, 0, 0] = 260 + month + offset
            geop[month, :, 0, 0] = (1000 + 10 * month + offset) * 9.80665
        xr.Dataset(
            {
                "t": (["time", "pressure_level", "latitude", "longitude"], temp),
                "z": (["time", "pressure_level", "latitude", "longitude"], geop),
            },
            coords={
                "time": times,
                "pressure_level": [1000, 900],
                "latitude": [40.0],
                "longitude": [-100.0],
            },
        ).to_netcdf(path)
        files.append(path)

    temp_monthly, heights_monthly, lats, lons, counts = s._load_pressure_climatology(files)

    assert temp_monthly.shape == (12, 2, 1, 1)
    assert np.all(counts == 2)
    assert temp_monthly[0, 0, 0, 0] == 260.5
    assert np.isclose(heights_monthly[0, 0, 0, 0], 1000.5)
    assert lats.tolist() == [40.0]
    assert lons.tolist() == [-100.0]
