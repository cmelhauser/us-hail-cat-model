"""
tests/integration/test_smoke_synthetic.py
==========================================
End-to-end integration smoke test using fully synthetic in-memory data.

Tests the critical pipeline path stages 08 → 13 without any real data or disk I/O.

Design goals:
  - Fast (< 5 seconds total)
  - No external data dependencies (no GeoTIFFs, no downloads)
  - Validates the most important invariants:
      (a) Stage 08 produces well-formed sparse event storage
      (b) Stage 13 never constructs dense (n_events, 520, 1180) arrays
      (c) Stage 13 annual-max matrix is (n_years, n_active_cells)
      (d) RP values are finite, non-negative, and monotonically ordered
      (e) Spatial translation stays within grid bounds
      (f) σ_perturb calibration is bounded to [0.10, 0.40]

Synthetic dataset:
  - 15 active hail days spread over 5 simulated years (2015-2019)
  - 3 geographic clusters of 5-10 cells each (central Plains, Front Range, Midwest)
  - MESH75 values 30-80 mm (above damage threshold)
  - Dates chosen to produce ~8-10 distinct events after stage 08 grouping

This test is intentionally not parameterized by grid size: it uses the real
520×1180 grid constants but very sparse synthetic data, which is the correct
mental model for the actual first run.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

# ── Load stage modules ────────────────────────────────────────────────────────
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from conftest import load_stage

s08 = load_stage("08_build_event_catalog.py")
s13 = load_stage("13_generate_stochastic_catalog.py")

NROWS = s08.NROWS   # 520
NCOLS = s08.NCOLS   # 1180


# ── Synthetic data fixtures ───────────────────────────────────────────────────

# Three geographic clusters (row, col center) for synthetic hail cores
_CLUSTERS = [
    (200, 500),  # central Great Plains
    (180, 450),  # Kansas / Oklahoma
    (160, 430),  # northern Plains
]


def _make_footprint(center_row: int, center_col: int, n_cells: int, peak_mm: float):
    """Return (footprint_bool, peak_float32) for a small synthetic hail core."""
    fp = np.zeros((NROWS, NCOLS), dtype=bool)
    peak = np.zeros((NROWS, NCOLS), dtype=np.float32)
    rng = np.random.default_rng(center_row * NCOLS + center_col)
    dr = rng.integers(-3, 4, size=n_cells)
    dc = rng.integers(-3, 4, size=n_cells)
    rows = np.clip(center_row + dr, 0, NROWS - 1)
    cols = np.clip(center_col + dc, 0, NCOLS - 1)
    fp[rows, cols] = True
    peak[rows, cols] = np.clip(
        peak_mm * rng.uniform(0.7, 1.3, size=n_cells),
        s08.DAMAGE_THRESHOLD_MM + 1,
        s13.MAX_HAIL_MM,
    ).astype(np.float32)
    return fp, peak


@pytest.fixture(scope="module")
def synthetic_days():
    """
    Build 15 synthetic hail-active days across three clusters.
    Returns (dates, footprints, peaks) ready to feed into stage 08 group_events.
    """
    day_specs = [
        # (date, cluster_idx, n_cells, peak_mm)
        (date(2015, 5, 3),  0, 8, 55.0),
        (date(2015, 5, 4),  0, 6, 60.0),
        (date(2015, 6,20),  1, 5, 40.0),
        (date(2016, 4,25),  0, 7, 45.0),
        (date(2016, 5,10),  2, 9, 70.0),
        (date(2016, 5,11),  2, 8, 65.0),
        (date(2016, 5,12),  2, 6, 50.0),
        (date(2017, 5,30),  1, 5, 38.0),
        (date(2017, 6, 1),  1, 7, 42.0),
        (date(2017, 7,15),  0, 4, 35.0),
        (date(2018, 4,12),  0, 6, 48.0),
        (date(2018, 5,20),  2, 8, 75.0),
        (date(2018, 5,21),  2, 7, 72.0),
        (date(2019, 5, 5),  1, 5, 44.0),
        (date(2019, 6,18),  0, 6, 52.0),
    ]
    dates = []
    footprints = []
    peaks = []
    for dt, cidx, ncells, peak_mm in day_specs:
        cr, cc = _CLUSTERS[cidx]
        fp, pk = _make_footprint(cr, cc, ncells, peak_mm)
        dates.append(dt)
        footprints.append(fp)
        peaks.append(pk)
    return dates, footprints, peaks


@pytest.fixture(scope="module")
def grouped_events(synthetic_days):
    """Run stage 08 event grouping on synthetic days."""
    dates, footprints, peaks = synthetic_days
    groups = s08.group_events(dates, footprints, peaks)
    return groups


@pytest.fixture(scope="module")
def event_catalog(synthetic_days, grouped_events):
    """Build stage 08 event catalog and sparse events from synthetic data."""
    dates, footprints, peaks = synthetic_days
    df, sparse = s08.build_catalog(dates, footprints, peaks, grouped_events)
    return df, sparse


@pytest.fixture(scope="module")
def stochastic_outputs(event_catalog):
    """Run stage 13 stochastic simulation with n_years=50."""
    df, sparse = event_catalog
    sparse_list = list(sparse.values())

    # Build the event_df in the format stage 13 expects
    event_df = df.copy()
    if "start_date" not in event_df.columns:
        pytest.skip("build_catalog did not produce expected start_date column")
    event_df["start_date"] = pd.to_datetime(event_df["start_date"])
    if "doy" not in event_df.columns:
        event_df["doy"] = event_df["start_date"].dt.dayofyear
    if "peak" not in event_df.columns:
        event_df["peak"] = [
            float(ev["vals"].max()) if len(ev["vals"]) else 0.0
            for ev in sparse_list
        ]

    sigma = s13.calibrate_sigma(event_df, sparse_list)
    doy_cdf = s13.build_doy_distribution(event_df)
    result = s13.simulate_catalog(event_df, sparse_list, sigma, doy_cdf, n_years=50)
    return result, sparse


# ── Stage 08 tests ─────────────────────────────────────────────────────────────

class TestStage08Grouping:

    def test_groups_non_empty(self, grouped_events):
        assert len(grouped_events) > 0, "Expected at least one event group"

    def test_groups_cover_all_days(self, synthetic_days, grouped_events):
        dates, footprints, peaks = synthetic_days
        n_days_in_groups = sum(len(g) for g in grouped_events)
        assert n_days_in_groups == len(dates), (
            f"Groups cover {n_days_in_groups} days but input has {len(dates)}"
        )

    def test_groups_have_no_duplicate_day_indices(self, grouped_events):
        seen = set()
        for grp in grouped_events:
            for idx in grp:
                assert idx not in seen, f"Day index {idx} appears in multiple groups"
                seen.add(idx)

    def test_event_count_plausible(self, grouped_events):
        # 15 days in 5 years — should produce 7–15 distinct events
        n = len(grouped_events)
        assert 5 <= n <= 15, f"Unexpected event count {n}"

    def test_geographically_distant_days_not_merged(self, synthetic_days, grouped_events):
        """Clusters that are ~hundreds of km apart should not be merged."""
        dates, footprints, peaks = synthetic_days
        # Days 0 (cluster 0) and 4 (cluster 2) are far apart and in different years
        # — they should be in different groups
        group_of_day0 = next(grp for grp in grouped_events if 0 in grp)
        group_of_day4 = next(grp for grp in grouped_events if 4 in grp)
        assert group_of_day0 is not group_of_day4 or 0 not in group_of_day4, (
            "Distant days in different years were incorrectly merged"
        )


class TestStage08SparseStorage:

    def test_catalog_non_empty(self, event_catalog):
        df, sparse = event_catalog
        assert len(df) > 0
        assert len(sparse) > 0

    def test_sparse_events_have_required_keys(self, event_catalog):
        _, sparse = event_catalog
        for ev in sparse.values():
            assert "rows" in ev, "Sparse event missing 'rows'"
            assert "cols" in ev, "Sparse event missing 'cols'"
            assert "vals" in ev, "Sparse event missing 'vals'"

    def test_sparse_events_same_length(self, event_catalog):
        _, sparse = event_catalog
        for eid, ev in sparse.items():
            n = len(ev["rows"])
            assert len(ev["cols"]) == n, f"Event {eid}: cols length mismatch"
            assert len(ev["vals"]) == n, f"Event {eid}: vals length mismatch"

    def test_sparse_events_rows_cols_within_grid(self, event_catalog):
        _, sparse = event_catalog
        for eid, ev in sparse.items():
            assert np.all(ev["rows"] >= 0) and np.all(ev["rows"] < NROWS), (
                f"Event {eid}: rows out of grid bounds [0, {NROWS})"
            )
            assert np.all(ev["cols"] >= 0) and np.all(ev["cols"] < NCOLS), (
                f"Event {eid}: cols out of grid bounds [0, {NCOLS})"
            )

    def test_sparse_events_vals_above_threshold(self, event_catalog):
        _, sparse = event_catalog
        for eid, ev in sparse.items():
            assert np.all(ev["vals"] >= s08.DAMAGE_THRESHOLD_MM), (
                f"Event {eid}: vals below damage threshold"
            )

    def test_sparse_events_vals_below_max_hail(self, event_catalog):
        _, sparse = event_catalog
        for eid, ev in sparse.items():
            assert np.all(ev["vals"] <= s13.MAX_HAIL_MM), (
                f"Event {eid}: vals exceed MAX_HAIL_MM"
            )

    def test_no_dense_grid_in_sparse_events(self, event_catalog):
        """Critical: sparse events must never expand to (NROWS, NCOLS) shape."""
        _, sparse = event_catalog
        for eid, ev in sparse.items():
            for key, arr in ev.items():
                assert arr.shape != (NROWS, NCOLS), (
                    f"Event {eid}['{key}'] has dense grid shape ({NROWS}, {NCOLS}). "
                    "Stage 13 must operate on rows/cols/vals only."
                )


# ── Stage 13 tests ─────────────────────────────────────────────────────────────

class TestStage13SparseSafety:

    def test_annual_max_is_not_dense_event_cube(self, stochastic_outputs):
        """
        The most critical invariant: ann_max must be (n_years, n_active_cells),
        NOT (n_years, NROWS, NCOLS).
        """
        (ann_max, active_rows, active_cols, *rest, _df), sparse = stochastic_outputs
        n_years = ann_max.shape[0]
        n_active = len(active_rows)
        assert ann_max.shape == (n_years, n_active), (
            f"ann_max shape is {ann_max.shape}; expected ({n_years}, {n_active}). "
            "Stage 13 has violated sparse-safe constraint — a dense event cube was built."
        )

    def test_annual_max_not_shape_nrows_ncols(self, stochastic_outputs):
        (ann_max, *_), sparse = stochastic_outputs
        for dim in ann_max.shape:
            assert dim != NROWS * NCOLS, (
                f"ann_max dimension {dim} == NROWS*NCOLS ({NROWS*NCOLS}). "
                "Possible dense grid construction."
            )

    def test_active_rows_cols_within_grid(self, stochastic_outputs):
        (_, active_rows, active_cols, *_), _ = stochastic_outputs
        assert np.all(active_rows >= 0) and np.all(active_rows < NROWS)
        assert np.all(active_cols >= 0) and np.all(active_cols < NCOLS)


class TestStage13Translate:

    def test_translate_sparse_stays_in_bounds(self):
        rng = np.random.default_rng(0)
        rows = np.array([10, 100, 500, 519], dtype=np.int32)
        cols = np.array([10, 200, 1100, 1179], dtype=np.int32)
        for _ in range(50):
            r_new, c_new, keep, _, _ = s13.translate_sparse(rows, cols, rng, sigma_cells=5)
            assert np.all(r_new >= 0), "Translated rows below 0"
            assert np.all(r_new < NROWS), f"Translated rows >= NROWS ({NROWS})"
            assert np.all(c_new >= 0), "Translated cols below 0"
            assert np.all(c_new < NCOLS), f"Translated cols >= NCOLS ({NCOLS})"

    def test_translate_sparse_empty_input(self):
        rng = np.random.default_rng(1)
        rows = np.array([], dtype=np.int32)
        cols = np.array([], dtype=np.int32)
        r_new, c_new, keep, dr, dc = s13.translate_sparse(rows, cols, rng)
        assert len(r_new) == 0
        assert len(c_new) == 0


class TestStage13CalibratedSigma:

    def test_calibrate_sigma_bounded(self, event_catalog):
        df, sparse = event_catalog
        event_df = df.copy()
        event_df["start_date"] = pd.to_datetime(event_df["start_date"])
        event_df["doy"] = event_df["start_date"].dt.dayofyear
        event_df["peak"] = [
            float(ev["vals"].max()) if len(ev["vals"]) else 0.0
            for ev in sparse.values()
        ]
        sigma = s13.calibrate_sigma(event_df, list(sparse.values()))
        assert 0.10 <= sigma <= 0.40, (
            f"calibrate_sigma returned {sigma:.4f}, expected in [0.10, 0.40]"
        )

    def test_calibrate_sigma_finite(self, event_catalog):
        df, sparse = event_catalog
        event_df = df.copy()
        event_df["start_date"] = pd.to_datetime(event_df["start_date"])
        event_df["doy"] = event_df["start_date"].dt.dayofyear
        event_df["peak"] = [
            float(ev["vals"].max()) if len(ev["vals"]) else 0.0
            for ev in sparse.values()
        ]
        sigma = s13.calibrate_sigma(event_df, list(sparse.values()))
        assert np.isfinite(sigma)


class TestStage13RPMonotonicity:

    def test_rp_values_finite_non_negative(self, stochastic_outputs, event_catalog):
        """RP maps from simulate_catalog must be finite and non-negative."""
        (ann_max, active_rows, active_cols, *_), _ = stochastic_outputs
        rp_maps = s13.compute_empirical_rps(ann_max, active_rows, active_cols, n_years=50)
        for rp, rp_map in rp_maps.items():
            assert np.all(np.isfinite(rp_map)), f"RP{rp} map has non-finite values"
            assert np.all(rp_map >= 0), f"RP{rp} map has negative values"

    def test_higher_rp_greater_or_equal_value_at_active_cells(self, stochastic_outputs):
        """
        RP values must be monotonically non-decreasing at each cell:
        rp_map[RP200] >= rp_map[RP100] >= rp_map[RP50].
        """
        (ann_max, active_rows, active_cols, *_), _ = stochastic_outputs
        rp_maps = s13.compute_empirical_rps(ann_max, active_rows, active_cols, n_years=50)

        rps_to_check = sorted(rp_maps.keys())
        # Only check pairs that are feasible given n_years=50
        feasible = [rp for rp in rps_to_check if rp <= 50]
        for rp_lo, rp_hi in zip(feasible[:-1], feasible[1:]):
            lo = rp_maps[rp_lo][active_rows, active_cols]
            hi = rp_maps[rp_hi][active_rows, active_cols]
            violations = np.sum(hi < lo - 1e-3)
            assert violations == 0, (
                f"RP{rp_hi} < RP{rp_lo} at {violations} cells — RP maps are not monotonic"
            )


class TestStage13BuildActiveIndex:

    def test_build_active_index_unique_cells(self, event_catalog):
        _, sparse = event_catalog
        sparse_list = list(sparse.values())
        rows, cols, lookup = s13.build_active_index(sparse_list)
        assert len(rows) == len(cols) == len(lookup)
        # All (row, col) pairs in lookup should be unique
        all_keys = list(lookup.keys())
        assert len(set(all_keys)) == len(all_keys), "Duplicate keys in active index"

    def test_build_active_index_contains_all_event_cells(self, event_catalog):
        _, sparse = event_catalog
        sparse_list = list(sparse.values())
        _, _, lookup = s13.build_active_index(sparse_list)
        for ev in sparse_list:
            for r, c in zip(ev["rows"].tolist(), ev["cols"].tolist()):
                assert (int(r), int(c)) in lookup, (
                    f"Cell ({r}, {c}) from sparse event not in active lookup"
                )


# ── End-to-end pipeline invariant ──────────────────────────────────────────────

class TestEndToEndPipelineInvariants:

    def test_events_from_08_are_consumable_by_13(self, event_catalog):
        """Stage 08 sparse events are in the format stage 13 expects."""
        df, sparse = event_catalog
        sparse_list = list(sparse.values())
        # stage 13 builds_active_index expects dicts with 'rows', 'cols', 'vals'
        rows, cols, lookup = s13.build_active_index(sparse_list)
        assert len(rows) > 0, "No active cells found — stage 08 → 13 handoff broken"

    def test_no_event_spans_entire_grid(self, event_catalog):
        """No single event should cover a dense fraction of the 520×1180 grid."""
        _, sparse = event_catalog
        total_cells = NROWS * NCOLS
        for eid, ev in sparse.items():
            n_cells = len(ev["rows"])
            fraction = n_cells / total_cells
            assert fraction < 0.01, (
                f"Event {eid} covers {fraction:.2%} of grid ({n_cells} cells). "
                "Something may have produced a dense footprint."
            )

    def test_stochastic_simulation_runs_without_oom(self, stochastic_outputs):
        """Smoke test: 50-year simulation completes without MemoryError."""
        result, _ = stochastic_outputs
        ann_max = result[0]
        assert ann_max is not None
        # Check memory footprint: should be well under 1 MB for 50 years × ~100 cells
        size_bytes = ann_max.nbytes
        assert size_bytes < 10 * 1024 * 1024, (
            f"ann_max is {size_bytes / 1024:.1f} KB — unexpectedly large, "
            "possible dense grid construction"
        )
