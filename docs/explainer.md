# What This Model Does — Plain-Language Explainer

**CONUS Hail Catastrophe Model v2.1**

---

## 1. The Problem

Hail causes major property damage in the United States. Insurers, reinsurers, risk managers, and researchers need to know how often damaging hail occurs and how severe hail can become at different locations.

The problem is that many historical hail datasets are based on human reports. Human reports are useful but biased. Hail is reported more often near towns, roads, and people. Rural storms can be missed. Hail sizes are often rounded to familiar objects such as quarters, golf balls, or baseballs.

This model uses radar-derived hail estimates instead of relying on human reports as the main input.

---

## 2. What the Model Produces

For each small grid cell across the continental United States, the model estimates:

1. how often hail occurs;
2. how large hail can get;
3. how rare a given hail size is;
4. where the estimates are more uncertain.

Example:

> “At this location, the 100-year hail size is estimated to be about 3 inches.”

This means the model estimates roughly a 1% annual chance of hail at least that large at that location.

---

## 3. How the Model Works

### Step 1 — Use radar

The model uses radar products that estimate hail size across the country. Radar can observe storms in rural areas, at night, and away from roads.

### Step 2 — Put all data on one grid

Every day becomes a hail map on the same grid, about 5.5 km per cell.

### Step 3 — Correct radar bias

Radar hail estimates are not perfect. Some sources overestimate hail. Some may miss short-lived peaks. The model corrects source differences so the record is more consistent.

### Step 4 — Filter unlikely hail

Some radar signals can look hail-like even if hail is unlikely to reach the ground. v2.1 supports probability-based filtering so questionable signals can be reduced instead of simply removed.

### Step 5 — Identify hail events

The model groups hail days into storm events. v2.1 adds checks so unrelated storms are less likely to be merged into one event.

### Step 6 — Fit rare-event statistics

The model estimates ordinary hail sizes and rare hail sizes using statistical distributions. Rare extremes are modeled with extreme-value theory.

### Step 7 — Simulate many years

Because the historical record is only a few decades long, the model simulates 50,000 years of synthetic hail events by resampling and perturbing real historical events.

### Step 8 — Compare two estimates

The model compares:

1. analytical estimates from statistical distributions;
2. empirical estimates from the stochastic simulation.

If the two disagree strongly, that area is flagged for review.

---

## 4. What v2.1 Improves

v2.1 improves:

- radar-source calibration;
- environmental filtering;
- event grouping;
- rare-event threshold selection;
- memory safety in the stochastic simulation;
- topographic correction;
- validation and diagnostics;
- tests and documentation.

---

## 5. What the Model Does Not Do

This is a hazard model, not a complete insured-loss model.

Hazard means:

> How large is the hail, and how often does it happen?

To estimate financial loss, two more pieces are needed:

1. exposure — what buildings are there and what are they worth?
2. vulnerability — how much damage does hail cause to those buildings?

The repository includes placeholder vulnerability curves, but they are not calibrated to insurance claims.

---

## 6. How to Interpret Results

Short return periods, such as 10-year and 100-year hail, are more directly supported by the historical record. Very long return periods, such as 10,000-year or 50,000-year hail, depend more heavily on model assumptions.

A responsible interpretation should include:

- the return-period map;
- the validation report;
- the stochastic comparison;
- the tail-stability diagnostics;
- a clear statement that vulnerability is placeholder only.

---

## 7. Simple Summary

This model uses radar to estimate hail risk across the United States. v2.1 makes the model more careful, better documented, more memory-safe, and easier to review.
