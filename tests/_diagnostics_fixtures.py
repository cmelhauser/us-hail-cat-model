"""Shared synthetic I/O helpers for diagnostics coverage tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin


def write_mesh_tif(
    path: Path,
    peak: float = 40.0,
    *,
    nrows: int = 8,
    ncols: int = 8,
    tags: dict[str, str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.zeros((nrows, ncols), dtype=np.float32)
    arr[nrows // 2, ncols // 2] = peak
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype="float32",
        transform=from_origin(-125.0, 50.0, 0.05, 0.05),
    ) as dst:
        dst.write(arr, 1)
        if tags:
            dst.update_tags(**tags)


def write_grid_tif(path: Path, data: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nrows, ncols = data.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype="float32",
        transform=from_origin(-125.0, 50.0, 0.05, 0.05),
    ) as dst:
        dst.write(data.astype(np.float32), 1)


def seed_mesh_days(
    mesh_dir: Path,
    days: list[date],
    *,
    peak: float = 40.0,
    nrows: int = 8,
    ncols: int = 8,
) -> None:
    for day in days:
        write_mesh_tif(
            mesh_dir / str(day.year) / f"mesh_{day.strftime('%Y%m%d')}.tif",
            peak=peak,
            nrows=nrows,
            ncols=ncols,
        )


def make_spc_pairs_csv(path: Path, n: int = 50) -> None:
    import pandas as pd

    rows = []
    for i in range(n):
        rows.append(
            {
                "date": f"201506{1 + (i % 28):02d}",
                "lat": 40.75 if i % 2 == 0 else 46.0,
                "lon": -73.99 if i % 2 == 0 else -110.0,
                "spc_size_in": 0.5 + (i % 6) * 0.25,
                "mesh75_mm": 10.0 + (i % 8) * 5.0,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
