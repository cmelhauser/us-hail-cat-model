# Literature Review

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Purpose

This literature review documents the scientific basis for the v2.1 hail catastrophe model methodology. It covers report bias, radar-based hail climatology, MESH correction, environmental filtering, extreme-value theory, spatial extremes, stochastic event simulation, topography, and vulnerability.

v2.1 does not replace the v2.0 radar-based design. It strengthens it by adding conditional calibration, probabilistic filtering, automated EVT threshold diagnostics, sparse-safe stochastic perturbations, and stronger model-risk diagnostics.

---

## 2. SPC Report Bias

### Allen and Tippett (2015)

Allen and Tippett documented major biases in U.S. hail reports, including population-density effects, road-network effects, time-of-day reporting bias, and report-size rounding. This supports the model decision to avoid using SPC reports as the primary hazard input.

**Model implication:** SPC reports should be used for validation and calibration support, not as the primary hazard field.

### Allen, Tippett, and Sobel (2015)

This work connected hail occurrence to large-scale environmental predictors such as CAPE, shear, and freezing level. It also reinforced that report-based hail climatologies are affected by non-meteorological reporting biases.

**Model implication:** Environmental predictors are appropriate covariates for v2.1 conditional calibration and probabilistic filtering.

### Blair et al. (2011, 2017)

Blair and coauthors documented the difficulty of measuring large hail at the surface and the mismatch between radar-inferred and ground-reported sizes.

**Model implication:** MESH validation against SPC should be interpreted cautiously. Ground reports are not perfect truth.

---

## 3. Radar-Based Hail Products

### Witt et al. (1998)

Witt et al. introduced the original MESH algorithm, which estimates maximum hail size from radar reflectivity above the freezing level using the Severe Hail Index.

**Model implication:** MESH is physically grounded but warning-oriented and intentionally conservative. Bias correction is required for climatological and actuarial use.

### Smith et al. (2016)

Smith et al. describe the operational MRMS system, including multi-radar severe-weather products and high-frequency gridded radar output.

**Model implication:** Operational MRMS is the best public recent radar source for spatially continuous hail estimates.

### Ortega et al. (2022)

MYRORSS reprocesses historical radar data through the MRMS framework, providing a consistent historical radar record.

**Model implication:** MYRORSS is the backbone for the pre-operational historical radar period.

### Wendt and Jirak (2021)

Wendt and Jirak produced an MRMS MESH climatology and compared it with Storm Data reports. They showed that radar-based MESH captures hail in rural and nocturnal settings that reports often miss.

**Model implication:** Radar-based input improves spatial completeness and reduces population/reporting bias.

### Murillo, Homeyer, and Allen (2021)

This GridRad-based hail climatology is foundational for extending the radar-based hail record. It used revised MESH configurations and environmental filtering to build a long-term hail climatology.

**Model implication:** GridRad can fill the MYRORSS-to-MRMS gap, but temporal-resolution and smoothing differences require cross-calibration.

---

## 4. MESH Bias Correction and Environmental Filtering

### Murillo and Homeyer (2019; corrected 2021)

Murillo and Homeyer developed revised SHI-to-hail-size relationships, including MESH75 and MESH95. MESH75 is appropriate for a hazard model seeking broad sensitivity to severe hail.

**Model implication:** The v2.1 model retains the corrected MESH75 relationship.

### Ortega (2018)

Ortega evaluated multi-radar products for surface hail estimation and discussed discriminating hail-producing from non-hail-producing radar signatures.

**Model implication:** Environmental filtering should use predictors, not just fixed thresholds. v2.1’s probabilistic filter follows this principle.

### Gneiting et al. (2005)

Gneiting and coauthors introduced calibrated probabilistic forecasting using ensemble model output statistics and minimum CRPS estimation. Although not a hail-specific paper, it is directly relevant to post-processing biased model outputs into calibrated probabilistic predictions.

**Model implication:** v2.1 conditional calibration and probabilistic filtering should be evaluated using calibration-oriented metrics such as Brier score, reliability, and distributional calibration.

---

## 5. Extreme Value Theory

### Coles (2001)

Coles provides the standard practical reference for extreme-value modeling, including generalized Pareto distributions, mean residual life diagnostics, return-level estimation, and uncertainty interpretation.

**Model implication:** Stage 09 GPD fitting should report threshold diagnostics and uncertainty indicators rather than relying on fixed thresholds alone.

### Hosking and Wallis (1997)

Hosking and Wallis provide the foundation for regional frequency analysis using L-moments. Pooling similar sites improves tail-parameter stability when local samples are sparse.

**Model implication:** v2.1 retains regional ξ pooling because hail extremes are sparse at individual grid cells.

### Scarrott and MacDonald (2012)

Scarrott and MacDonald review threshold selection and uncertainty quantification for peaks-over-threshold extreme-value models.

**Model implication:** v2.1 implements automated threshold diagnostics using MRL behavior, parameter stability, and goodness-of-fit measures.

---

## 6. Spatial Extremes and Dependence

### Davison, Padoan, and Ribatet (2012)

Davison and coauthors review spatial extremes and discuss latent-variable, copula, and max-stable approaches.

**Model implication:** Independent cell-level tails can understate aggregate risk. v2.1 should at least diagnose spatial dependence and may add a lightweight Gaussian-copula sampling option. Full max-stable modeling is better suited for a later major version.

### Cooley, Nychka, and Naveau (2007)

Cooley and coauthors developed Bayesian spatial modeling approaches for extreme precipitation using max-stable process ideas.

**Model implication:** This supports future v3.0 consideration of spatial extreme processes, but v2.1 deliberately avoids the complexity.

---

## 7. Stochastic Hail Event Modeling

### Miralles, Davison, and Schmid (2023)

This work models hail insurance claims using spatial stochastic structures, including hail swath representations and extreme marks.

**Model implication:** Historical event resampling can be strengthened with parametric perturbations of location, intensity, and footprint shape. v2.1 implements lightweight sparse-safe perturbation rather than a full generative storm process.

### Commercial severe convective storm model practices

Commercial models generally use long stochastic catalogs, event perturbation, spatial correlation, and vulnerability/exposure layers calibrated to claims.

**Model implication:** A 50,000-year event catalog is reasonable, but diagnostics must clearly distinguish hazard uncertainty from vulnerability and exposure uncertainty.

---

## 8. Topographic Effects

### Li et al. (2021)

Li and coauthors discuss the role of elevated terrain and the Gulf of Mexico in severe storm environments, including the importance of the Rocky Mountain Front Range.

**Model implication:** Terrain matters for hail production and survival. v2.1 replaces a purely fixed elevation adjustment with a freezing-level-relative survival factor where ERA5 is available.

### Andrews et al. (2024)

Andrews and coauthors describe the climatology of elevated mixed layers over CONUS and northern Mexico using ERA5, highlighting the terrain-linked severe-storm environment.

**Model implication:** Topography affects both storm initiation environments and hail survival. v2.1 only addresses the survival component; production treatment would require environmental occurrence modeling.

---

## 9. Vulnerability

### Brown et al. (2015)

Brown and coauthors evaluated hail damage using property insurance claims and found roofing material and roof vulnerability are central to hail loss.

**Model implication:** Stage 14 placeholder MDR curves are directionally useful but must be calibrated with claims data for production loss modeling.

### IBHS and impact-testing literature

IBHS and related impact-testing programs provide evidence on how roofing materials respond to hail sizes and impact energy.

**Model implication:** Construction class, roof type, roof age, and material matter. A complete catastrophe model must include these exposure/vulnerability attributes.

---

## 10. Climate Non-Stationarity

Recent severe-hail literature increasingly discusses possible non-stationarity in large hail environments and losses. The v2.1 model remains stationary because the record is still short for robust non-stationary tail estimation.

**Recommended v2.1 diagnostic:**

- Mann-Kendall trend tests for annual event counts.
- Rolling 10-year summaries of peak intensity and occurrence.
- Regional trend diagnostics reported separately from the stationary CDF fit.

**Model implication:** Do not force a trend into the tail model without stronger evidence and a longer homogeneous record.

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
