# Upgrade Notes

**Scope:** v2.0 → v2.1 → **v2.2**  
**Audience:** maintainers moving an existing checkout, run plan, or review workflow to the current model.

---

## 0. v2.1 / v2.2.0 calendar-UTC → v2.2 convective days (breaking)

If you have **v2.1** (or early **v2.2.0**) daily rasters built with **UTC calendar midnight** windows:

1. **Do not mix** those GeoTIFFs with v2.2 convective-day rasters in Stages 05–15.
2. Archive or move old trees (e.g. `mesh_0.05deg_archive_calendar_utc_00z/`).
3. **Re-run** Stages **01**, **02**, and **04c** on a clean `data/historical/mesh_0.05deg/`.
4. Then run **05–15** with `--skip-ml` (or your production flags).

Definition: label `YYYY-MM-DD` = max MESH over **[D 12:00 UTC, D+1 12:00 UTC)**. See `docs/methodology.md` §2.6 and `docs/literature_review.md` §3.6.

---

## 1. Upgrade Summary (v2.0 → v2.1)

v2.1 is a hardening release. It does not change the model grid, the 15-stage
pipeline shape, or the radar-first hazard philosophy introduced in v2.0.

The practical upgrade is about provenance, safety, and reviewability:

- Stage 01 now accepts both plain `.netcdf` and `.netcdf.gz` MYRORSS archive
  objects.
- Stage 01 writes a source-coverage manifest so missing-source days are not
  confused with source-present no-hail days.
- Optional ML calibration/filtering paths are guarded by deterministic
  fallbacks and can be disabled with `--skip-ml`.
- Event grouping, tail fitting, topographic correction, and stochastic
  simulation have stronger diagnostics and safety checks.
- Tests, CI, and documentation were expanded for pre-run confidence.

---

## 2. Breaking or Behaviorally Important Changes

### 2.1 Stage 01 manifest is now required for interpretation

Do not interpret an all-zero Stage 01 TIFF without checking:

```text
data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv
```

The manifest records whether a day is source-missing, source-present with no
hail pixels, successful, partially successful with read errors, or failed.

### 2.2 Generated figures and data are not source artifacts

Generated data products and figures are excluded from git. They should be
recreated from the pipeline rather than merged into source-control history.

### 2.3 Optional ML artifacts are not mandatory

The reproducible baseline run is:

```text
python run_pipeline.py --skip-ml
```

Optional calibration artifacts may improve behavior, but they are not required
for the v2.1 baseline.

### 2.4 Sparse events are authoritative

Downstream event and stochastic stages should use sparse event representations,
not dense event cubes.

---

## 3. Recommended Upgrade Steps

1. Pull the latest `main` branch.
2. Confirm generated outputs are not staged:

```text
git status --short
```

3. Run the pre-flight checks:

```text
python -m py_compile run_pipeline.py scripts/*.py
python run_pipeline.py --dry-run
pytest -q tests -m "not integration and not regression and not slow"
```

4. For a deterministic full run, use the staged run plan in `docs/RUN_NOTES.md` with
   `--skip-ml`.
5. For Stage 01, monitor both the log and manifest status counts.
6. For Stage 01 QA repair without downloading, run
   `python scripts/01_download_myrorss.py --qa-only`; this applies the
   300.0 mm physical QA bound and refreshes manifest maxima/statuses.
7. Stage 02, Stage 04b, and Stage 05 also enforce the shared 300.0 mm hail-value
   QA cap during processing and validation.
8. After each stage, validate outputs before starting the next expensive stage.

---

## 4. Reviewer Checklist

Before treating a v2.1 run as publishable or review-ready, confirm:

- the Stage 01 manifest covers the processed period continuously;
- `missing_source` days are separated from `no_hail_pixels` days;
- `ok_with_read_errors` days are reviewed and acceptable;
- output maps pass geographic sanity checks;
- generated figures are not tracked;
- CI is green with no GitHub annotations;
- methodology, technical documentation, data dictionary, and changelog match the
  implemented behavior.

---

## 5. Relationship to v1.0

These notes focus on v2.0 -> v2.1. For the larger v1.0 -> v2.0 -> v2.1
scientific migration, see:

```text
docs/migration_plan.md
docs/PR_v1_to_v2.1.md
CHANGELOG.md
```
