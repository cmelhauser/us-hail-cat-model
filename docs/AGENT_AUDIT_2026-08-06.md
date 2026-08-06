# Full Agent Review — 2026-08-06

**Repository:** `cmelhauser/us-hail-cat-model`  
**Branch:** `v2.3.0`  
**Review target:** Complete uncommitted working tree after the 2026-08-05 fix pass  
**Scope:** Code, tests, scientific policy, manifests, operator docs, and PNAS tooling  
**Disposition:** Findings only; no fixes applied

## Executive assessment

The prior fix pass closed many real defects, and the local/AWS tests are green.
This review nevertheless found four P1 issues, five P2 issues, and two P3
hygiene failures. The most important problems are:

1. the new SPC-derived hazard path conflicts with the repository's explicit
   “SPC validation only” non-negotiable rule;
2. Stage 04c can silently accept a day when every GridRad input failed to read;
3. Stage 04c can overwrite valid source provenance after its normal input
   cleanup;
4. Stage 13 validation accepts a smoke catalog as a complete 50,000-year
   production catalog.

Do not treat the tree as release- or publication-ready until the P1 findings
are resolved and the scientific-policy decision is explicit.

## Findings

### [P1] Resolve the SPC-input policy conflict — `scripts/05_apply_mesh_bias_correction.py:624-668`

`AGENTS.md:42-45` states that SPC reports are validation only and must **never**
be used as a hazard input. The new `--allow-spc-derived-adjustments` path applies
SPC-fitted range factors directly to corrected hail rasters and then applies a
classifier trained from SPC weak labels. Calling the path “research-only” or
making it opt-in does not satisfy the current non-negotiable rule.

**Action for Grok:** choose one policy explicitly:

- remove SPC-derived range debias/classifier inference from Stage 05 hazard
  generation and keep them as diagnostics/ablation only; or
- obtain explicit scientific sign-off, revise Rule #3 and all validation claims,
  document that SPC is now a tuning input, and consider a version bump/full
  rerun.

The PNAS abstract/methods must not call SPC purely independent validation if the
accepted hazard path was tuned with SPC.

### [P1] Fail Stage 04c when every source file fails to read — `scripts/04c_fill_gridrad_gap.py:674-729`

`process_day()` catches every per-file exception, increments `errors`, then still
writes an all-zero GeoTIFF and returns a normal result. `_finalize_day()` only
increments `failed` for `result["error"]`; it therefore counts this day as done
and appends it to `gridrad_days.txt` (`scripts/04c_fill_gridrad_gap.py:1129-1142`).
Although the manifest row may say `error`, the stage exits successfully and
Stage 05 treats the zero raster as authoritative GridRad coverage.

**Action for Grok:** when `errors >= len(nc_files)` (or no file produced a valid
field), do not publish/retain a normal output and return a day-level error that
increments `failed`. Add tests for all-files-fail and partial-read-error cases.

### [P1] Preserve manifest provenance after staged inputs are deleted — `scripts/04c_fill_gridrad_gap.py:637-655`

Stage 04c normally deletes each day's GridRad inputs after processing. On a
later resume, an existing output with no staged inputs is rebuilt/upserted from
`nc_files=[]`, producing `status=missing_source`, `source_files=0`, and
`temporal_coverage_status=missing`. `rebuild_manifest_from_outputs()` repeats
the same destructive inference at lines 735-766. A direct check of
`manifest_row_for_day(..., nc_files=[], active_cells=10, skipped=True)` returns
`missing_source 0 missing`.

This overwrites valid historical source-coverage metadata and violates
AGENTS rule #9. The absence of temporary staging after cleanup is not evidence
that the original source was absent.

**Action for Grok:** on skip/rebuild, preserve the existing manifest's immutable
source/provenance/coverage fields and refresh only raster-derived fields. If no
prior row exists, recover provenance from durable GeoTIFF tags or mark it
`unknown_after_cleanup`, never `missing_source`. Add a resume-after-cleanup
regression test.

### [P1] Reject smoke or truncated Stage 13 catalogs during production validation — `scripts/13_generate_stochastic_catalog.py:459-493`

Validation now checks that the Parquet file is readable, non-empty, and has only
three columns. The accompanying test deliberately demonstrates that a one-row
catalog passes. A `--n-years 1000` smoke run writes the same map, PET, and
catalog paths as production and writes every configured RP map (return periods
above the simulated length use rank 1). Consequently, `run_pipeline.py
--validate` can falsely approve smoke outputs as the required 50,000-year
catalog.

**Action for Grok:** persist simulation metadata (`n_years`, seed, model version,
completion state) in a durable manifest/Parquet metadata and require
`n_years == N_SIM_YEARS` during production validation. Also validate the full
documented schema and year coverage. Add tests proving 1-row and 1,000-year
catalogs fail while a declared 50,000-year catalog passes.

### [P2] Reconstruct the actual Stage 05 prefilter frame on resume — `scripts/05_apply_mesh_bias_correction.py:544-565`

When a sidecar is missing or corrupt, `load_persistence_history_frame()` silently
falls back to the raw input raster. Pass 5 expects the post-quantile-map,
optionally debiased, pre-artifact-filter frame. Raw GridRad input can have a
different value distribution and active-cell mask, so pre-sidecar archives or
corrupt sidecars distort the 21-frame persistence history while claiming to be
resume-safe. Sidecar writes are also non-atomic.

**Action for Grok:** either recompute the exact prefilter frame using the active
Stage 05 mode or require a clean rebuild when a sidecar is unavailable. Write
sidecars through a temporary file plus `os.replace`, validate shape/dtype, and
log corruption instead of silently substituting raw data.

### [P2] Report the classifier's real grouped-year holdout — `scripts/diagnostics/render_pnas_article_figures.py:527-543`

The trainer now uses `GroupShuffleSplit(test_size=0.25)` grouped by whole year,
but the generated publication disclosure still says “random 80/20 split.”
`render_pnas_publication_md.py:356-362` repeats “random train/test split.”
Running the renderer would therefore insert a false methods/limitations claim
into the manuscript.

**Action for Grok:** derive disclosure text from diagnostics fields such as
`split`, `train_years`, and `holdout_years`; say that the evaluation is
year-grouped but still not an independent external validation dataset. Extend
the renderer tests to reject “random 80/20” when `split=grouped_by_year`.

### [P2] Keep acknowledgments and competing-interest sections in the publication render — `scripts/diagnostics/render_pnas_publication_md.py:366-370`

The renderer extracts Materials and Methods only up to `## Acknowledgments`,
then appends References. It never extracts or emits Acknowledgments or Competing
Interests from the source draft. A direct build check returned:

```text
## Acknowledgments False
## Competing Interests False
## References True
```

**Action for Grok:** extract and append both sections (and any author
contributions/data-availability sections required by the target journal). Add
assertions that the generated manuscript preserves them.

### [P2] Fix operator instructions that silently disable the accepted research path — `README.md:209-215`

The README tells operators to rerun Stage 05+ merely “without `--skip-ml`.”
`docs/reproduce.md:456-459` repeats the same incomplete instruction. The code
now requires `--allow-spc-derived-adjustments`; following these documents leaves
the classifier and range debias off without an error. The README's feature and
limitation text also describes range debias as though it were normal Stage 05
behavior rather than an opt-in research path.

**Action for Grok:** make every accepted research-path command include
`--allow-spc-derived-adjustments`, and label range debias/classifier consistently
as SPC-derived tuning. If P1's policy decision removes the path, remove these
instructions instead.

### [P2] Synchronize Stage 09 methodology and output schema with normalized scoring — `docs/uncertainty.md:256-267`

Stage 09 now normalizes four components to `[0,1]` and assigns equal 0.25
weights, but `docs/uncertainty.md` still says they are unnormalized and lists
normalization as future work. `docs/data_dictionary.md:366-372` and
`docs/technical_documentation.md:678-692` omit `count_penalty`, all four
`*_normalized` columns, `score`, and the actual emitted field names.

**Action for Grok:** document the implemented equation and exact CSV schema,
including fallback rows. Update methodology/uncertainty from “recommended” to
implemented, while retaining any unresolved sensitivity concern as residual
risk.

### [P3] Restore a clean full-repository Ruff run — `tests/test_04b_fill_gridrad_gap.py:48-55`

`ruff check .` fails with `RUF012` because the synthetic `Dataset.variables`
dictionary is a mutable class attribute.

**Action for Grok:** initialize `variables` on an instance, add `ClassVar`, or
use a simple namespace/mock fixture.

### [P3] Remove diff whitespace failure — `docs/pnas_article_publication.md:12`

`git diff --check` reports trailing whitespace on the stale-render model-version
line.

**Action for Grok:** remove the trailing spaces (or preserve intentional Markdown
line breaks without violating the repository's diff check).

## Verification performed

```bash
.venv/bin/python -m py_compile run_pipeline.py scripts/*.py scripts/diagnostics/*.py
.venv/bin/ruff check .
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  .venv/bin/python -m pytest -q tests
PYTHONPATH=aws OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest -q \
  aws/tests -m 'not localstack' --ignore=aws/tests/test_cdk_stack.py \
  --cov=hail_aws --cov=run_pipeline_aws --cov-fail-under=100
.venv/bin/python run_pipeline.py --dry-run
git diff --check
```

Results:

- Python compilation: passed.
- Local pipeline tests: passed.
- AWS adapter tests: passed; 100% coverage gate reached.
- Pipeline dry run: passed.
- Ruff: failed only on the P3 `RUF012` finding above.
- Diff check: failed only on the P3 trailing-whitespace finding above.

## Residual external blockers (not code-review findings)

- v2.3.0 Stages 04c→14 remain unverified since 2026-07-09.
- `data/analysis/pnas_article_metrics.json` must be regenerated from a verified
  final run before rendering/submitting the manuscript.
- Final event counts, validation metrics, radar-artifact QA, RP maps, and
  50,000-year outputs require a production rerun/validation.
- Zenodo DOI and exact manuscript commit SHA require external release actions.

## Remediation status (2026-08-06 close-out)

All P1–P3 findings above are **fixed** in the tree:

| Finding | Resolution |
|---------|------------|
| P1 SPC policy | Stage 05 no longer applies SPC range debias / classifier to hazard rasters; `--allow-spc-derived-adjustments` removed; SPC remains validation-only |
| P1 04c all-read-fail | `process_day` returns day-level `error` when every source file fails; no success GeoTIFF |
| P1 04c provenance | Skip/rebuild with empty staging preserves prior manifest provenance or uses `unknown_after_cleanup` |
| P1 Stage 13 smoke | `stochastic_catalog_manifest.json` + production validation require `n_years == N_SIM_YEARS` |
| P2 Stage 05 sidecar | Reconstruct via `apply_optional_cqm`; atomic sidecar writes |
| P2 PNAS disclosure | Year-grouped holdout text from diagnostics; no “random 80/20” |
| P2 Acknowledgments | Publication renderer emits Acknowledgments + Competing Interests |
| P2 operator docs | Opt-in SPC hazard path instructions removed |
| P2 Stage 09 docs | Normalized equal-weight score + schema documented |
| P3 Ruff / whitespace | Clean `ruff check .` and `git diff --check` |

Coverage gates: `scripts` + `run_pipeline` **100%**; AWS `hail_aws` **100%**.
External blockers (verified 04c→14 rebuild, metrics JSON, Zenodo) remain unchanged.

