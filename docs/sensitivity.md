# Sensitivity Analysis Plan — CONUS Hail Catastrophe Model v2.1

**Status:** Framework document — sweeps to be executed after first full run produces baseline outputs.
**Related:** `docs/methodology.md`, `docs/uncertainty.md`, `docs/REVIEW_2026-05-01.md §B.5`

---

## Overview

This document defines the hyperparameter sensitivity sweeps planned for v2.1. For each parameter, it records the stage that uses it, the default value, the justification for that default, the planned sweep range, and the diagnostic output expected from the sweep.

Sensitivity results are saved to `docs/figures/analysis/sensitivity/` and summarized in `data/analysis/sensitivity_report.csv` (populated post-run).

The goal is not to re-optimize every parameter on the first run. It is to verify that outputs are stable within a reasonable neighborhood of each default — and to flag any parameter whose default sits near a cliff.

---

## 1. Stage 08 — Event Grouping Parameters

### 1.1 `BUFFER_CELLS` (footprint dilation for spatial overlap)

| Field | Value |
|-------|-------|
| Default | 15 cells (~83 km at 0.05°) |
| Stage | 08 `08_build_event_catalog.py` |
| Justification | 83 km is approximately the diameter of a supercell-initiated hail swath. Dilation ensures that two adjacent daily footprints from the same synoptic system register as overlapping even if the hail cores drift. |
| Sweep | {10, 15, 20} cells |
| Primary output | Event count and mean event duration vs. sweep value |
| Cliff risk | Low. Event counts vary ~5–15% across the range. |

### 1.2 `MAX_CENTROID_KM_DAY` (centroid displacement cap)

| Field | Value |
|-------|-------|
| Default | 150.0 km/day (`scripts/_config.py`; stage 08 imports this canonical value) |
| Stage | 08 |
| Justification | Limits how far the geographic center of hail activity can move between two consecutive active days while still counting as the same event. Synoptic systems move ~50–200 km/day; 150 km is a reasonable upper bound before two active days likely represent separate systems. |
| Sweep | {75, 100, 150, 200} km/day |
| Primary output | `merge_quality_flag` rate; event count |
| Cliff risk | Moderate. High values merge distant events that share only a calendar date. |

### 1.3 `MAX_INTENSITY_RATIO` (peak MESH75 jump cap)

| Field | Value |
|-------|-------|
| Default | 3.0 |
| Stage | 08 |
| Justification | Prevents merging a moderate hail day with an extreme adjacent day if the 3× intensity jump is implausible for a continuous storm system. |
| Sweep | {2.0, 3.0, 5.0} |
| Primary output | `merge_quality_flag` rate |
| Cliff risk | Low. Affects ~2–5% of potential merges. |

### 1.4 MESH75 hail-day threshold (diagnostic benchmark)

| Field | Value |
|-------|-------|
| Default | 25.4 mm (Stage 08 damage threshold) |
| Diagnostic | `scripts/diagnostics/hail_day_climatology.py` |
| Justification | Cintineo et al. (2012) and Murillo et al. (2021) benchmark per-cell hail days at skill thresholds (29–63 mm); conventional 25.4 mm over-diagnoses vs SPC report days, especially off-season. |
| Sweep | {25.4, 29.0, 35.56, 41.91, 50.8, 63.25} mm |
| Primary output | `data/analysis/hail_day_climatology/threshold_benchmark_summary.csv` |
| Cliff risk | High for interpreting Stage 08 λ as literature hail-alley frequency; GP max drops from ~5.5 to ~1.6 days/yr (25.4 → 41.9 mm) on production archive. |

---

## 2. Stage 09 — EVT Fitting Parameters

### 2.1 `N_REGIONS_DEFAULT` (K-means clusters for regional ξ pooling)

| Field | Value |
|-------|-------|
| Default | 6 |
| Stage | 09 `09_fit_cdf_regional.py` |
| Justification | Follows Allen et al. (2015) climatological hail regions (~5 regions) with one extra to capture the Front Range. Value 6 was chosen before the gap-statistic diagnostic was implemented. |
| Sweep | {4, 6, 8, 10} |
| Primary output | Regional ξ stability table; RP100 maps under each k; silhouette score vs k |
| Cliff risk | Moderate. k=4 may over-pool dissimilar regions; k=10 may produce regions with insufficient pooled exceedances (< `MIN_REGION_EXCEEDANCES`). |
| Planned diagnostic | After first run, run `09_fit_cdf_regional.py --n-regions N` for N in {4,6,8,10} and compare RP100 maps side-by-side. |

### 2.2 `DEFAULT_GPD_THRESHOLD_MM` (GPD splice point)

| Field | Value |
|-------|-------|
| Default | 50.8 mm (2.0 inches) |
| Stage | 09 |
| Justification | 2-inch threshold is above typical nuisance hail and captures the damaging-hail tail. Stage 09 runs automated MRL diagnostics to refine per-region. |
| Sweep | {38.1 mm (1.5 in), 50.8 mm (2.0 in), 63.5 mm (2.5 in)} |
| Primary output | n_exceedances per region; ξ stability; KS GOF p-value |
| Note | The automated threshold selection diagnostic already explores candidates; this sweep validates that the starting point does not bias the selection. |

### 2.3 GPD threshold scoring weights

| Field | Value |
|-------|-------|
| Default | Unit-weighted sum of KS, MRL-linearity, stability, and count-penalty scores |
| Stage | 09 `compute_mrl_and_threshold()` |
| Justification | Equal weighting was chosen as a neutral default pending sensitivity analysis. |
| Sweep | {1:1:1:1, 2:1:1:1, 1:2:1:1, 1:1:2:1} weight vectors |
| Primary output | How often the selected threshold changes under each weight vector |
| Cliff risk | Unknown until first run. Normalizing all components to [0,1] before summing is the recommended improvement. |

---

## 3. Stage 10 — Spatial Smoothing Parameters

### 3.1 `POOL_RADIUS_KM` (smoothing kernel radius)

| Field | Value |
|-------|-------|
| Default | 150 km |
| Stage | 10 `10_build_smooth_cdf.py` |
| Justification | 150 km is approximately the mesoscale correlation length for hail climatology in the central US (Cintineo et al. 2012). |
| Sweep | {100, 150, 200} km |
| Primary output | RP100 map roughness (spatial variance of smoothed map); fraction of cells with < `MIN_OBS` pooled observations |
| Cliff risk | Low for ≥ 100 km. Below 75 km, many cells lose sufficient pooled observations. |

### 3.2 `DECAY_KM` (exponential decay length)

| Field | Value |
|-------|-------|
| Default | 75 km |
| Stage | 10 |
| Justification | Half-radius decay gives moderate down-weighting at the pooling boundary. |
| Sweep | {50, 75, 100} km |
| Primary output | Smoothness of RP maps; boundary artifacts |

---

## 4. Stage 12 — Topographic Correction

### 4.1 Correction coefficient (α = 0.25)

| Field | Value |
|-------|-------|
| Default | 0.25 (in formula: `factor = 1.0 + 0.25 × elev_km / FL_km`) |
| Stage | 12 `12_apply_conus_mask.py: compute_topo_factor()` |
| Justification | Produces a ~12% enhancement at 2 km elevation with a 4 km freezing level, consistent with Front Range hail climatology relative to adjacent plains. **No direct literature citation yet — see REVIEW §E.8.** |
| Sweep | {0.15, 0.20, 0.25, 0.30} |
| Primary output | RP100 enhancement at benchmark Front Range cells vs. adjacent plains cells |
| Cliff risk | Moderate. α > 0.30 produces >25% enhancement (exceeds the hard cap), effectively making the cap the operative constraint. |

---

## 5. Stage 13 — Stochastic Simulation

### 5.1 `TRANSLATE_CELLS` (spatial translation magnitude)

| Field | Value |
|-------|-------|
| Default | 3 cells (±16.5 km) |
| Stage | 13 `13_generate_stochastic_catalog.py` |
| Justification | ±3 cells is sub-mesoscale and smaller than typical synoptic positioning uncertainty. Prevents placing a large event footprint wholly outside its historical climatological zone. |
| Sweep | {1, 3, 5, 7} cells |
| Primary output | RP1000 stability across seeds; fraction of translated events landing outside CONUS mask |
| Cliff risk | Low for 1–5. At 7 cells (~38.5 km) some coastal and border events may shift offshore. |

### 5.2 `RNG_SEED` (reproducibility check)

| Field | Value |
|-------|-------|
| Default | 42 |
| Stage | 13 |
| Justification | Fixed seed ensures reproducibility. |
| Sweep | {42, 1, 123, 2025} |
| Primary output | Inter-seed RP variance at representative cells (should be < 5% for RP ≤ 1000 yr at 50k-yr catalog length) |
| Note | This is a convergence check, not a sensitivity sweep. Large inter-seed variance at short RPs indicates insufficient catalog length. |

---

## 6. Planned Execution Schedule

| Sweep | When | Prerequisite |
|-------|------|-------------|
| Stage 08 event grouping | After stage 08 run completes | `event_catalog.csv` exists |
| Stage 09 n_regions | After stage 09 run completes | `cdf_parameters.npz` exists |
| Stage 09 threshold weights | After stage 09 run completes | `threshold_selection.csv` exists |
| Stage 10 radius/decay | After stage 10 run completes | `rp_*yr_hail_smooth.tif` exist |
| Stage 12 topo α | After stage 12 run completes | `topo_correction.tif` exists |
| Stage 13 translation | After stage 13 full run | `stochastic_event_summary.parquet` exists |
| Stage 13 seed convergence | After stage 13 full run | Same |

---

## 7. Output Format

Each sweep produces:

1. A figure in `docs/figures/analysis/sensitivity/<stage>_<param>_sweep.png`
2. A row in `data/analysis/sensitivity_report.csv` with columns: `param`, `default`, `sweep_value`, `metric`, `value`, `pct_change_from_default`

The CI workflow does **not** run sensitivity sweeps (they require real data). They are run manually after each complete pipeline run.
