# What This Model Does — Plain-Language Explainer

**CONUS Hail Catastrophe Model v2.1**

---

## The Problem

Hail causes billions of dollars in property damage in the United States. Insurers, reinsurers, risk managers, and model reviewers need to know how often damaging hail occurs and how severe it can become at any location.

The challenge is that traditional hail data are usually based on human reports. Human reports are useful, but they are biased. People report hail more often near towns, roads, and during the daytime. Large rural hailstorms can be missed, and reported hail sizes are often rounded to familiar objects such as quarters, golf balls, or baseballs.

This model uses radar-derived hail estimates instead of relying on human reports as the main input.

---

## What the Model Produces

For each small grid cell across the continental United States, the model estimates:

1. **How often hail happens.**
2. **How large hail can get.**
3. **How rare a given hail size is.**
4. **How uncertain the extreme estimates may be.**

Example output:

> “At this location, the 100-year hail size is estimated to be about 3 inches.”

This means there is roughly a 1% annual chance of hail at least that large at that location, according to the model assumptions.

---

## How the Model Works

### Step 1 — Use radar, not just storm reports

The model uses weather radar products that estimate hail size across the whole country. Radar sees storms in rural areas, at night, and away from roads. This provides a more consistent view than human reports alone.

The model combines three radar sources:

- MYRORSS for older historical data.
- GridRad for the gap period.
- Operational MRMS for recent data.

### Step 2 — Put all data onto the same grid

Every day is converted into a map with the same grid spacing, approximately 5.5 km. Each grid cell stores the largest hail size estimated for that day.

### Step 3 — Correct radar bias

Radar hail estimates are not perfect. Some radar products intentionally overestimate hail size because they were designed for warnings. Others can underestimate short-lived hail cores because of lower time resolution.

The model corrects these biases so that the different radar sources are more consistent with one another.

v2.1 improves this correction by considering the storm environment, such as freezing level height, season, location, and instability.

### Step 4 — Filter unlikely hail

Some storms can look hail-like on radar even when hail is unlikely to reach the ground. Older versions used hard cutoffs. v2.1 uses probability-based filtering, so suspicious signals are reduced rather than abruptly removed.

### Step 5 — Identify hail events

The model groups hail days into storm events. This helps distinguish a multi-day severe-weather outbreak from isolated unrelated storms.

v2.1 adds sanity checks so events are not merged if their centers jump too far or if the intensity changes implausibly between days.

### Step 6 — Fit statistical models

At each grid cell, the model fits a statistical distribution to the historical hail record.

- Ordinary hail sizes are modeled with a lognormal distribution.
- Rare, large hail is modeled with extreme value theory.
- Nearby cells share information to make rare-event estimates more stable.

### Step 7 — Simulate many years

The historical record is only a few decades long. That is not enough to directly observe 500-year or 1,000-year events.

To estimate rare events, the model simulates 50,000 years of synthetic hail events by resampling and perturbing real historical events.

v2.1 makes this simulation more realistic while keeping it computationally efficient:

- Events are moved slightly in space.
- Intensities are scaled based on observed variability.
- Event shapes can be lightly perturbed.
- The sparse event format is preserved to avoid memory blowups.

### Step 8 — Compare two independent estimates

The model produces two different return-period views:

1. Analytical estimates from fitted statistical distributions.
2. Empirical estimates from the 50,000-year simulation.

If these two disagree strongly, the model flags the area for review.

---

## What v2.1 Improves

v2.1 makes the model more defensible by improving:

- Bias correction between radar sources.
- Filtering of false hail signals.
- Event grouping logic.
- Rare-event statistical threshold selection.
- Stochastic event simulation.
- Topographic adjustment.
- Diagnostic reporting.

In plain language: v2.1 does not change what the model is. It makes the same model more careful, better documented, and easier to review.

---

## What the Model Does Not Do Yet

The model currently provides **hazard**, not complete insured loss.

Hazard means:

> How large is the hail, and how often does it happen?

To estimate financial loss, two additional pieces are needed:

1. **Exposure:** what buildings are located there and what they are worth.
2. **Vulnerability:** how much damage different hail sizes cause to those buildings.

The repository includes placeholder vulnerability curves, but they are not calibrated to proprietary insurance claims.

---

## Why the Model Matters

Commercial catastrophe models are often closed systems. This model is designed to be transparent and based on public data. It gives users an independent hail hazard view that can be compared with commercial models, internal underwriting assumptions, or historical loss experience.

---

## How to Interpret the Results Carefully

Shorter return periods, such as 10-year, 25-year, and 100-year hail, are more directly constrained by the historical record. Very long return periods, such as 10,000-year or 50,000-year hail, depend heavily on statistical assumptions.

For that reason, v2.1 includes extra diagnostic maps. These maps help identify places where the rare-event tail may be uncertain.

A responsible interpretation should always include:

- The return-period map.
- The stochastic comparison map.
- The validation report.
- The tail-stability diagnostics.
- A clear statement that vulnerability and exposure are not production-calibrated.

---

## Simple Summary

This model uses radar to estimate hail risk across the United States. v2.1 improves the model by making the correction, filtering, event grouping, rare-event math, and simulation steps more realistic and reviewable. It is a hazard model, not a complete loss model, but it provides a strong foundation for transparent hail risk analysis.
