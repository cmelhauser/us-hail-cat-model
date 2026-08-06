# Agent Audit & Reaudit — 2026-08-05

**Repository:** `cmelhauser/us-hail-cat-model`  
**Branch:** `v2.3.0`  
**Model version:** 2.3.0  
**Mode:** Fix all flagged items (methodology + schemas in scope) + full reaudit  
**Production rebuild:** **not** launched; run status remains **unverified since 2026-07-09**

This document captures (1) the initial full-repo audit findings, (2) fixes
applied in this working tree, (3) local verification evidence, and (4) an
independent reaudit of residual / external blockers.

---

## 1. Executive summary

| Stream | Initial audit | After fix pass | Reaudit |
|--------|---------------|----------------|---------|
| Stage 05 radar QA / SPC policy | High defects | Code fixed | Docs mostly synced; residual Low wording possible |
| Stage 04c GridRad QC / resume | High defects | Code fixed | Fixed |
| Engineering / tests / deps | Medium–High | Fixed + tests | Stage 13 Parquet validate deepened |
| Docs / operator guides | High contradictions | Synced to SPC opt-in | Residual Low (e.g. executive_summary framing) |
| PNAS manuscript tooling | High stale claims | Renderer + draft fixed; checked-in render marked STALE | External: need metrics JSON + verified run |
| Hazard numbers / Zenodo | External | Unchanged | Still open |

**Bottom line:** Treat the **code and documentation fix pass as largely
successful** for the audited defects. Do **not** cite v2.3.0 hazard metrics or
submit the PNAS render from this tree alone. A verified Stages **04c→14**
rebuild, metrics freeze, and Zenodo DOI remain external gates.

---

## 2. Original findings (pre-fix)

### 2.1 Radar / Stage 05–04c (High)

| ID | Finding |
|----|---------|
| A01 | Stage 05 persistence history broke on resume (skip existing outs without updating `_gridrad_history`) |
| A02 | Stage 04c `gridrad_days.txt` incomplete after resume (skipped existing days not merged) |
| A03 | Docs claimed hard **0.65** artifact zeroing; code used probability / hail-likelihood down-weighting |
| A04 | Docs claimed Stage 06 KS overlap test that does not exist |
| A05 | Classifier applied to all sources; should be GridRad-gated / research-only |
| A06 | Era-pooled QM uses non-overlapping eras — methodological risk under-documented |
| A07 | SHI used fixed 1 km `dh`; Mesh75 constants duplicated in 04c |
| A08 | GridRad QC missing v4.2 **W &lt; 1.5** weight filter; weak-shallow clutter defaulted off |
| A09 | SPC-derived range debias / classifier violated “SPC validation only” when applied by default |

### 2.2 Engineering / tests (Medium–High)

| ID | Finding |
|----|---------|
| B01 | `cfgrib` / `eccodes` required by pipeline but missing from `pyproject.toml` |
| B02 | No golden/regression tests; Stage 05 `--skip-ml` not behaviorally tested |
| B03 | Non-deterministic `random.sample` in stage validates |
| B04 | Stage 12 non-atomic GeoTIFF rewrite |
| B05 | `KeyboardInterrupt` risk if `proc` unset in `run_pipeline.py` |
| B06 | Stage 08 CSV/NPZ consistency gap |
| B07 | Stage 13 Parquet validate was existence-only |
| B08 | Stage 09 threshold score components not normalized |

### 2.3 Docs / PNAS (High)

| ID | Finding |
|----|---------|
| C01 | Conflicting run status across `RUN_NOTES` / `HANDOFF` / `project_memory` / `AGENTS` |
| C02 | Classifier train-before-04c vs train-after-06 contradiction |
| C03 | `site_remediation` docs said OFF; code default ON |
| C04 | Publication MD frozen at v2.2.2 with contradictory stochastic/IoD claims |
| C05 | Hard-coded 173,766 pairs; GridRad `missing_source` template dash bug |
| C06 | SPC tuning leakage undisclosed; SHA/DOI TBD |

---

## 3. Fixes applied (this working tree)

### 3.1 Science / Stage 05

- Resume-safe persistence sidecars: `mesh_YYYYMMDD.tif.prefilter_history.npy`
  (`PERSISTENCE_HISTORY_SIDECAR`); load on skip, save when filtering.
- **`--allow-spc-derived-adjustments`** (Stage 05 + `run_pipeline.py`): gates
  SPC-collocated range debias and hail-likelihood classifier; ignored with
  `--skip-ml`.
- Classifier: GridRad-only; `apply_hail_likelihood_weights` (multiply, not 0.65
  hard zero); trainer defaults to GridRad pairs + year-grouped holdout.
- Docstring / Phase A end year aligned to 2020; Mesh75 constants from `_config`.

### 3.2 Stage 04c / GridRad QC / I/O

- Skip-existing days append labels; `merge_gridrad_days_labels` /
  `rebuild_gridrad_days_from_geotiffs`.
- `temporal_coverage_summary` + manifest fields + GeoTIFF tags.
- SHI vertical spacing via `np.gradient`; shared `MESH75_A/B`.
- `_gridrad_qc.py`: min weight 1.5; weak-shallow clutter default **on**.
- Failed day counting can fail the stage; sparse `wReflectivity` support.

### 3.3 Engineering

- `cfgrib` / `eccodes` in `pyproject.toml` + `requirements.txt`.
- `proc = None` before Popen; seeded validation sampling (`RNG_SEED`).
- Stage 12 atomic rewrite; Stage 08 CSV↔NPZ ID checks; Stage 09 score
  normalization; Stage 13 Parquet schema/non-empty checks.
- GEOTIFF nodata uses shared `NODATA`.

### 3.4 Docs / PNAS

- Synced: `AGENTS.md`, `RUN_NOTES.md`, `HANDOFF.md`, `reproduce.md`,
  `methodology.md` §5.5, `data_dictionary.md`, `uncertainty.md`,
  `technical_documentation.md`, `FAQ.md`, `radar_artifact_ml_plan.md`,
  draft `pnas_article_ai_hail_model.md`, publication renderer.
- Checked-in `docs/pnas_article_publication.md` marked **STALE**; GridRad
  `— missing_source` dash repaired with historical freeze note.

### 3.5 Tests added / extended

- Stage 05: sidecar resume, classifier gates, range-debias opt-in, skip-ml.
- 04c / QC / artifact features / trainer / Stage 08–09 / Stage 12–13 /
  dependency metadata / validation sampling / PNAS renderer / run_pipeline
  flag forwarding.

---

## 4. Local verification (2026-08-05)

Commands run from repo root with `.venv` (Python 3.12):

```bash
.venv/bin/python -m py_compile run_pipeline.py scripts/*.py
.venv/bin/ruff check scripts/05_apply_mesh_bias_correction.py \
  scripts/13_generate_stochastic_catalog.py run_pipeline.py \
  scripts/_gridrad_qc.py scripts/_artifact_features.py scripts/04c_fill_gridrad_gap.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests
.venv/bin/python run_pipeline.py --dry-run
```

| Check | Result |
|-------|--------|
| Focused + full `tests/` suite | Green (NumPy 2.5 deprecation warnings only) |
| Ruff on touched core modules | All checks passed |
| `run_pipeline.py --dry-run` | All stages listed; nothing executed |
| AWS `hail_aws` 100% coverage gate | **100%** (`pytest` with cov; LocalStack/CDK synth ignored) |
| `pnas_article_metrics.json` | **Missing** |
| Production `--validate` / 04c→14 rebuild | **Not run** (out of scope for this session) |

---

## 5. Reaudit findings (post-fix)

Independent reaudit after the fix pass. Severity is for **remaining** risk.

| ID | Severity | Status | Evidence | Action |
|----|----------|--------|----------|--------|
| RA-01 | High→Fixed | Fixed | `docs/RUN_NOTES.md` research path now includes `--allow-spc-derived-adjustments` | — |
| RA-02 | High→Fixed | Fixed | `docs/technical_documentation.md` no longer says automatic range debias | — |
| RA-03 | High→Fixed | Fixed | `docs/FAQ.md` radar-rings answer uses deterministic baseline + opt-in note | — |
| RA-04 | Medium→Fixed | Fixed | `docs/HANDOFF.md` runner CLI includes opt-in flag | — |
| RA-05 | Medium | Open | `docs/executive_summary.md` may still frame rebuild without full RUN_NOTES caveat | Point solely to RUN_NOTES canonical state |
| RA-06 | Medium | Partial | Persistence sidecar fallback can read **input** MESH if sidecar absent (pre-sidecar archives) | Clean rebuild of Stage 05 for Pass-5 fidelity |
| RA-07 | Medium→Fixed | Fixed | Stage 13 validate checks non-empty Parquet + required columns | — |
| RA-08 | Medium→Fixed | Fixed | `test_stage05_range_debias_requires_spc_opt_in` | — |
| RA-09 | Medium | Open | Stale checked-in PNAS publication render | Regenerate after metrics JSON exists |
| RA-10 | Medium | Open | Draft still has provisional TBD event counts in places | Freeze after validated Stage 08/13 |
| RA-11 | Low | Open | Occasional “five-pass” shorthand without naming site remediation | Prefer “five core + site remediation” |
| RA-12 | Low | Partial | Site remediation default covered in geometry tests, not Stage 05 process_file wiring | Optional |
| RA-22 | Critical* | External | v2.3.0 Stages 04c–14 unverified since 2026-07-09 | Inspect logs; rebuild; `--validate` |
| RA-23 | Critical* | External | Zenodo DOI + manuscript SHA TBD | GitHub Release `v2.3.0` → Zenodo |

\*Critical for **publication readiness**, not for local code correctness of this fix pass.

### Still Fixed (reaudit confirmed)

SPC opt-in gate; GridRad-only hail-likelihood classifier; `--skip-ml` fallbacks;
site remediation default on; 04c day-list merge + temporal coverage; SHI `dh` /
MESH75 constants; W&lt;1.5 + weak-shallow defaults; cfgrib/eccodes; KeyboardInterrupt
safety; seeded sampling; Stage 12 atomic writes; Stage 08 CSV/NPZ; Stage 09
normalization.

---

## 6. Suggested edits already landed (summary for reviewers)

1. Gate all SPC-derived hazard adjustments behind `--allow-spc-derived-adjustments`.
2. Persist GridRad pre-filter frames for Pass-5 resume safety.
3. Merge skipped 04c days into `gridrad_days.txt`; record temporal coverage.
4. Align SHI/MESH75 and GridRad native QC with literature defaults.
5. Replace “0.65 artifact zero” documentation with hail-likelihood down-weighting.
6. Harden Stage 08/12/13 validation and Stage 09 threshold scoring.
7. Mark PNAS checked-in render STALE; drive numbers from metrics JSON only.
8. Canonicalize operator docs on deterministic Stage 05 → 06 → optional research path.

---

## 7. Explicitly out of scope / cannot close here

1. Verified completion of v2.3.0 Stages **04c → 14**.
2. Final hazard metrics (events, λ, POD, RP peaks, speckle %, stochastic size).
3. Fresh `range_debias.npz` / classifier metrics after deterministic baseline.
4. Regenerated `pnas_article_metrics.json` + publication MD/figures from a frozen run.
5. Zenodo code/outputs DOIs and manuscript commit SHA.
6. Scientific acceptance of the SPC-derived research path (policy call).
7. End-to-end 50k-yr Stage 13 runtime proof on production hardware.
8. Golden checksum freeze of production GeoTIFF/NPZ artifacts.

---

## 8. Recommended next operator actions

```bash
# 1. Inspect whether a rebuild is still required
#    (see docs/RUN_NOTES.md#canonical-current-run-state)

# 2. Deterministic rebuild path (if needed)
.venv/bin/python run_pipeline.py --only 04c --clean-from 04c
.venv/bin/python run_pipeline.py --only 05 --skip-ml
.venv/bin/python run_pipeline.py --from 06 --skip-ml

# 3. Optional research path only after Stage 06 + classifier review
.venv/bin/python scripts/train_artifact_classifier.py
.venv/bin/python run_pipeline.py --from 05 --clean-from 05 --allow-spc-derived-adjustments

# 4. After final path
.venv/bin/python scripts/13_generate_stochastic_catalog.py --n-years 1000
.venv/bin/python run_pipeline.py --validate
.venv/bin/python scripts/diagnostics/radar_artifact_diagnostic.py
.venv/bin/python scripts/diagnostics/literature_validation_suite.py
.venv/bin/python scripts/diagnostics/render_pnas_article_figures.py
.venv/bin/python scripts/diagnostics/render_pnas_publication_md.py
```

Then mint Zenodo DOIs from a GitHub Release and record `git rev-parse HEAD` in
the manuscript / `CITATION.cff` / `DATA_AVAILABILITY.md`.

---

## 9. Change inventory note

This audit accompanies an **uncommitted** working-tree fix pass on `v2.3.0`
(dozens of modified docs/scripts/tests plus new test modules). No commit or
push was made as part of this audit session unless the operator requests one.
