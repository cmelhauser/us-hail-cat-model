#!/usr/bin/env python3
"""
06_validate_mesh_vs_spc.py — Cross-Validate Corrected MESH Against SPC Reports
================================================================================
For each SPC hail report (2004–present), extracts the co-located corrected
MESH75 value from the same day's raster and produces calibration statistics,
detection metrics, and diagnostic figures.

Input
-----
  data/historical/mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif (from stage 05)
  data/historical/spc/YYYY/YYMMDD_rpts_hail.csv                (from stage 03)

Output
------
  data/historical/validation/mesh_vs_spc_pairs.csv
  data/historical/validation/calibration_report.csv
  data/historical/validation/spatial_bias_1deg.csv
  data/historical/validation/validation_summary.txt
  data/historical/validation/figures/*.png

Usage
-----
  python scripts/06_validate_mesh_vs_spc.py
  python scripts/06_validate_mesh_vs_spc.py --validate
"""

import argparse
import csv
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN
    from _io import latlon_to_grid
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN
    from scripts._io import latlon_to_grid
    from scripts._logging import get_logger

MESH_DIR  = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
SPC_DIR   = DATA_ROOT / "historical" / "spc"
OUT_DIR   = DATA_ROOT / "historical" / "validation"
FIG_DIR   = REPO_ROOT / "docs" / "figures" / "analysis"
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "06_validate_mesh_vs_spc.log"

MM_PER_INCH = 25.4

SIZE_BINS = [
    (0.00, 0.75,  "<0.75\""),
    (0.75, 1.00,  "0.75-1.00\""),
    (1.00, 1.50,  "1.00-1.50\""),
    (1.50, 2.00,  "1.50-2.00\""),
    (2.00, 3.00,  "2.00-3.00\""),
    (3.00, 4.00,  "3.00-4.00\""),
    (4.00, 99.0,  ">=4.00\""),
]

log = get_logger("06_validate_mesh_vs_spc", LOG_ROOT).info


def parse_spc_csv(path: Path) -> list:
    """Parse a single SPC hail CSV. Returns list of (lat, lon, size_in, hour)."""
    reports = []
    try:
        with open(path, newline="", encoding="latin-1") as f:
            # SPC CSVs sometimes have comment lines at top
            lines = f.readlines()

        # Find header line
        header_idx = 0
        for i, line in enumerate(lines):
            if "lat" in line.lower() and "lon" in line.lower():
                header_idx = i
                break

        reader = csv.DictReader(lines[header_idx:])
        for row in reader:
            try:
                # Handle various column name conventions
                lat = float(row.get("lat", row.get("Lat", row.get("LAT", ""))))
                lon = float(row.get("lon", row.get("Lon", row.get("LON", ""))))
                size_raw = row.get("size", row.get("Size", row.get("SIZE", "")))
                size_in = float(size_raw) / 100.0  # SPC reports in hundredths of inches

                time_str = row.get("time", row.get("Time", row.get("TIME", "1200")))
                hour = int(str(time_str)[:2]) if time_str else 12

                if 20 <= lat <= 55 and -130 <= lon <= -60 and size_in > 0:
                    reports.append((lat, lon, size_in, hour))
            except (ValueError, TypeError):
                continue
    except Exception:
        pass
    return reports

def load_mesh_raster(date_str: str) -> np.ndarray:
    """Load a corrected MESH75 raster for a given date. Returns None if missing."""
    import rasterio
    year = date_str[:4]
    path = MESH_DIR / year / f"mesh_{date_str}.tif"
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        return src.read(1)

def build_pairs() -> list:
    """Match all SPC reports to co-located MESH75 values."""
    pairs = []
    spc_files = sorted(SPC_DIR.rglob("*_rpts_hail.csv"))
    log(f"  Found {len(spc_files):,} SPC report files")

    loaded_dates = {}  # cache: date_str -> raster or None
    skipped_no_raster = 0

    for i, spc_path in enumerate(spc_files):
        # Extract date from filename: YYMMDD_rpts_hail.csv
        stem = spc_path.stem  # e.g., "240515_rpts_hail"
        try:
            yy = int(stem[:2])
            mm = int(stem[2:4])
            dd = int(stem[4:6])
            year = 2000 + yy if yy < 80 else 1900 + yy
            date_str = f"{year}{mm:02d}{dd:02d}"
        except (ValueError, IndexError):
            continue

        reports = parse_spc_csv(spc_path)
        if not reports:
            continue

        # Load raster (cached)
        if date_str not in loaded_dates:
            loaded_dates[date_str] = load_mesh_raster(date_str)
        raster = loaded_dates[date_str]

        if raster is None:
            skipped_no_raster += 1
            continue

        # Match reports to grid cells
        # Take max reported size per cell per day
        cell_max = {}  # (row, col) -> (max_size_in, lat, lon, hour)
        for lat, lon, size_in, hour in reports:
            row, col = latlon_to_grid(lat, lon)
            if row < 0:
                continue
            key = (row, col)
            if key not in cell_max or size_in > cell_max[key][0]:
                cell_max[key] = (size_in, lat, lon, hour)

        for (row, col), (size_in, lat, lon, hour) in cell_max.items():
            mesh75_mm = float(raster[row, col])
            pairs.append({
                "date":        date_str,
                "lat":         round(lat, 3),
                "lon":         round(lon, 3),
                "spc_size_in": round(size_in, 2),
                "mesh75_mm":   round(mesh75_mm, 1),
                "mesh75_in":   round(mesh75_mm / MM_PER_INCH, 2),
                "grid_row":    row,
                "grid_col":    col,
                "hour":        hour,
            })

        if (i + 1) % 500 == 0:
            log(f"    processed {i+1:,}/{len(spc_files):,} SPC files, "
                f"{len(pairs):,} pairs so far")

        # Memory management: evict old cached rasters
        if len(loaded_dates) > 100:
            loaded_dates.clear()

    log(f"  Total pairs: {len(pairs):,}")
    log(f"  Dates without MESH raster: {skipped_no_raster:,}")
    return pairs

def compute_calibration(pairs: list) -> list:
    """Compute calibration stats by size bin."""
    results = []
    for lo, hi, label in SIZE_BINS:
        subset = [p for p in pairs if lo <= p["spc_size_in"] < hi]
        if not subset:
            results.append({"bin": label, "n": 0})
            continue

        spc = np.array([p["spc_size_in"] for p in subset])
        m75 = np.array([p["mesh75_in"] for p in subset])

        bias = float(np.mean(m75 - spc))
        rmse = float(np.sqrt(np.mean((m75 - spc) ** 2)))
        mae  = float(np.mean(np.abs(m75 - spc)))
        pod  = float(np.mean(m75 > 0))  # fraction where MESH detected anything

        results.append({
            "bin":          label,
            "n":            len(subset),
            "mean_spc_in":  round(float(np.mean(spc)), 3),
            "mean_mesh_in": round(float(np.mean(m75)), 3),
            "bias_in":      round(bias, 3),
            "rmse_in":      round(rmse, 3),
            "mae_in":       round(mae, 3),
            "pod":          round(pod, 3),
        })
    return results

def compute_spatial_bias(pairs: list) -> list:
    """Compute mean MESH/SPC ratio on 1° grid."""
    cells = defaultdict(list)
    for p in pairs:
        if p["spc_size_in"] > 0 and p["mesh75_in"] > 0:
            lat_1 = int(p["lat"])
            lon_1 = int(p["lon"])
            cells[(lat_1, lon_1)].append(p["mesh75_in"] / p["spc_size_in"])

    results = []
    for (lat, lon), ratios in sorted(cells.items()):
        results.append({
            "lat_center":   lat + 0.5,
            "lon_center":   lon + 0.5,
            "n_reports":    len(ratios),
            "mean_ratio":   round(float(np.mean(ratios)), 3),
            "median_ratio": round(float(np.median(ratios)), 3),
        })
    return results

def write_summary(pairs: list, cal: list):
    """Write human-readable summary."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "validation_summary.txt"

    spc = np.array([p["spc_size_in"] for p in pairs])
    m75 = np.array([p["mesh75_in"] for p in pairs])

    # Detection stats
    severe_spc = spc >= 1.0
    severe_m75 = m75 >= 1.0
    hits = np.sum(severe_spc & severe_m75)
    misses = np.sum(severe_spc & ~severe_m75)
    false_alarms = np.sum(~severe_spc & severe_m75)
    pod = hits / max(hits + misses, 1)
    far = false_alarms / max(hits + false_alarms, 1)
    csi = hits / max(hits + misses + false_alarms, 1)

    # Night vs day
    night = [p for p in pairs if p.get("hour", 12) < 6 or p.get("hour", 12) >= 22]
    day   = [p for p in pairs if 6 <= p.get("hour", 12) < 22]
    night_det = np.mean([p["mesh75_mm"] > 0 for p in night]) if night else 0
    day_det   = np.mean([p["mesh75_mm"] > 0 for p in day]) if day else 0

    with open(path, "w") as f:
        f.write("MESH75 vs SPC Hail Reports — Validation Summary\n")
        f.write(f"{'='*60}\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Total report–MESH pairs: {len(pairs):,}\n")
        f.write(f"Date range: {pairs[0]['date']} to {pairs[-1]['date']}\n\n")

        f.write(f"Overall bias (MESH75 − SPC): {float(np.mean(m75 - spc)):+.3f} inches\n")
        f.write(f"Overall RMSE: {float(np.sqrt(np.mean((m75 - spc)**2))):.3f} inches\n")
        f.write(f"Overall correlation: {float(np.corrcoef(spc, m75)[0,1]):.3f}\n\n")

        f.write(f"Severe hail (>=1.0\") detection:\n")
        f.write(f"  POD: {pod:.3f}  FAR: {far:.3f}  CSI: {csi:.3f}\n")
        f.write(f"  Hits: {hits:,}  Misses: {misses:,}  False alarms: {false_alarms:,}\n\n")

        f.write(f"Diurnal coverage:\n")
        f.write(f"  Day (06–22 UTC) reports: {len(day):,}, MESH detection rate: {day_det:.1%}\n")
        f.write(f"  Night (22–06 UTC) reports: {len(night):,}, MESH detection rate: {night_det:.1%}\n\n")

        f.write(f"Calibration by size bin:\n")
        f.write(f"{'Bin':<14} {'N':>6} {'SPC':>7} {'MESH75':>7} {'Bias':>7} {'RMSE':>7} {'POD':>6}\n")
        f.write(f"{'-'*55}\n")
        for c in cal:
            if c["n"] > 0:
                f.write(f"{c['bin']:<14} {c['n']:>6} {c['mean_spc_in']:>7.2f} "
                        f"{c['mean_mesh_in']:>7.2f} {c['bias_in']:>+7.3f} "
                        f"{c['rmse_in']:>7.3f} {c['pod']:>6.3f}\n")

    log(f"  Summary written to {path.name}")

def make_figures(pairs: list):
    """Generate diagnostic figures."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        log("  WARN: matplotlib not available, skipping figures")
        return

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    spc = np.array([p["spc_size_in"] for p in pairs])
    m75 = np.array([p["mesh75_in"] for p in pairs])

    # 1. Scatter plot
    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    ax.hexbin(spc, m75, gridsize=50, cmap="YlOrRd", mincnt=1)
    ax.plot([0, 6], [0, 6], "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("SPC Reported Hail Size (inches)")
    ax.set_ylabel("MESH75 (inches)")
    ax.set_title("MESH75 vs SPC Ground Reports")
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 6)
    ax.legend()
    plt.colorbar(ax.collections[0], ax=ax, label="Count")
    fig.savefig(FIG_DIR / "mesh_vs_spc_scatter.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2. Detection rate by size
    bins_edges = [0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0]
    pod_vals = []
    bin_labels = []
    for j in range(len(bins_edges) - 1):
        mask = (spc >= bins_edges[j]) & (spc < bins_edges[j+1])
        if np.sum(mask) > 10:
            pod_vals.append(np.mean(m75[mask] > 0))
            bin_labels.append(f"{bins_edges[j]:.1f}-{bins_edges[j+1]:.1f}")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(range(len(pod_vals)), pod_vals)
    ax.set_xticks(range(len(pod_vals)))
    ax.set_xticklabels(bin_labels, rotation=45)
    ax.set_ylabel("MESH75 Detection Rate (POD)")
    ax.set_title("MESH75 Detection Rate by SPC Reported Hail Size")
    ax.set_ylim(0, 1)
    fig.savefig(FIG_DIR / "detection_by_size.png", dpi=150, bbox_inches="tight")
    plt.close()

    log(f"  Figures saved to {FIG_DIR}")

def validate_outputs() -> bool:
    """Validate outputs exist and are reasonable."""
    errors = []
    for fname in ["mesh_vs_spc_pairs.csv", "calibration_report.csv", "validation_summary.txt"]:
        p = OUT_DIR / fname
        if not p.exists():
            errors.append(f"Missing: {fname}")
        elif p.stat().st_size == 0:
            errors.append(f"Empty: {fname}")

    if errors:
        log("Validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True

def main():
    parser = argparse.ArgumentParser(description="Validate MESH75 against SPC reports.")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log(f"  MESH vs SPC Validation — Stage 06")
    log(f"{'='*60}")

    # Build pairs
    log("\n[1/4] Building report–MESH pairs")
    pairs = build_pairs()
    if not pairs:
        log("  ERROR: No pairs found. Check SPC and MESH data paths.")
        sys.exit(1)

    # Write pairs CSV
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pairs_path = OUT_DIR / "mesh_vs_spc_pairs.csv"
    fields = ["date", "lat", "lon", "spc_size_in", "mesh75_mm", "mesh75_in",
              "grid_row", "grid_col", "hour"]
    with open(pairs_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(pairs)
    log(f"  Wrote {len(pairs):,} pairs to {pairs_path.name}")

    # Calibration report
    log("\n[2/4] Computing calibration statistics")
    cal = compute_calibration(pairs)
    cal_path = OUT_DIR / "calibration_report.csv"
    with open(cal_path, "w", newline="") as f:
        fieldnames = sorted({k for row in cal for k in row.keys()})
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(cal)

    # Spatial bias
    log("\n[3/4] Computing spatial bias")
    spatial = compute_spatial_bias(pairs)
    sp_path = OUT_DIR / "spatial_bias_1deg.csv"
    if spatial:
        with open(sp_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(spatial[0].keys()))
            w.writeheader()
            w.writerows(spatial)

    # Summary + figures
    write_summary(pairs, cal)

    log("\n[4/4] Generating figures")
    make_figures(pairs)

    log(f"\n{'='*60}")
    log(f"  Validation complete")
    log(f"{'='*60}\n")

    ok = validate_outputs()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
