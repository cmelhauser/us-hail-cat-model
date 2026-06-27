# Uncertainty Budget — CONUS Hail Catastrophe Model v2.2

**Version:** 2.2.0  
**Status:** Framework document — quantitative bounds to be populated after first full run  
**Related:** `docs/methodology.md`, `docs/technical_documentation.md §09`

---

## Overview

Every probabilistic hazard estimate carries uncertainty. This document catalogues
the sources of uncertainty in the v2.2 model, characterises their expected
magnitude, and records the current treatment of each. It serves both as a
disclosure document for model users and as a roadmap for future uncertainty
quantification work.

Sources are grouped into six categories following standard catastrophe model
practice (Grossi & Kunreuther 2005; Mitchell-Wallace et al. 2017):

1. **Measurement uncertainty** — errors in the radar observations themselves
2. **Algorithmic uncertainty** — approximations introduced by the processing pipeline
3. **Sampling uncertainty** — finite record length limits tail estimation
4. **Model uncertainty** — the choice of statistical model and its parameters
5. **Stochastic uncertainty** — variability in the synthetic catalog
6. **Vulnerability uncertainty** — damage ratio curve errors

---

## 1. Measurement Uncertainty

### 1.1 Radar reflectivity error

Calibration uncertainty in WSR-88D reflectivity is typically ±1 dBZ (Bringi &
Chandrasekar 2001). For MYRORSS mosaic, network-wide calibration is performed
but residual bias exists at individual sites. The SHI integral is roughly linear
in reflectivity above the damage threshold, so a ±1 dBZ error propagates to
roughly ±5–10% in SHI and ±1–3 mm in MESH75 at moderate hail sizes.

**Current treatment:** Accepted as irreducible. No per-radar calibration
correction is applied beyond the MYRORSS compositing procedure.

### 1.2 MESH75 formula residuals

The Murillo & Homeyer (2021) MESH75 formula (`MESH75 = 15.096 × SHI^0.206`) was
fitted against observed hail reports. The paper reports RMS residuals of
approximately 15–20 mm over the training dataset. The formula explains roughly
40–60% of variance in observed maximum hail size at the storm level.

**Current treatment:** Formula residuals are not propagated through the pipeline.
They contribute to the uncertainty in annual maximum MESH75 at any given cell.
A formal propagation would require the joint distribution of (SHI error,
formula residual) across all active radar days.

**Recommended improvement (v2.2):** Apply bootstrapped uncertainty from Murillo
& Homeyer (2021) Fig. 8 to quantify formula-induced uncertainty on RP maps.

### 1.3 ERA5 isotherm interpolation error

ERA5 monthly 0°C and −20°C isotherm heights are used to compute the SHI
temperature weighting for GridRad days (Stage 04a). ERA5 horizontal resolution
is 0.25° vs the model grid of 0.05°; vertical resolution on pressure levels is
approximately 50–100 m near the freezing level. The Copernicus ERA5 quality
documentation reports typical 2-m temperature errors of 0.5–1.5°C, implying
isotherm height errors of ~50–150 m or roughly 0.05–0.15 km.

**Current treatment:** ERA5 is bilinearly interpolated to the 0.05° grid.
Monthly means are used; diurnal variability is not resolved.

**Impact:** SHI is approximately linear in the isotherm layer depth. A 100 m
error in freezing-level height yields a ~2–5% SHI error in typical environments.

---

## 2. Algorithmic Uncertainty

### 2.1 Block-maximum quantization

Each radar day's corrected MESH75 raster is a spatial maximum over the day's
available sweeps. The temporal resolution of the underlying radar mosaics (5–6
minutes for MRMS; hourly for MYRORSS) means the "convective-day maximum" (12 UTC → 12 UTC) is well
resolved for long-duration events but may miss short-duration isolated
convection in MYRORSS.

**Current treatment:** Daily maxima are taken as-is.

**Impact:** MYRORSS convective-day maxima may underestimate true peak MESH75 for fast-moving
events. This is expected to depress annual maxima by a few mm in regimes where
isolated convective cells dominate (e.g., Pacific coast, high plains).

### 2.2 Source-transition bias

Stages 01–05 merge three radar sources (MYRORSS 1998–2011, GridRad 2012–2020-10-13,
MRMS 2020–present). Despite quantile-mapping calibration in Stage 05, residual
bias at the transition boundaries may exist. Stage 06 performs a source-
homogeneity check (KS test between MYRORSS and calibrated GridRad distributions
in the 2005–2011 overlap), but KS rejection does not automatically correct the
bias.

**Current treatment:** Quantile mapping calibration. KS diagnostic (Stage 06)
is advisory.

**Impact:** If residual bias is present at the MYRORSS→GridRad boundary (2012),
annual maxima from the two eras will be drawn from slightly different
distributions. This would inflate or deflate tail estimates depending on the
direction of the residual bias.

### 2.2.1 GridRad product calendar coverage

NCAR publishes three GridRad products used in Stage 04c: **GridRad-Severe**
(~100 severe events per year), **V3.1 hourly** (through 2017, all months), and
**V4.2 warm-season hourly** (Apr–Aug only). Many gap-era convective days have
no NCAR product (off-season, or warm-season days without a severe event and
outside the V4.2 calendar). The Stage 04c manifest records these as
`missing_source`; they are data-availability gaps, not algorithm failures.

**Current treatment:** Severe-first download policy; hourly fallback
**d841000 → d841001**; manifest provenance; optional `--missing-only` backfill.

**Impact:** Annual maxima and occurrence statistics in the gap era are
conditional on NCAR product availability. Sparse rural areas on non-severe
warm-season days may be underrepresented relative to the MRMS era.

### 2.3 Topographic correction coefficient

Stage 12 applies a freezing-level-aware topographic correction:

```math
f(z, z_{0°C}) = \mathrm{clip}\!\left(1 + 0.25 \cdot \frac{z}{\max(z_{0°C},\, \varepsilon)},\; 1.0,\; 1.25\right)
```

The coefficient 0.25 is currently not cited to a specific publication (see
review finding E.8). It is calibrated to produce Front Range / Great Plains
ratios broadly consistent with Cintineo et al. (2012). The true physical
relationship between terrain elevation, freezing level, and hail occurrence
involves complex microphysical processes not reducible to a simple linear factor.

**Current treatment:** Fixed empirical coefficient, bounded to a maximum 25%
enhancement. Applied only within CONUS mask.

**Recommended improvement (v2.2):** Sensitivity analysis over coefficient range
[0.1, 0.4]; cite Rasmussen & Heymsfield (1987) for physical bound.

---

## 3. Sampling Uncertainty

### 3.1 Record-length and tail instability

The usable radar record runs from April 1998 to the present (~27 years as of
2026). For a GPD fitted above a threshold, the effective sample size at each
cell for tail estimation is the number of years with annual maxima exceeding the
GPD threshold. In low-frequency hail regions (e.g., Pacific Northwest,
Northeast), this may be as few as 5–10 exceedances — insufficient for reliable
GPD estimation even with regional ξ pooling.

**Effect on RP estimates:**

| Record length | Exceedances | Approximate 90% CI width on RP100 |
|---|---|---|
| 25 years | 5 | ±300% |
| 25 years | 15 | ±80% |
| 25 years | 25 | ±40% |

(Approximate, based on Coles 2001 Table 4.2 for GPD shape ξ ≈ 0.)

**Current treatment:** Regional ξ pooling via L-moments (Stage 09) reduces
the effective variance of the shape parameter. Per-cell σ_GPD is estimated
individually.

**Current output:** Point estimates only. No confidence intervals on RP maps.

**Priority improvement (v2.2 — recommended P0):** Bootstrap 95% CIs on
cell-level RP estimates using block bootstrap by year (preserves temporal
dependence). Output companion rasters `rp_XXXXXyr_hail_q05.tif` and
`rp_XXXXXyr_hail_q95.tif`.

Implementation sketch:

```python
# Stage 09 — after fitting regional ξ:
B = 200  # bootstrap replicates
xi_boot = np.zeros((B, n_regions))
for b in range(B):
    for reg in range(n_regions):
        exc_b = rng.choice(exceedances[reg],
                           size=len(exceedances[reg]),
                           replace=True)
        xi_boot[b, reg] = lmoments_fit_xi(exc_b)
# Propagate to RP maps via Monte Carlo — cell-wise p05/p95 in two passes
```

### 3.2 Stationarity assumption

The model assumes the hail climate is stationary over the 1998–present record.
Mann-Kendall trend analysis (Stage 15 diagnostic) will test this assumption once
outputs are available. Non-stationarity in the record would invalidate
return-period estimates: a positive trend would cause the model to underestimate
future hazard.

**Current treatment:** Stationary model. Trend diagnostic is advisory.

---

## 4. Model Uncertainty

### 4.1 GPD tail model vs alternatives

The GPD is the theoretically justified limit distribution for exceedances above
a sufficiently high threshold (Pickands–Balkema–de Haan theorem; Coles 2001
§4.2). However:

- The convergence to GPD may be slow for the underlying hail size distribution.
- The lognormal body + GPD tail composite used in Stage 09 introduces a
  junction point; the sensitivity of RP estimates to this junction should be
  tested.
- Generalised Extreme Value (GEV) fitted to block maxima is an alternative with
  comparable theoretical justification.

**Current treatment:** GPD tail + lognormal body. GEV sensitivity is not
currently performed.

**Recommended improvement (v2.2):** GEV-vs-GPD comparison at the five benchmark
cells in `docs/benchmarks.md`. Report whether RP100 estimates agree within
the bootstrap CIs.

### 4.2 GPD threshold selection

Stage 09 selects the GPD threshold using a composite score of KS goodness-of-fit,
MRL stability, exceedance count, and shape parameter stability. The four
components have different units and are summed without normalisation. This means
the relative weight of each component depends on regional sample size.

**Current treatment:** Unweighted composite score. Threshold diagnostics are
written to `threshold_selection.csv` for manual review.

**Recommended improvement (v2.2):** Normalize all components to [0, 1] before
summing; document the resulting weights in `docs/methodology.md §09`.

### 4.3 Regional ξ pooling (K-means, k=6)

K-means clustering with k=6 is used to define EVT pooling regions. The choice
of k=6 is pragmatic; it has not been optimised against a silhouette score or
compared to published hail climatological regions (Allen et al. 2015).

**Current treatment:** k=6 fixed default. `--n-regions N` CLI flag allows
experimentation.

**Recommended improvement (v2.2):** Report silhouette scores for k∈{4,6,8,10}
and select the elbow or maximum. Compare against Allen et al. (2015) Fig. 5
hail regions.

### 4.4 Spatial smoothing kernel (Stage 10)

Stage 10 applies a 150 km radius / 75 km decay kernel to smooth per-cell RP
estimates. The kernel parameters are not calibrated; they represent a compromise
between spatial coherence and local accuracy.

**Impact:** The smoothed RP maps are used for final output. Kernel-induced
smoothing will underestimate RP values at local maxima (e.g., hail alleys) and
overestimate them at local minima (e.g., mountain gaps).

**Recommended improvement (v2.2):** Sensitivity analysis over POOL_RADIUS_KM ∈
{100, 150, 200} and DECAY_KM ∈ {50, 75, 100}.

---

## 5. Stochastic Uncertainty

### 5.1 σ_perturb calibration

Stage 13 perturbs each synthetic event's intensity by a log-normal factor. The
global perturbation parameter is calibrated from historical event peaks using
monthly coefficient of variation during the main hail season:

```math
\mathrm{CV}_m =
\frac{\mathrm{sd}(\text{event peak MESH75 in month }m)}
     {\mathrm{mean}(\text{event peak MESH75 in month }m)}
```

```math
\hat{\sigma}_{\text{perturb}} =
\mathrm{clip}\left(\mathrm{median}(\mathrm{CV}_m), 0.10, 0.40\right),
\quad m \in \{\mathrm{Mar}, \ldots, \mathrm{Sep}\}
```

Months with fewer than 10 positive events are excluded. During simulation, the
implementation uses a percentile-aware event standard deviation:

```math
\sigma_{\mathrm{event}} =
\mathrm{clip}(0.10 + 0.15p, 0.10, \max(0.25, \hat{\sigma}_{\text{perturb}}))
```

where `p` is the historical template's rank percentile by peak hail size. The
assumption that hail intensity variability is spatially uniform is likely
violated: Tornado Alley and the High Plains may have different variance
structure than the Southeast or Northeast.

**Current treatment:** Global σ_perturb applied uniformly to all events.

**Recommended improvement (v2.2):** Region-stratified σ_perturb (one value per
EVT region); document derivation with explicit equation.

### 5.2 Event frequency: Poisson vs Negative Binomial

Stage 13 samples annual event counts from a Poisson distribution:
`N_events ~ Poisson(λ)`. Poisson assumes events are temporally independent with
mean equal to variance (index of dispersion = 1). Hail events are known to
cluster during active synoptic patterns, leading to over-dispersion
(var/mean > 1).

**Current treatment:** Poisson. Diagnostic not yet implemented.

**Recommended improvement (v2.2):** Compute index of dispersion on annual event
counts from Stage 08. If index of dispersion significantly > 1 (one-sample
Poisson test, α = 0.05), switch to Negative Binomial with the fitted dispersion
parameter.

**Impact:** Poisson under-dispersed tail → the model underestimates the
probability of years with many large events (aggregate loss tail), and
overestimates the probability of average years. This is the primary driver of
potential aggregate-loss underestimation in the stochastic catalog.

### 5.3 Spatial translation uncertainty

Each synthetic event footprint is translated by ±3 cells (~16.5 km) in row and
column. The translation magnitude is not calibrated from observed event track
variability; it is chosen to be sub-mesoscale (smaller than typical storm
track length) so as not to perturb event identity.

**Current treatment:** Uniform translation up to ±3 cells. Sensitivity to this
parameter (±1, 3, 5, 7 cells) is planned but not yet performed.

### 5.4 Catalog length and empirical RP stability

The 50,000-year catalog is large enough for empirical RP estimates to be stable
at 50,000-year return periods. At shorter return periods (RP < 100), empirical
and analytical estimates should agree within a few percent. Divergence between
the two RP products flags potential GPD misspecification (see Stage 15 diagnostic).

**Current treatment:** Both RP products are computed; divergence flag is
mandatory review before interpretation.

---

## 6. Vulnerability Uncertainty

### 6.1 Placeholder status

The Stage 14 MDR (mean damage ratio) curves are derived from published literature
parameters (Brown et al. 2015; IBHS impact testing). They are **not calibrated
against insurance claims data**. The curves represent a reasonable literature-
based prior but are subject to large uncertainty:

- μ_v and σ_v are eyeballed from published damage onset thresholds, not fitted
  to observed claims.
- Roof age distribution (which strongly affects vulnerability) is not modelled.
- Geographic variation in construction quality is not captured.

**Typical uncertainty range:** MDR estimates from un-calibrated curves may be
off by a factor of 2–5× relative to claims-calibrated curves for the same
hail size and construction class (Pita et al. 2013).

**Current treatment:** Clearly marked as placeholder. Stage 14 prints a warning
at runtime.

**Required for production use:** Calibration against proprietary claims data is
mandatory before the vulnerability module is used for any financial or
insurance-related purpose.

---

## 7. Compound and Interaction Effects

The six uncertainty categories above are not independent:

- GPD threshold selection (model uncertainty) affects the number of exceedances
  (sampling uncertainty).
- σ_perturb calibration (stochastic uncertainty) is itself subject to sampling
  uncertainty from the finite record.
- Source-transition bias (algorithmic uncertainty) inflates apparent sampling
  uncertainty by contaminating the annual maximum series.

A full uncertainty propagation would require Monte Carlo simulation across all
six categories simultaneously. This is deferred to v3.0.

---

## 8. Current Uncertainty Disclosures

The following disclosures must accompany any publication of v2.2 model outputs:

1. Return-period maps are **point estimates**. Confidence intervals are not yet
   computed. For RP > 500 years, uncertainty likely exceeds ±50% of the point
   estimate in most regions.

2. The model assumes **stationarity**. Results may not be valid for future
   climate scenarios without non-stationarity adjustment.

3. Vulnerability curves are **placeholders**. Loss estimates should not be used
   for financial decision-making without claims calibration.

4. The stochastic catalog uses **Poisson event frequency**, which may
   underestimate aggregate loss in active years.

5. Topographic correction uses an **uncited coefficient** (0.25). Results in
   complex terrain (Rockies, Appalachians, Pacific Coast ranges) should be
   treated with additional caution.

---

## References

- Bringi, V. N. & Chandrasekar, V. (2001). *Polarimetric Doppler Weather Radar.*
  Cambridge University Press.
- Coles, S. (2001). *An Introduction to Statistical Modeling of Extreme Values.*
  Springer.
- Grossi, P. & Kunreuther, H. (2005). *Catastrophe Modeling: A New Approach to
  Managing Risk.* Springer.
- Mitchell-Wallace, K. et al. (2017). *Natural Catastrophe Risk Management and
  Modelling.* Wiley.
- Murillo, E. M. & Homeyer, C. R. (2021). Severe hail estimation from dual-
  polarization radar. *J. Appl. Meteor. Climatol.*, 60, 1197–1223.
- Pita, G. L. et al. (2013). Assessment of hurricane-induced internal pressure
  loads on low-rise buildings. *J. Wind Eng. Ind. Aerodyn.*, 114, 26–34.
- Rasmussen, R. M. & Heymsfield, A. J. (1987). Melting and shedding of graupel
  and hail. *J. Atmos. Sci.*, 44, 2754–2763.
