# Benchmarks — Published RP Comparison Framework

**CONUS Hail Catastrophe Model v2.1**
**Status:** Framework document — comparisons to be executed after first full run produces RP maps.
**Related:** `docs/methodology.md`, `docs/uncertainty.md`, `docs/sensitivity.md`, `docs/REVIEW_2026-05-01.md §B.6`

---

## Overview

This document defines the post-run benchmarking framework for v2.1. Benchmarking answers a different question from sensitivity analysis: not "are outputs stable near the default parameters?" but "are outputs plausible in absolute terms, given what the literature reports?"

The benchmark suite does not require a published dataset with identical return periods and grid resolution. It requires that the model's outputs be comparable in direction, order of magnitude, and regional pattern to independently derived estimates.

Benchmark failures (large systematic mismatches) indicate model miscalibration, EVT misspecification, or a grid/unit error. Benchmark agreement does not validate the model — sources, periods, and methods differ — but it raises confidence that the outputs are in the right ballpark.

All comparison figures are saved to `docs/figures/analysis/benchmarks/`.

---

## 1. Published Hail Frequency Benchmarks

### 1.1 Cintineo et al. (2012) — NEXRAD MESH climatology

**Source:** Cintineo, J. M., T. M. Smith, V. Lakshmanan, H. E. Brooks, and K. L. Ortega, 2012: An objective high-resolution hail climatology of the contiguous United States. *Wea. Forecasting*, 27, 1235–1248.

**Benchmark metric:** Annual probability of exceeding MESH ≥ 25 mm (≈ 1 inch) per 0.5° grid cell.

**Comparison approach:**
1. Aggregate v2.1 Stage 11 exceedance probabilities from 0.05° to 0.5° using cell-area-weighted mean.
2. Visually compare the resulting map to Figure 3 or equivalent in Cintineo et al.
3. Flag any region where v2.1 annual exceedance rate differs by more than a factor of 2 from the published climatology.

**Expected pattern:** Peak activity in the central Great Plains (Kansas, Nebraska, eastern Colorado, Oklahoma), secondary maximum in Midwest corridor, lower probabilities in Southeast and Northwest.

**Known differences:** Cintineo et al. (2012) uses NEXRAD MESH without the Murillo-Homeyer correction and covers a different period. Expect v2.1 to report lower values for equivalent size thresholds after the MESH75 correction, which compresses the extreme tail of the raw-MESH distribution.

---

### 1.2 Murillo, Homeyer, and Allen (2021) — GridRad hail climatology

**Source:** Murillo, E. M., C. R. Homeyer, and J. T. Allen, 2021: A 22-year severe hail climatology using GridRad MESH observations. *Mon. Wea. Rev.*, 149, 945–958.

**Benchmark metric:** Annual severe hail day frequency (days with MESH ≥ 25 mm) per 1° grid cell, 1998–2019.

**Comparison approach:**
1. Compute v2.1 annual severe-hail-day frequency from Stage 07 climatology output at 1° aggregation.
2. Compare to Figure 1 or Table 1 in Murillo et al. (2021).
3. Report mean absolute error (MAE) across the High Plains and central US core, where coverage is most complete.

**Expected pattern:** Broad hail maximum across the Great Plains and central US, 5–15 hail days per year at the climatological core. Reduced frequency along western mountain ranges and coastlines.

**Known differences:** GridRad is one of three sources in v2.1; the other two (MYRORSS, MRMS) are not part of the Murillo (2021) climatology. The comparison is most meaningful for the 2012–2019 overlap period.

---

### 1.3 Wendt and Jirak (2021) — MRMS MESH climatology

**Source:** Wendt, N. A., and I. L. Jirak, 2021: An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports. *Wea. Forecasting*, 36, 645–659.

**Benchmark metric:** Annual frequency of MRMS MESH ≥ 50 mm (significant severe hail) per 0.1° grid cell, 2015–2019.

**Comparison approach:**
1. Aggregate v2.1 Stage 07 MRMS-only annual frequency to 0.1° for the 2020–present period.
2. Compare regional pattern of Stage 11 exceedance probabilities for the 50 mm threshold.
3. Confirm that the MRMS-era v2.1 outputs are directionally consistent with the Wendt-Jirak pattern.

**Caveat:** The v2.1 MRMS record starts October 2020, which is shorter than the Wendt-Jirak analysis period. Treat as directional validation only.

---

## 2. Return-Period Benchmarks

### 2.1 Swiss Re / RMS industry estimates (qualitative)

Published commercial model outputs are proprietary and cannot be directly compared. However, industry presentations and academic partner papers occasionally report aggregate annual hail losses or indicative RP maps for the US.

**Benchmark approach:** After first run, solicit informal comparison with industry practitioners to verify that v2.1 RP100 hail sizes in the Great Plains core (e.g., central Kansas) are in the range of 60–90 mm. This range is derived from literature-consistent extrapolation, not a single authoritative source.

**Cliff test:** If RP100 at any non-coastal CONUS cell exceeds 150 mm or is below 25 mm, that cell is a candidate for diagnostic review.

---

### 2.2 Spatial extent and shape plausibility

**Benchmark:** Visually compare v2.1 RP50, RP100, and RP500 maps to the hail-day frequency climatology from Cintineo et al. (2012) and Murillo et al. (2021). The high-return-period contours should approximately follow the climatological high-frequency zones, not appear as disconnected islands.

**Diagnostic:** Compute the Spearman rank correlation between the v2.1 RP100 map and the Stage 07 annual exceedance frequency map. Expected value: ≥ 0.70. Values below 0.50 suggest spatial anomalies in the EVT fitting or smoothing.

---

### 2.3 Analytical vs stochastic RP divergence

**Reference:** `docs/methodology.md §2.4`, `docs/uncertainty.md §6`.

This is the most important internal benchmark. Analytical and stochastic RP maps are derived from different model paths (EVT CDF vs event-resampling). Their agreement validates internal consistency.

**Diagnostic thresholds:**

| Return Period | Expected divergence | Flag threshold |
|---|---|---|
| RP10 | < 5% | > 15% |
| RP50 | < 10% | > 25% |
| RP100 | < 15% | > 35% |
| RP500 | < 25% | > 50% |
| RP1000+ | Can diverge | Log and review |

Divergence above the flag threshold at RP ≤ 500 yr is a P0 model-risk item requiring manual review before reporting.

**Stage 15 renders this comparison.** The benchmark is met when Stage 15 produces a flagged-cell count below 5% of CONUS land cells for RP ≤ 500 yr.

---

## 3. Regional Sanity Checks

### 3.1 High Plains core

**Region:** Central Kansas / Oklahoma (lat 36–40°N, lon 98–102°W)
**Expected RP50 MESH75:** 45–70 mm
**Expected RP100 MESH75:** 55–90 mm
**Rationale:** The High Plains is the climatological hail core. Any model producing RP100 < 30 mm or > 120 mm here has a likely calibration or EVT error.

### 3.2 Northern Front Range

**Region:** Eastern Colorado / Wyoming (lat 40–43°N, lon 103–106°W)
**Expected RP100 MESH75:** 50–80 mm
**Rationale:** Known hail corridor. Topographic correction should increase values relative to the adjacent plains; Stage 12 benchmark is that the topo-corrected RP100 is 5–15% higher than the uncorrected value at benchmark cells above 1.5 km elevation.

### 3.3 Southeast US

**Region:** Alabama / Mississippi / Georgia (lat 32–36°N, lon 85–92°W)
**Expected RP100 MESH75:** 25–50 mm
**Rationale:** Southeast hail is real but less extreme than Great Plains. Return levels should be meaningfully lower than the High Plains core.

### 3.4 Pacific Coast and Northeast

**Region:** California coast, New England coast
**Expected behavior:** Annual occurrence probability near zero; RP maps should show very low values or be masked by the CONUS mask where land fractions are low.

---

## 4. Source-Transition Benchmarks

### 4.1 2011/2012 transition (MYRORSS → GridRad)

**Benchmark:** The corrected annual 90th-percentile MESH75 in the CONUS core should not jump by more than 15% between the final MYRORSS year (2011) and the first GridRad year (2012).

**Diagnostic:** Stage 06 produces a year-by-year source-stratified summary. Extract the annual P90 MESH75 series and run a Kolmogorov-Smirnov test on the two-year windows bracketing 2012. Flag if p < 0.05.

### 4.2 2019/2020 transition (GridRad → MRMS)

Same as 4.1 for the 2019–2020 boundary.

---

## 5. Execution Schedule

| Benchmark | When | Prerequisite |
|---|---|---|
| Cintineo frequency comparison | After Stage 07 runs | `hail_climo.tif` exists |
| Murillo frequency comparison | After Stage 07 runs | `hail_climo.tif` exists |
| Wendt-Jirak MRMS check | After Stage 07 runs | MRMS-era outputs exist |
| Source-transition KS test | After Stage 06 runs | `validation_mesh_vs_spc.csv` exists |
| Regional sanity checks (RP) | After Stage 12 runs | `rp_*yr_hail_final.tif` exist |
| Analytical vs stochastic RP divergence | After Stage 13 full run | Both RP map sets exist |
| Stage 15 divergence flag count | After Stage 15 runs | `rp_divergence_summary.csv` exists |

---

## 6. Output Format

Each benchmark produces:

1. A figure in `docs/figures/analysis/benchmarks/<benchmark_name>.png`
2. A row in `data/analysis/benchmark_report.csv` with columns: `benchmark`, `region`, `metric`, `observed_value`, `reference_value`, `reference_source`, `flag`

The `flag` column is `PASS`, `WARN`, or `FAIL` based on the thresholds defined in each section above.
