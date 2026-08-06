# Radar Artifact ML Plan (v2.3+)

Roadmap for separating NEXRAD geometry from meteorological hail signal before
long-return-period aggregation.

## Problem

Range rings and site spokes in **analytical and stochastic** return-period maps
indicate radar geometry baked into the Stage **05** daily archive—not a bug in
Stages **09–13**.

## Implemented tiers

### Tier 0 (v2.2.3)

| Item | Location |
|------|----------|
| GridRad native echo-frequency + clutter QC | `scripts/_gridrad_qc.py`, Stage **04c** |
| Site-specific WSR-88D remediation (default on) | `remove_gridrad_artifacts(site_remediation=True)` |
| 10 km azimuth range bins | `remove_azimuthal_ring_artifacts(edges=RADIAL_RING_BIN_EDGES_KM)` |

**Re-run:** Stage **04c** (GridRad gap-fill) + **05–14**.

### Tier 1 (v2.3.0)

| Item | Location |
|------|----------|
| Geometry feature builder | `scripts/_artifact_features.py` |
| SPC weak-label trainer (diagnostic) | `scripts/train_artifact_classifier.py` |
| Diagnostic classifier artifact | `data/analysis/calibration/artifact_classifier.pkl` |
| Ring metric on RP maps | `literature_validation_suite.py` → `rp_ring_energy` |

**Training** (after Stage **06**; diagnostic only — never applied to hazard rasters):

```bash
.venv/bin/python scripts/train_artifact_classifier.py
# or
.venv/bin/python scripts/05_apply_mesh_bias_correction.py --retrain-models
```

**Inference:** Stage **05** does **not** apply the classifier (or SPC-derived
range debias) to hazard rasters. SPC remains validation-only (AGENTS.md rule
#3). `--skip-ml` remains the deterministic reproducible baseline (AGENTS.md
rule #2).

### Tier 2 (v3.0 research)

Polar CNN / ConvLSTM ring segmenter on GridRad convective-day volume trees (Chilson
et al. 2019 analogue). Not in repository yet.

## Success metrics

| Metric | Target |
|--------|--------|
| `map_gridrad_minus_myrorss_mean_annual_max.png` | Visible ring reduction |
| GridRad speckle P95 | < 5% |
| SPC POD @ ≥ 1″ | Not degraded > 3% absolute |
| `rp_ring_energy` range-profile CV | ↓ vs prior version |
| Analytical vs stochastic 100-yr median ratio | ~1.1 (do not break tail physics) |

## Feature vector (artifact classifier)

`mesh_mm`, `log_mesh_mm`, `local_median_ratio`, `range_km`, `azimuth_sin`,
`azimuth_cos`, `month_sin`, `month_cos`, `era_gridrad`, `era_mrms`.

Labels: SPC severe reports (positive); high-MESH no-report cells (negative).

## Ablation plan (manuscript)

1. Rules only (`--skip-ml`, pre–v2.2.3 archive)
2. Rules + Tier 0 (v2.2.3 / v2.3.0 production path; no SPC hazard adjustments)
3. Diagnostic classifier trained and reviewed separately (does not alter Stage 05 rasters)

Compare ring maps, validation metrics, and RP peaks under fixed 0–10″ color scale.
