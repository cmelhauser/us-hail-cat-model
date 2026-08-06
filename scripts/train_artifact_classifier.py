#!/usr/bin/env python3
"""
Train an optional research geometry-aware hail-likelihood classifier.

Uses Stage 06 SPC–MESH pairs as weak positive hail labels and samples high-MESH
no-report cells as weak negatives. A no-report cell is not established ground
truth for an artifact. The model is therefore research-only, trained on GridRad
days by default, and evaluated with whole years held out. It must not be treated
as independent SPC validation.

Usage (repo root, after Stage 06):
  .venv/bin/python scripts/train_artifact_classifier.py
  .venv/bin/python scripts/train_artifact_classifier.py --max-neg-per-day 200
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts._artifact_features import (
    ARTIFACT_FEATURE_NAMES,
    build_feature_matrix,
    build_single_cell_features,
    local_median_3x3,
)
from scripts._config import DATA_ROOT, MODEL_VERSION
from scripts._radar_geometry import (
    azimuth_to_nearest_site_deg,
    classify_mesh_source_from_yyyymmdd,
    ensure_nearest_site_index_grid,
    ensure_range_km_grid,
)

PAIRS_PATH = DATA_ROOT / "historical" / "validation" / "mesh_vs_spc_pairs.csv"
CORRECTED_DIR = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
CAL_DIR = DATA_ROOT / "analysis" / "calibration"
OUT_MODEL = CAL_DIR / "artifact_classifier.pkl"
OUT_DIAG = CAL_DIR / "artifact_classifier_diagnostics.json"
MIN_SEVERE_IN = 1.0
MIN_MESH_POS_MM = 25.4
MIN_MESH_NEG_MM = 29.0
RNG_SEED = 42


def _load_raster(datestr: str) -> np.ndarray | None:
    for base in (CORRECTED_DIR, DATA_ROOT / "historical" / "mesh_0.05deg"):
        year = datestr[:4]
        path = base / year / f"mesh_{datestr}.tif"
        if path.is_file():
            with rasterio.open(path) as src:
                return src.read(1).astype(np.float32)
    return None


def build_training_sets(
    pairs: pd.DataFrame,
    *,
    max_neg_per_day: int,
    rng: np.random.Generator,
    gridrad_only: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    reported_by_date: dict[str, set[tuple[int, int]]] = defaultdict(set)
    pos_keys: list[tuple[str, int, int]] = []
    for row in pairs.itertuples(index=False):
        key = (int(row.grid_row), int(row.grid_col))
        reported_by_date[str(row.date)].add(key)
        if float(row.spc_size_in) >= MIN_SEVERE_IN and float(row.mesh75_mm) >= MIN_MESH_POS_MM:
            pos_keys.append((str(row.date), key[0], key[1]))

    range_km = ensure_range_km_grid()
    ensure_nearest_site_index_grid()
    azimuth = azimuth_to_nearest_site_deg()

    X_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    group_parts: list[np.ndarray] = []
    dates = sorted(reported_by_date.keys())
    cache: dict[str, np.ndarray | None] = {}

    for datestr in dates:
        if datestr not in cache:
            cache[datestr] = _load_raster(datestr)
        raster = cache[datestr]
        if raster is None:
            continue
        doy = datetime.strptime(datestr, "%Y%m%d").timetuple().tm_yday
        source = classify_mesh_source_from_yyyymmdd(datestr)
        if gridrad_only and source != "GridRad":
            continue
        feats, active = build_feature_matrix(
            raster,
            range_km=range_km,
            azimuth_deg=azimuth,
            day_of_year=doy,
            source=source,
            active_mm=MIN_MESH_NEG_MM,
        )
        if feats.size == 0:
            continue
        flat_active = np.flatnonzero(active)
        reported = reported_by_date[datestr]
        neg_sel = []
        for fi, flat_cell in enumerate(flat_active):
            r, c = divmod(int(flat_cell), raster.shape[1])
            if (r, c) not in reported:
                neg_sel.append(fi)
        if not neg_sel:
            continue
        neg_idx_arr = np.array(neg_sel, dtype=np.int64)
        if neg_idx_arr.size > max_neg_per_day:
            neg_idx_arr = rng.choice(neg_idx_arr, size=max_neg_per_day, replace=False)
        X_parts.append(feats[neg_idx_arr])
        y_parts.append(np.zeros(neg_idx_arr.size, dtype=np.int8))
        group_parts.append(np.full(neg_idx_arr.size, datestr, dtype="U8"))

    med_cache: dict[str, np.ndarray] = {}
    for datestr, row, col in pos_keys:
        if datestr not in cache:
            cache[datestr] = _load_raster(datestr)
        raster = cache[datestr]
        if raster is None:
            continue
        cell_mesh = float(raster[row, col])
        if cell_mesh < MIN_MESH_POS_MM:
            continue
        if datestr not in med_cache:
            med_cache[datestr] = local_median_3x3(raster)
        doy = datetime.strptime(datestr, "%Y%m%d").timetuple().tm_yday
        source = classify_mesh_source_from_yyyymmdd(datestr)
        if gridrad_only and source != "GridRad":
            continue
        X_parts.append(
            build_single_cell_features(
                cell_mesh,
                float(range_km[row, col]),
                float(azimuth[row, col]),
                float(med_cache[datestr][row, col]),
                doy,
                source,
            ).reshape(1, -1)
        )
        y_parts.append(np.ones(1, dtype=np.int8))
        group_parts.append(np.array([datestr], dtype="U8"))

    if not X_parts:
        raise RuntimeError("No training samples built; run Stage 06 and ensure corrected rasters exist.")
    X = np.vstack(X_parts)
    y = np.concatenate(y_parts)
    groups = np.concatenate(group_parts)
    return X, y, groups


def train_classifier(X: np.ndarray, y: np.ndarray, groups: np.ndarray):
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupShuffleSplit

    years = np.asarray([str(group)[:4] for group in groups])
    if len(np.unique(years)) < 2:
        raise RuntimeError("Classifier evaluation requires samples from at least two years.")
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RNG_SEED)
    train_idx, test_idx = next(splitter.split(X, y, groups=years))
    X_tr, X_te = X[train_idx], X[test_idx]
    y_tr, y_te = y[train_idx], y[test_idx]
    if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
        raise RuntimeError("Year holdout must contain both weak-label classes.")
    model = GradientBoostingClassifier(
        random_state=RNG_SEED,
        max_depth=4,
        n_estimators=200,
        learning_rate=0.05,
        subsample=0.8,
    )
    model.fit(X_tr, y_tr)
    prob = model.predict_proba(X_te)[:, 1]
    auc = float(roc_auc_score(y_te, prob)) if len(np.unique(y_te)) > 1 else float("nan")
    return model, {
        "n_train": int(len(y_tr)),
        "n_test": int(len(y_te)),
        "roc_auc": auc,
        "split": "grouped_by_year",
        "train_years": sorted(set(years[train_idx].tolist())),
        "holdout_years": sorted(set(years[test_idx].tolist())),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Train research SPC-weak-label hail-likelihood classifier."
    )
    parser.add_argument("--pairs", type=Path, default=PAIRS_PATH)
    parser.add_argument("--max-neg-per-day", type=int, default=150)
    parser.add_argument("--output", type=Path, default=OUT_MODEL)
    parser.add_argument(
        "--include-all-sources",
        action="store_true",
        help="Research only: include MYRORSS/MRMS in addition to default GridRad samples.",
    )
    args = parser.parse_args(argv)

    if not args.pairs.is_file():
        raise FileNotFoundError(f"Missing pairs file: {args.pairs} (run Stage 06 first)")

    pairs = pd.read_csv(args.pairs)
    rng = np.random.default_rng(RNG_SEED)
    X, y, groups = build_training_sets(
        pairs,
        max_neg_per_day=args.max_neg_per_day,
        rng=rng,
        gridrad_only=not args.include_all_sources,
    )
    model, metrics = train_classifier(X, y, groups)

    CAL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "feature_names": list(ARTIFACT_FEATURE_NAMES),
        "model_version": MODEL_VERSION,
        "trained": datetime.now().isoformat(timespec="seconds"),
        "metrics": metrics,
        "n_samples": int(len(y)),
        "positive_rate": float(y.mean()),
        "label_semantics": "1=SPC-collocated likely hail; 0=no-report weak negative",
        "data_role": "research_tuning_not_independent_validation",
        "sources": "all" if args.include_all_sources else "GridRad",
    }
    with open(args.output, "wb") as f:
        pickle.dump(payload, f)
    OUT_DIAG.write_text(json.dumps({k: v for k, v in payload.items() if k != "model"}, indent=2))
    print(f"Wrote {args.output} ({len(y):,} samples, ROC-AUC={metrics['roc_auc']:.3f})")
    print(f"Diagnostics → {OUT_DIAG}")


if __name__ == "__main__":
    main()
