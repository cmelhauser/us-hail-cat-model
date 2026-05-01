# Literature Review

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Purpose

This literature review documents the scientific basis for the v2.1 hail catastrophe model methodology. It covers report bias, radar-based hail climatology, MESH correction, environmental filtering, extreme-value theory, spatial extremes, stochastic event simulation, topography, vulnerability, and non-stationarity.

---

## 2. SPC Report Bias

### Allen and Tippett (2015)

Allen and Tippett documented major biases in U.S. hail reports, including population-density effects, road-network effects, time-of-day reporting bias, and report-size rounding.

**Model implication:** SPC reports should not be the primary hazard field. They are useful for validation but incomplete.

### Allen, Tippett, and Sobel (2015)

This work connected hail occurrence to large-scale environmental predictors such as CAPE, shear, and freezing level.

**Model implication:** Environmental predictors are appropriate covariates for v2.1 conditional calibration and probabilistic filtering.

### Blair et al. (2011, 2017)

These studies documented difficulties in measuring large hail and differences between radar-inferred hail and ground reports.

**Model implication:** MESH validation against SPC should be interpreted cautiously.

---

## 3. Radar-Based Hail Products

### Witt et al. (1998)

Witt et al. introduced the original MESH algorithm based on Severe Hail Index.

**Model implication:** MESH is physically motivated but warning-oriented, so calibration is required for climatological and actuarial use.

### Smith et al. (2016)

Smith et al. describe the operational MRMS system.

**Model implication:** MRMS provides recent public, spatially continuous radar hail products.

### Ortega et al. (2022)

MYRORSS provides historical radar reanalysis for the contiguous United States.

**Model implication:** MYRORSS is the backbone of the early historical radar record.

### Wendt and Jirak (2021)

This work compares operational MRMS MESH hail climatology with Storm Data.

**Model implication:** Radar captures hail in underreported regions and times.

### Murillo, Homeyer, and Allen (2021)

This GridRad-based hail climatology supports using GridRad to extend radar hail records.

**Model implication:** GridRad can fill temporal gaps but requires calibration.

---

## 4. MESH Correction and Filtering

### Murillo and Homeyer (2019; corrected 2021)

Murillo and Homeyer developed revised MESH relationships including MESH75.

**Model implication:** v2.1 retains the corrected MESH75 relationship.

### Ortega (2018)

Ortega evaluated radar products for surface hail estimation.

**Model implication:** Environmental filtering should use meteorological context.

### Gneiting et al. (2005)

This paper provides a probabilistic forecasting calibration framework.

**Model implication:** Conditional calibration and probabilistic filtering should be evaluated with reliability and Brier-style metrics.

---

## 5. Extreme Value Theory

### Coles (2001)

Coles provides a practical foundation for GPD tail modeling, threshold diagnostics, and return levels.

**Model implication:** Tail outputs require explicit threshold diagnostics and uncertainty review.

### Hosking and Wallis (1997)

Hosking and Wallis establish regional frequency analysis using L-moments.

**Model implication:** Regional pooling of GPD shape parameter ξ is appropriate where local samples are sparse.

### Scarrott and MacDonald (2012)

This paper reviews threshold selection and uncertainty for peaks-over-threshold modeling.

**Model implication:** v2.1 automated threshold diagnostics are methodologically justified.

---

## 6. Spatial Extremes

### Davison, Padoan, and Ribatet (2012)

This work reviews statistical modeling of spatial extremes.

**Model implication:** Independent cell-level tail modeling can understate aggregate risk. v2.1 includes diagnostics and leaves full spatial extremes for a future version.

### Cooley, Nychka, and Naveau (2007)

This work supports max-stable spatial extreme modeling.

**Model implication:** Max-stable models are future v3.0 candidates, not v2.1 scope.

---

## 7. Stochastic Event Modeling

### Miralles, Davison, and Schmid (2023)

This work models hail insurance claims with spatial stochastic structures.

**Model implication:** Stochastic event catalogs and perturbations are appropriate for hail risk modeling.

### Commercial severe convective storm model practice

Commercial models generally use event catalogs, perturbations, spatial dependence, exposure, and vulnerability.

**Model implication:** v2.1 implements public-data hazard components but not full production loss modeling.

---

## 8. Topography

### Li et al. (2021)

Li and coauthors discuss the role of elevated terrain and Gulf moisture in severe storm environments.

**Model implication:** Terrain matters for hail environments and hail survival.

### Andrews et al. (2024)

This work describes elevated mixed-layer climatology over CONUS and northern Mexico using ERA5.

**Model implication:** Terrain-linked severe storm environments support including topographic context.

---

## 9. Vulnerability

### Brown et al. (2015)

Brown and coauthors evaluated hail damage using property insurance claims.

**Model implication:** Roof type, material, age, and construction class matter. Stage 14 is placeholder until claims-calibrated.

### IBHS impact-testing literature

IBHS testing supports different vulnerability by roof material and impact resistance.

**Model implication:** Complete loss modeling requires detailed exposure and vulnerability calibration.

---

## 10. Climate Non-Stationarity

The v2.1 model remains stationary because the radar record is short relative to long-return-period estimation. Recommended diagnostics include Mann-Kendall trend tests and rolling 10-year summaries.

**Model implication:** Do not force trend into the tail model without stronger evidence and a longer homogeneous record.

---

## 11. References

Allen, J.T. and M.L. Tippett, 2015: The characteristics of United States hail reports: 1955–2014. *Electronic Journal of Severe Storms Meteorology*, 10(3), 1–31.

Allen, J.T., M.L. Tippett, and A.H. Sobel, 2015: An empirical model relating U.S. monthly hail occurrence to large-scale meteorological environment. *Journal of Advances in Modeling Earth Systems*, 7(1), 226–243.

Andrews, M.S., et al., 2024: Climatology of the elevated mixed layer over the contiguous United States and Northern Mexico using ERA5: 1979–2021. *Journal of Climate*, 37, 1833–1851.

Blair, S.F., et al., 2011: A radar-based assessment of the detectability of giant hail. *Electronic Journal of Severe Storms Meteorology*, 6(7), 1–30.

Blair, S.F., et al., 2017: High-resolution hail observations: implications for NWS warning operations. *Weather and Forecasting*, 32, 1101–1119.

Brown, T.M., et al., 2015: Evaluating hail damage using property insurance claims data. *Weather, Climate, and Society*, 7(3), 197–210.

Coles, S., 2001: *An Introduction to Statistical Modeling of Extreme Values.* Springer.

Cooley, D., D. Nychka, and P. Naveau, 2007: Bayesian spatial modeling of extreme precipitation return levels. *Journal of the American Statistical Association*, 102(479), 824–840.

Davison, A.C., S.A. Padoan, and M. Ribatet, 2012: Statistical modeling of spatial extremes. *Statistical Science*, 27(2), 161–186.

Gneiting, T., A.E. Raftery, A.H. Westveld III, and T. Goldman, 2005: Calibrated probabilistic forecasting using ensemble model output statistics and minimum CRPS estimation. *Monthly Weather Review*, 133(5), 1098–1118.

Hosking, J.R.M. and J.R. Wallis, 1997: *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press.

Li, F., D.R. Chavas, K.A. Reed, N. Rosenbloom, and D.T. Dawson, 2021: The role of elevated terrain and the Gulf of Mexico in the production of severe local storm environments over North America. *Journal of Climate*, 34, 7799–7819.

Miralles, O., A.C. Davison, and T. Schmid, 2023: Bayesian modeling of insurance claims for hail damage. *arXiv:2308.04926*.

Murillo, E.M. and C.R. Homeyer, 2019: Revised estimates of the maximum expected size of hail. *Journal of Applied Meteorology and Climatology*, 58, 2037–2056.

Murillo, E.M., C.R. Homeyer, and J.T. Allen, 2021: A 23-year severe hail climatology using GridRad MESH observations. *Monthly Weather Review*, 149, 945–958.

Ortega, K.L., 2018: Evaluating multi-radar, multi-sensor products for surface hailfall estimation. *Electronic Journal of Severe Storms Meteorology*, 13(1), 1–36.

Ortega, K.L., et al., 2022: Comprehensive radar data for the contiguous United States: Multi-Year Reanalysis of Remotely Sensed Storms. *Bulletin of the American Meteorological Society*, 103, E732–E749.

Scarrott, C. and A. MacDonald, 2012: A review of extreme value threshold estimation and uncertainty quantification. *REVSTAT*, 10(1), 33–60.

Smith, T.M., et al., 2016: Multi-Radar Multi-Sensor severe weather and aviation products: initial operating capabilities. *Bulletin of the American Meteorological Society*, 97, 1617–1630.

Wendt, N.A. and I.L. Jirak, 2021: An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports. *Weather and Forecasting*, 36, 645–659.

Witt, A., et al., 1998: An enhanced hail detection algorithm for the WSR-88D. *Weather and Forecasting*, 13, 286–303.
