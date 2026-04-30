# Literature Review: CONUS Hail Catastrophe Model v2.0

**Date:** 2026-04-30
**Purpose:** Foundation for migrating the hail cat model from SPC-report-based to MRMS/GridRad-MESH-based hazard input, with supporting literature for all planned methodology improvements.

---

## 1. Population Bias in SPC Storm Reports

### 1.1 The Core Problem

The NOAA Storm Prediction Center hail report database is the most widely used source for US hail climatologies, but it suffers from well-documented spatial and temporal biases that fundamentally limit its utility for quantitative hazard modeling.

**Allen, J.T. and M.L. Tippett (2015).** "The characteristics of United States hail reports: 1955–2014." *Electronic J. Severe Storms Meteor.*, 10(3), 1–31.
- Demonstrated that SPC hail report density is strongly correlated with population density, road network proximity, and proximity to NWS offices.
- Found that simple population-density corrections are of limited effectiveness because road networks, spotter networks, and NWS warning verification practices introduce additional non-population biases.
- Documented systematic size-rounding in reports (clustering at whole-inch and reference-object sizes: quarter, golf ball, baseball).
- Showed that nighttime hail is dramatically underreported relative to daytime events.

**Allen, J.T., M.L. Tippett, and A.H. Sobel (2015).** "An empirical model relating U.S. monthly hail occurrence to large-scale meteorological environment." *J. Adv. Model. Earth Syst.*, 7(1), 226–243.
- Developed an environmental proxy model for hail occurrence using CAPE, wind shear, and freezing level height from reanalysis data.
- Confirmed that the road network imprint on hail reports limits the effectiveness of population-only corrections.
- Proposed environmental proxies as a complementary approach to ground-truth reports for spatial hail frequency estimation.

**Blair, S.F., D.R. Deroche, J.M. Boustead, J.W. Leighton, B.L. Barjenbruch, and W.P. Gargan (2011, 2017).** "A radar-based assessment of the detectability of giant hail." *Electronic J. Severe Storms Meteor.*, 6(7), 1–30; and "High-resolution hail observations: implications for NWS warning operations." *Wea. Forecasting*, 32, 1101–1119.
- Documented that hail reports systematically underestimate true hail size due to surface melting, measurement timing, and use of approximate reference objects.
- Found size discrepancies of 0.5–1.0 inches between radar-inferred and ground-reported sizes for large hail events.
- Implications for our model: even with radar-based MESH as primary input, a ground-truth calibration layer is needed for size accuracy.

### 1.2 Implications for Our Model

The v1.0 model's β=2.37 superlinear scaling exponent captures the population-density component of the reporting bias but cannot address road-network effects, nighttime underreporting, size-rounding artifacts, or temporal non-stationarity in reporting practices. Migrating to radar-based MESH as the primary hazard input eliminates the population and temporal biases entirely. SPC reports are retained as a validation/calibration dataset rather than the primary input.

---

## 2. Radar-Based Hail Climatologies

### 2.1 MRMS MESH — The Operational Standard

**Witt, A., M.D. Eilts, G.J. Stumpf, J.T. Johnson, E.D. Mitchell, and K.W. Thomas (1998).** "An enhanced hail detection algorithm for the WSR-88D." *Wea. Forecasting*, 13, 286–303.
- Original MESH algorithm: estimates maximum hail size from the vertical profile of radar reflectivity above the 0°C isotherm.
- MESH integrates reflectivity-weighted kinetic energy flux (Severe Hail Index, SHI) and converts it to an estimated hail diameter.
- Designed as an intentional overforecast: approximately 75% of observed hail falls below the MESH estimate.
- Key parameters: reflectivity thresholds, 0°C and −20°C isotherm heights from environmental temperature profiles.

**Smith, T.M., V. Lakshmanan, G.J. Stumpf, K.L. Ortega, et al. (2016).** "Multi-Radar Multi-Sensor (MRMS) severe weather and aviation products: initial operating capabilities." *Bull. Amer. Meteor. Soc.*, 97, 1617–1630.
- Describes the operational MRMS system deployed at NCEP in 2014.
- MESH product computed on an approximately 1-km horizontal grid across CONUS.
- Updates every 2 minutes using data from 143+ WSR-88D radars plus Canadian radars.
- Provides spatially continuous hail size estimates eliminating all population-density biases.

**Wendt, N.A. and I.L. Jirak (2021).** "An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports." *Wea. Forecasting*, 36, 645–659.
- Constructed an hourly MESH climatology for CONUS from 2012–2019.
- Demonstrated that MESH captures severe hail occurrence in low-population-density areas where SPC reports are sparse.
- Showed MESH detects nocturnal hail events missed by ground-based reports, particularly in regions prone to elevated convection and mesoscale convective systems.
- Key finding: MESH spatial patterns broadly agree with SPC report patterns in population-dense areas but reveal significantly more hail activity in rural Great Plains and Mountain West — exactly the regions where our v1.0 model is weakest.

### 2.2 GridRad MESH — The Extended Record

**Murillo, E.M., C.R. Homeyer, and J.T. Allen (2021).** "A 23-year severe hail climatology using GridRad MESH observations." *Mon. Wea. Rev.*, 149, 945–958.
- **This is the foundational paper for our v2.0 migration.**
- Applied improved MESH configurations (MESH75, MESH95) to the full GridRad archive of hourly composite NEXRAD data from 1995–2017.
- GridRad provides ~2-km horizontal resolution and 1-km vertical resolution composite radar volumes across most of CONUS (West Coast excluded due to negligible severe hail).
- The improved MESH configurations (from Murillo & Homeyer 2019) use updated SHI–hail size relationships fitted to a larger calibration dataset than the original Witt et al. (1998) 147-report sample.
- MESH75: 75th percentile of observed hail given SHI — captures severe hail (≥1.0") with higher sensitivity.
- MESH95: 95th percentile — captures significant severe hail (≥2.0") with higher specificity.
- Key finding for our model: the filtered MESH climatology shifts the Central Plains hail maximum further into southwest Texas and eastern Colorado compared to SPC reports, likely reflecting better capture of hail in low-population areas.
- Environmental filtering using MERRA-2 reanalysis constrains MESH to environments supportive of hail reaching the ground, reducing false detections from deep tropical convection.

**Murillo, E.M. and C.R. Homeyer (2019).** "Revised estimates of the maximum expected size of hail." *J. Appl. Meteor. Climatol.*, 58, 2037–2056.
- Developed the recalibrated MESH75 and MESH95 algorithms used in the 23-year climatology.
- Fitted SHI–hail-size relationships to a much larger set of hail reports than Witt et al. (1998).
- MESH75 provides the best balance of detection and false alarm for severe hail (≥1.0").
- MESH95 is better suited for significant severe hail (≥2.0") detection.
- For our cat model, MESH75 is the recommended primary product for hazard raster construction.

### 2.3 MYRORSS — The Historical Reanalysis

**Ortega, K.L., T.M. Smith, G.J. Stumpf, et al. (2022).** "Comprehensive radar data for the contiguous United States: Multi-Year Reanalysis of Remotely Sensed Storms." *Bull. Amer. Meteor. Soc.*, 103, E732–E749.
- MYRORSS reprocesses the WSR-88D Level-II archive from April 1998 through December 2011 using the MRMS framework.
- Produces a seamless 3D reflectivity volume on a ~1-km grid across CONUS with ~5-min update frequency.
- Includes derived severe-storm products including MESH.
- Data is manually quality-controlled to remove erroneous radar scans.
- Freely available on AWS: `s3://noaa-oar-myrorss-pds/`
- Combined with operational MRMS (2012–present), this provides a potential 28-year radar-based hail record (1998–2026).

### 2.4 Data Availability Summary

| Dataset | Period | Resolution | Format | Access |
|---|---|---|---|---|
| GridRad V3.1 | 1995–2017 | ~0.02° (~2 km), hourly | NetCDF | NCAR RDA (gridrad.org) |
| GridRad V4.2 | 2008–2021 | ~0.02° (~2 km), hourly | NetCDF | NCAR RDA |
| MYRORSS | Apr 1998–Dec 2011 | ~0.01° (~1 km), ~5-min | NetCDF/GRIB | AWS S3 (noaa-oar-myrorss-pds) |
| Operational MRMS | 2012–present | ~0.01° (~1 km), 2-min | GRIB2 | NCEP HTTP, AWS S3 (noaa-mrms-pds), Iowa State archive |
| Iowa State MRMS archive | 2021–present (hourly zips) | ~0.01°, hourly | GRIB2 | mrms.agron.iastate.edu |

**Recommended data strategy for our model:**
1. **Primary (1998–2011):** MYRORSS MESH from AWS S3 — provides pre-operational MRMS-equivalent data.
2. **Primary (2012–present):** Operational MRMS MESH from Iowa State archive or AWS S3.
3. **Calibration/validation:** GridRad MESH75/MESH95 from Murillo et al. (2021) for bias correction benchmarking.
4. **Validation:** SPC hail reports (2004–present) for ground-truth comparison in populated areas.

---

## 3. MESH Bias Correction

### 3.1 Known MESH Biases

MESH systematically overestimates ground-level hail size. This is by design — Witt et al. (1998) calibrated MESH so that approximately 75% of observed hail falls below the MESH estimate, making it a useful "upper bound" for warning purposes but a biased estimate for climatological and actuarial use.

Additional bias sources:
- **Tropical/subtropical deep convection:** MESH produces false hail signals from deep convection without hail (high reflectivity aloft but warm melting layer). Environmental filtering (surface temperature, CAPE, freezing level) mitigates this.
- **Beam blockage and range degradation:** Radar coverage degrades with distance from radar sites, particularly in mountainous terrain. The Intermountain West and parts of the Northern Plains have reduced radar coverage.
- **Temporal sampling:** MRMS updates every 2 minutes; shorter-lived hail cores may be partially captured depending on radar scan strategy.

### 3.2 Correction Approaches

**Murillo and Homeyer (2019) recalibration:**
- MESH75/MESH95 provide improved SHI-to-hail-size conversions.
- For our model, applying the MESH75 calibration to raw MESH values provides the most physically grounded bias correction.
- The environmental filtering approach (requiring CAPE > threshold, surface T < threshold, and freezing level within supportive range) from the GridRad climatology paper should be applied to eliminate false detections.

**Ortega, K.L. (2018).** "Evaluating multi-radar, multi-sensor products for surface hailfall estimation." *Electronic J. Severe Storms Meteor.*, 13(1), 1–36.
- Proposed a Linear Discriminant Analysis (LDA) approach to distinguish hail-producing from non-hail-producing MESH signals.
- Used environmental variables (CAPE, shear, freezing level) as discriminant features.
- This approach could serve as the basis for our environmental filtering step.

**Recommended correction pipeline for our model:**
1. Ingest raw MESH values from MYRORSS/MRMS.
2. Apply MESH75 recalibration (Murillo & Homeyer 2019) to convert raw MESH to calibrated hail size estimates.
3. Apply environmental filter: require coincident lightning within 40 km (as in Wendt & Jirak 2021) and/or CAPE/freezing-level thresholds from reanalysis.
4. Validate corrected MESH against SPC reports where both data sources co-occur.

---

## 4. Extreme Value Theory for Hail

### 4.1 Block Maxima vs. Peaks Over Threshold

The standard EVT framework offers two approaches: the Block Maxima (BM) approach using the Generalized Extreme Value (GEV) distribution, and the Peaks Over Threshold (POT) approach using the Generalized Pareto Distribution (GPD). Our v1.0 model uses a hybrid: block maxima (annual maximum series) for the lognormal body, and POT for the GPD tail above 2.0".

**Hosking, J.R.M. and J.R. Wallis (1997).** *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press.
- The foundational text for L-moment-based regional frequency analysis.
- Recommends pooling data from hydrologically/climatologically similar sites to improve parameter estimation stability.
- Key technique for our model: **regional pooling of GPD shape parameter ξ** — fit a shared ξ across neighboring cells while allowing cell-specific scale σ. This eliminates most of the 88 empirical-fallback cells in v1.0.
- L-moment ratio diagrams can be used to verify distributional assumptions across groups of cells.

**Coles, S. (2001).** *An Introduction to Statistical Modeling of Extreme Values.* Springer.
- Standard reference for EVT methodology in practice.
- Mean Residual Life (MRL) plots: for data exceeding threshold u, plot E[X − u | X > u] vs. u. If GPD is appropriate above u, the MRL plot should be approximately linear. This diagnostic should be used to validate the 2.0" splice point per region.
- Profile likelihood confidence intervals for GPD parameters provide uncertainty quantification.

### 4.2 Threshold Selection

**Scarrott, C. and A. MacDonald (2012).** "A review of extreme value threshold estimation and uncertainty quantification." *REVSTAT*, 10(1), 33–60.
- Reviews automated threshold selection methods including sequential Anderson-Darling tests, cross-validation, and mixture model approaches.
- For our model: the 2.0" threshold was chosen heuristically. MRL diagnostics should be computed per region (e.g., Great Plains core, Southeast, Northeast, Mountain West) to determine whether a single threshold is appropriate or whether regional thresholds better capture the GPD asymptote.

### 4.3 Regional Frequency Analysis for the 88 Fallback Cells

The 88 cells where GPD fitting fails (shape parameter ξ too large, producing physically impossible extrapolations) are concentrated in data-sparse areas at the edges of the active domain. The solution from the literature is clear:

**Hosking and Wallis (1997), Chapter 9:**
- Group cells into climatologically homogeneous regions.
- Fit a shared GPD shape parameter ξ for the region using pooled L-moment ratios.
- Allow cell-specific scale parameters σ and occurrence probabilities p_occ.
- This preserves local hazard characteristics while stabilizing the tail fit.

For implementation: define regions using K-means clustering on cell attributes (mean annual hail, p_occ, latitude, longitude, elevation). Pool GPD exceedances within each region for L-moment estimation of ξ. This should reduce the 88 fallback cells to near zero.

---

## 5. Stochastic Event Set Generation

### 5.1 Industry Approaches

**Moody's RMS North America Severe Convective Storm HD Model:**
- 50,000 simulation years, producing 12+ million stochastic events.
- Calibrated against $50+ billion in historical insurance claims data.
- 16 distinct hail size categories.
- Uses a combination of historical event resampling and parametric perturbation of track, intensity, and footprint geometry.
- Explicitly captures rare high-impact events including derechos.

**Verisk/AIR Touchstone Severe Thunderstorm Model:**
- Parametric storm generation using environmental proxies (CAPE, shear, moisture) from reanalysis.
- Stochastic storm tracks with spatially varying intensity.
- Vulnerability functions calibrated to claims data by construction class, roof type, and roof age.

### 5.2 Improving Event Resampling

Our v1.0 event-resampling approach preserves real spatial footprint geometry (a significant advantage over purely parametric methods) but cannot generate novel footprint shapes. The literature suggests several enhancements:

**Miralles, O., A.C. Davison, and T. Schmid (2023).** "Bayesian modeling of insurance claims for hail damage." *arXiv:2308.04926.*
- Develops a Gaussian line process with extreme marks to model both the geographic footprint of a hailstorm and the damage to buildings.
- Appears to be the first open stochastic hail impact function providing realistic estimates for individual buildings.
- Models the hail swath as a spatial process with a centerline and lateral decay — directly relevant to improving our footprint perturbation approach.

**Intensity perturbation calibration:**
- The current σ=0.15 log-normal perturbation was chosen a priori. It should be calibrated by computing the empirical inter-annual coefficient of variation of peak hail intensity across historical events in the same DOY window. If the observed CV exceeds 0.15, the perturbation is too conservative and underestimates tail risk.

**Spatial translation:**
- The existing `SPATIAL_TRANSLATE` flag (±2 cells, disabled) should be enabled with a displacement distribution calibrated from observed event centroid variance. For synoptic-scale events, inter-annual centroid displacement of ±50–100 km is physically plausible (1–3 cells at 0.25° or 2–4 cells at the new resolution).

---

## 6. Vulnerability Functions

### 6.1 Published Hail Vulnerability Curves

**Brown, T.M., et al. (2015).** "Evaluating hail damage using property insurance claims data." *Wea. Climate Soc.*, 7(3), 197–210.
- Analyzed insurance claims and policy-in-force data from 5 insurance companies for 67,000+ residential properties across 20 ZIP codes.
- Evaluated roofing material type vs. hail damage susceptibility.
- Found that roofing system damage dominates total hail loss (typically 60–80% of claim value).
- Compared WSR-88D radar-estimated hail sizes to claim damage levels.
- Key finding: damage onset begins at approximately 1.0–1.25" for aged 3-tab asphalt shingles, 1.5" for architectural/laminated shingles, and 2.0"+ for impact-resistant (IR/Class 4) products.

**IBHS (Insurance Institute for Business & Home Safety) research programs:**
- Conducted controlled impact testing of roofing materials using ice-ball launchers at various sizes and velocities.
- Class 4 (UL 2218) roofing withstands 2.0" steel ball impacts from 20 feet.
- Haag Engineering ice-ball tests: aged organic-mat 3-tab shingles sustain damage at 50% of impacts with 1.0" stones; fiberglass-mat at 60% with 1.25" stones.

### 6.2 MDR Functional Form

The standard mean damage ratio (MDR) curve for hail follows a lognormal CDF:

```
MDR(h) = Φ((ln(h) − μ_v) / σ_v)
```

where h is hail diameter (inches), μ_v and σ_v are construction-class-specific parameters, and Φ is the standard normal CDF.

**Typical parameter estimates from the literature and industry practice:**

| Construction Class | Roof Type | μ_v | σ_v | MDR at 1.0" | MDR at 2.0" | MDR at 3.0" |
|---|---|---|---|---|---|---|
| Frame, 3-tab asphalt (aged) | Standard | 0.40 | 0.60 | 0.16 | 0.63 | 0.89 |
| Frame, architectural shingle | Laminated | 0.70 | 0.55 | 0.06 | 0.42 | 0.77 |
| Frame, Class 4 IR | Impact-resistant | 1.10 | 0.50 | 0.01 | 0.14 | 0.48 |
| Metal roof | Standing seam | 1.30 | 0.45 | <0.01 | 0.06 | 0.30 |
| Masonry, flat built-up | Commercial BUR | 0.80 | 0.65 | 0.04 | 0.36 | 0.70 |

*Note: These are approximate values compiled from published studies and industry practice. Actual MDR calibration requires claims data.*

---

## 7. Exposure Data Sources

For a production-grade cat model, the exposure layer requires total insured value (TIV) by location and construction class. Public data sources include:

- **US Census American Community Survey:** Housing unit counts, median home values, and building age by census tract/block group.
- **CoreLogic / ATTOM property databases:** Commercial sources providing property-level construction details, roof type, and replacement cost estimates.
- **FEMA HAZUS:** Provides default building inventory by census tract including occupancy class, construction type, and replacement cost.
- **County assessor records:** Publicly available in many jurisdictions; vary widely in format and completeness.

---

## 8. Topographic Effects on Hail

**Li, F., D.R. Chavas, K.A. Need, N. Rosenbloom, and D.T. Dawson (2021).** "The role of elevated terrain and the Gulf of Mexico in the production of severe local storm environments over North America." *J. Climate*, 34, 7799–7819.
- Demonstrated that the Rocky Mountain Front Range creates pronounced hail enhancement through upslope flow triggering.
- Elevated terrain affects hail survival through shorter fall distances in the melting layer.
- Implications: a topographic correction factor should account for both enhanced hail production (orographic lift) and reduced melting (shorter path through warm air at elevation).

**Andrews, M.S., et al. (2024).** "Climatology of the elevated mixed layer over the contiguous United States and Northern Mexico using ERA5: 1979–2021." *J. Climate*, 37, 1833–1851.
- The elevated mixed layer (EML) is a key ingredient for severe hail-producing environments.
- EML frequency is strongly modulated by terrain — the lee of the Rockies produces the highest EML frequency in North America.
- Relevant for our topographic correction: cells near the Front Range should have elevated base hail rates that account for this orographic enhancement.

---

## 9. Climate Non-Stationarity

**Nature Geoscience (2025).** "Contrasting trends in very large hail events and related economic losses across the globe."
- Recent evidence that very large hail events may be increasing in frequency and/or intensity in some regions.
- Our v1.0 model assumes stationarity over the 22-year record. If the record is extended to 28 years (1998–2026) using MRMS/MYRORSS, testing for temporal trends becomes more feasible and important.
- Recommended: include a trend diagnostic (Mann-Kendall test on annual event counts and peak intensities) without building trend into the CDF fitting, which would require much longer records to do defensibly.

---

## 10. Grid Resolution Considerations

### 10.1 Matching Resolution to Data

The v1.0 model uses a 0.25° (~28 km) analysis grid — chosen to smooth the sparse SPC report data into stable cell-level statistics. With MRMS/GridRad MESH at ~1–2 km native resolution, the analysis grid should be reconsidered.

**Recommended analysis resolution: 0.05° (~5.5 km).**

Rationale:
- Native MRMS is ~0.01° (~1 km) — working at native resolution produces cells with a single hail swath width, leading to binary (hail/no-hail) cell behavior that is poorly suited to CDF fitting.
- 0.05° aggregation (~5×5 MRMS cells) provides sufficient spatial averaging for stable CDF statistics while preserving the spatial variability of hail swaths.
- 0.05° is the resolution of the v1.0 raw rasters (before aggregation to 0.25°) — the existing grid infrastructure can be reused.
- At 0.05°, the CONUS grid is 1180 × 520 = ~614,000 cells. With 28 years of data, most cells in Hail Alley will have 15–25+ hail events — sufficient for stable GPD fitting.
- For comparison: Moody's RMS HD models operate at property-level resolution for vulnerability but use ~5 km for hazard grids.

**Not recommended: 0.01° or 0.02° (native MRMS/GridRad).**
- At ~1–2 km resolution, individual hail swaths are only 1–5 cells wide. Most cells would have 0–2 events in the 28-year record — far too few for any meaningful CDF fitting.
- Would require 30+ million cells for CONUS — computationally prohibitive for the spatial correlation and stochastic modules.
- These resolutions are appropriate for event footprint characterization but not for the frequency/severity CDF layer.

---

## References (Alphabetical)

Allen, J.T. and M.L. Tippett, 2015: The characteristics of United States hail reports: 1955–2014. *Electronic J. Severe Storms Meteor.*, 10(3), 1–31.

Allen, J.T., M.L. Tippett, and A.H. Sobel, 2015: An empirical model relating U.S. monthly hail occurrence to large-scale meteorological environment. *J. Adv. Model. Earth Syst.*, 7(1), 226–243.

Andrews, M.S., et al., 2024: Climatology of the elevated mixed layer over the contiguous United States and Northern Mexico using ERA5: 1979–2021. *J. Climate*, 37, 1833–1851.

Blair, S.F., et al., 2011: A radar-based assessment of the detectability of giant hail. *Electronic J. Severe Storms Meteor.*, 6(7), 1–30.

Blair, S.F., et al., 2017: High-resolution hail observations: implications for NWS warning operations. *Wea. Forecasting*, 32, 1101–1119.

Brown, T.M., et al., 2015: Evaluating hail damage using property insurance claims data. *Wea. Climate Soc.*, 7(3), 197–210.

Coles, S., 2001: *An Introduction to Statistical Modeling of Extreme Values.* Springer, 208 pp.

Doswell, C.A., H.E. Brooks, and M.P. Kay, 2005: Climatological estimates of daily local nontornadic severe thunderstorm probability for the United States. *Wea. Forecasting*, 20(4), 577–595.

Hosking, J.R.M. and J.R. Wallis, 1997: *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press, 224 pp.

Li, F., et al., 2021: The role of elevated terrain and the Gulf of Mexico in the production of severe local storm environments over North America. *J. Climate*, 34, 7799–7819.

Miralles, O., A.C. Davison, and T. Schmid, 2023: Bayesian modeling of insurance claims for hail damage. *arXiv:2308.04926*.

Murillo, E.M. and C.R. Homeyer, 2019: Revised estimates of the maximum expected size of hail. *J. Appl. Meteor. Climatol.*, 58, 2037–2056.

Murillo, E.M., C.R. Homeyer, and J.T. Allen, 2021: A 23-year severe hail climatology using GridRad MESH observations. *Mon. Wea. Rev.*, 149, 945–958.

Ortega, K.L., 2018: Evaluating multi-radar, multi-sensor products for surface hailfall estimation. *Electronic J. Severe Storms Meteor.*, 13(1), 1–36.

Ortega, K.L., et al., 2022: Comprehensive radar data for the contiguous United States: Multi-Year Reanalysis of Remotely Sensed Storms. *Bull. Amer. Meteor. Soc.*, 103, E732–E749.

Scarrott, C. and A. MacDonald, 2012: A review of extreme value threshold estimation and uncertainty quantification. *REVSTAT*, 10(1), 33–60.

Smith, T.M., et al., 2016: Multi-Radar Multi-Sensor (MRMS) severe weather and aviation products: initial operating capabilities. *Bull. Amer. Meteor. Soc.*, 97, 1617–1630.

Wendt, N.A. and I.L. Jirak, 2021: An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports. *Wea. Forecasting*, 36, 645–659.

Witt, A., et al., 1998: An enhanced hail detection algorithm for the WSR-88D. *Wea. Forecasting*, 13, 286–303.
