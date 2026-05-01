# What This Model Does — Plain Language Explainer

## The Problem

Hailstorms cause billions of dollars in property damage annually in the United States. Insurance and reinsurance companies need to understand how often damaging hail occurs at any given location and how severe it can be. This requires a mathematical model that captures both the spatial patterns and the statistical tails of hail hazard.

## What We Built

A probabilistic hail hazard model for the entire continental United States that answers two questions for any location:

1. **How often does hail occur?** The model provides annual probabilities that hail exceeds various size thresholds (1 inch, 2 inches, etc.).
2. **How big can it get?** The model provides return period estimates — for example, "the once-in-100-years hail size at this location is 3.2 inches."

## How It Works

**Step 1 — Radar data, not storm reports.** Previous models relied on eyewitness reports of hail, which are biased toward cities and daytime. Our model uses ~28 years of weather radar data that detects hail everywhere, day or night, populated or not. Three radar sources are stitched together to build a continuous record from 1998 to today.

**Step 2 — Calibrate the radar.** Radar estimates of hail size are intentionally high (they're designed for warning, not measurement). We apply a published correction that brings them in line with ground observations.

**Step 3 — Fit statistical distributions.** At each ~5.5 km grid cell, we fit a statistical model to the historical hail record. The body of the distribution captures typical events; the tail uses extreme value theory (GPD) to characterize rare, large hail. Nearby cells share information to stabilize the fits.

**Step 4 — Simulate 50,000 years.** We resample from the historical event catalog with random perturbations to intensity and location, generating a synthetic record far longer than the observed 28 years. This allows us to estimate very long return periods (200-year, 500-year) with quantified confidence.

## What It Doesn't Do (Yet)

The model produces **hazard only** — how big the hail is and how often it occurs. To estimate insured losses, two additional layers are needed: vulnerability (how much damage does 2-inch hail cause to different roof types?) and exposure (what properties exist at each location, and what are they worth?). These are planned as future additions.

## Why It Matters

This model uses only publicly available data and open-source code. It provides an independent, transparent hail hazard view that can be compared against commercial models (AIR, RMS) and used for portfolio management, risk selection, and regulatory filings.
