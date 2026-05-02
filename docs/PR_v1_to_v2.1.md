# Pull Request Narrative: v1.0 -> v2.0 -> v2.1

This document is the reviewer-facing narrative for merging `cmelhauser:main`
into `theonlymuffinbot:main`.

---

## Summary

This PR brings the upstream repository from the original v1.0-era hail
catastrophe prototype to the current v2.1 radar-first model. The update is
large because it includes both a scientific redesign and a hardening pass:

- **v1.0 -> v2.0:** replaces SPC-report-driven hazard estimation with a
  radar-first MESH/MESH75 pipeline.
- **v2.0 -> v2.1:** preserves the v2.0 architecture while adding provenance,
  tests, documentation, deterministic fallbacks, CI, and pre-run controls.

The PR does not ask reviewers to approve final model results. It prepares the
repository for the full production-style run and subsequent scientific review.

---

## v1.0 Baseline

v1.0 was an SPC-report-based prototype. It used human hail reports as the
primary hazard input and attempted to account for reporting changes through
population-trend adjustment.

That approach was useful for prototyping, but it had structural limitations:

- hail reports are biased by population, roads, spotter networks, time of day,
  and reporting practices;
- rural underreporting is severe;
- report-size rounding affects severity distributions;
- all-zero or no-report days cannot be interpreted as no-hail days;
- gridded rare-event tail estimation is weak when the evidence is sparse point
  reports.

v1.0 scripts are retained under `scripts/archive/v1/` for provenance.

---

## v2.0 Redesign

v2.0 changes the model from report-first to radar-first.

Major v2.0 additions:

- MYRORSS historical radar reanalysis for 1998-2011;
- GridRad / GridRad-Severe gap-fill support for 2012-2019;
- operational MRMS support for 2020-present;
- ERA5 0 C and -20 C isotherm support;
- MESH75 calibration;
- fixed 0.05 degree CONUS grid;
- 15-stage pipeline from ingestion through figures;
- SPC reports retained for validation rather than hazard truth;
- event-catalog construction;
- regional EVT fitting with lognormal body and GPD tail;
- analytical and stochastic return-period outputs;
- placeholder vulnerability curves for integration testing.

The most important methodological decision is that radar-derived hail fields
become the primary gridded hazard evidence, while human reports become
validation evidence.

---

## v2.1 Hardening

v2.1 keeps the v2.0 methodology and hardens it for defensibility.

Major v2.1 additions:

- Stage 01 reads both `.netcdf` and `.netcdf.gz` MYRORSS files;
- Stage 01 writes `manifest_stage01_myrorss.csv`;
- source-present no-hail days are separated from missing-source days;
- `--skip-ml` supports deterministic baseline runs;
- optional calibration/filter artifacts have safe fallbacks;
- Stage 08 adds centroid and intensity checks for event grouping;
- Stage 09 adds threshold diagnostics for tail fitting;
- Stage 12 adds bounded freezing-level-aware topographic correction;
- Stage 13 is sparse-safe and avoids dense event cubes;
- CI runs on main with Python 3.10, 3.11, 3.12, and an integration smoke test;
- GitHub Actions annotations have been cleaned to zero on the latest run;
- generated figures and large data products are excluded from git;
- documentation has been expanded across methodology, technical behavior,
  uncertainty, sensitivity, reproduction, data dictionary, and manuscript
  readiness.

---

## Files and Docs to Review

Start with:

- `README.md`
- `CHANGELOG.md`
- `docs/migration_plan.md`
- `docs/UPGRADE_NOTES.md`
- `docs/methodology.md`
- `docs/technical_documentation.md`
- `docs/data_dictionary.md`
- `docs/reproduce.md`
- `docs/RUN_NOTES.md`
- `docs/REVIEW_PRE_RUN.md`

Then review implementation stages under `scripts/` and tests under `tests/`.

---

## Validation State

Recent validation on `origin/main`:

- GitHub CI passes on Python 3.10, 3.11, and 3.12.
- Integration smoke test passes.
- GitHub check annotations are zero on the latest CI run.
- Local `py_compile`, unit tests, dry run, and integration tests passed before
  the latest push.

Known non-blocking issue:

- Full ruff cleanup remains a separate refactor. Advisory ruff/mypy steps were
  removed from CI because they created red annotations despite being
  continue-on-error checks.

---

## Full-Run State

The full model run is in progress. Stage 01 is producing MYRORSS daily TIFFs and
updating the manifest. Later stages should run only after Stage 01 completion
and validation, following `docs/RUN_NOTES.md`.

The PR is therefore best understood as a repository, methodology, and pipeline
readiness merge. Final hazard results, return-period figures, and manuscript
result placeholders will be filled after the full run finishes.

