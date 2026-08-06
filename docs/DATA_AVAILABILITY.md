# Data and Code Availability

**Model version:** 2.3.0  
**Maintainer:** Christopher Melhauser  
**AI collaborator:** theonlymuffinbot (project pseudonym for all AI work; not a
separate GitHub repository)  
**ORCID:** [0009-0000-4234-5419](https://orcid.org/0009-0000-4234-5419)  
**Last updated:** 2026-07-30

This document records where code, figures, and generated outputs live. The git
repository holds **source code and documentation only**; pipeline data and
figures are stored externally or regenerated locally.

---

## Identifiers (fill in after first upload)

The DOI and manuscript commit SHA are **external blockers**, not values that can
be completed by editing this repository. Do not invent identifiers. Populate
them only after the v2.3.0 release is archived and the exact submission
snapshot is selected.

| Artifact | Status | Location / DOI |
|----------|--------|----------------|
| Source code (GitHub) | Active | [github.com/cmelhauser/us-hail-cat-model](https://github.com/cmelhauser/us-hail-cat-model) |
| Manuscript commit SHA | TBD | Record the exact `git rev-parse HEAD` used for the PNAS submission |
| Code archive (Zenodo, via GitHub Release) | **External blocker — pending** | Real DOI pending publication of GitHub Release **`v2.3.0`** |
| Generated outputs (Zenodo, manual upload) | **External blocker — pending** | Real DOI pending upload of the matching **v2.3.0** `data/` + `docs/figures/` bundle (see §3) |

After the first Zenodo deposit, replace `TBD` entries above and in `CITATION.cff`,
`docs/pnas_article_ai_hail_model.md`, and optionally add a README DOI badge.

---

## 1. What stays in git

- Python pipeline (`scripts/`, `run_pipeline.py`, `tests/`)
- Documentation (`docs/`, `AGENTS.md`, `README.md`)
- Configuration (`pyproject.toml`, `environment.yml`, `Dockerfile`)
- Citation metadata (`CITATION.cff`, `.zenodo.json`)

**Not in git:** `data/`, `docs/figures/`, `logs/` (see `.gitignore`).

---

## 2. Code archive on Zenodo (GitHub integration)

Each **GitHub Release** tagged **`v2.X.X`** (semantic version matching
`CHANGELOG.md` / `CITATION.cff`) produces a separate **version DOI** on Zenodo.
All versions share one **concept DOI** (always resolves to the latest release).

Historical check (2026-07-05): the Zenodo account was linked and no deposit
existed. Reverify externally before publishing v2.3.0.

### One-time setup (if not already done)

1. Log in at [zenodo.org](https://zenodo.org/) (ORCID or GitHub login).
2. Profile menu → **GitHub** → **Sync now**.
3. Enable **`cmelhauser/us-hail-cat-model`** (toggle **On**).
4. Confirm **ORCID** is linked under account settings (deposits can sync to
   [0009-0000-4234-5419](https://orcid.org/0009-0000-4234-5419)).

Zenodo reads metadata from `.zenodo.json` (highest priority) and `CITATION.cff`.
The GitHub integration archives **source code only** (what is in the git tree).
Gitignored `data/` and `docs/figures/` are **not** included in that snapshot.

### Publish the v2.3.0 code DOI

1. Merge or tag the release commit.
2. On GitHub: **Releases → Draft a new release**.
   - Tag: `v2.3.0`
   - Title: `CONUS Hail Catastrophe Model v2.3.0`
   - Description: point to `CHANGELOG.md` and this file.
3. Publish the release. Zenodo archives the repository snapshot within minutes.
4. Copy the **version DOI** for that tag into the table in § Identifiers and
   into `CITATION.cff` (`doi:` field) for the manuscript tied to that release.

**Concept DOI** (latest): Zenodo record landing page. **Version DOI**: specific
to each `v2.X.X` tag.

---

## 3. Full generated outputs on Zenodo (manual upload)

**Policy:** If the compressed release tarball is **≤ 50 GB**, host the complete
generated outputs on Zenodo in **one dataset record per `v2.X.X` release**
(figures, diagnostics, corrected rasters, catalogs, validation, CDF maps, etc.).
Request extra Zenodo quota if a future release exceeds the default per-record limit.

### Zenodo limits (confirm before upload)

| Limit | Value | Implication |
|-------|------:|-------------|
| Default per record | **50 GB** | No extra quota management needed if tarball is below this |
| Files per record | **100** | Use one or two `.tar.gz` files, not thousands of loose GeoTIFFs |
| Account extra pool | **150 GB** total | Assignable across records via **Manage storage** if you ever need > 50 GB on one record (up to ~200 GB) |

See [Zenodo storage quota](https://help.zenodo.org/docs/deposit/manage-quota/) and
[size limitations FAQ](https://support.zenodo.org/help/en-gb/1-upload-deposit/80-what-are-the-size-limitations-of-zenodo).

**Verify size locally before uploading:**

```bash
du -sh data/ docs/figures/
# After building tarball:
ls -lh us-hail-cat-model-v2.X.X-generated-outputs.tar.gz
```

If `du` shows the tree near or above 50 GB uncompressed, compress aggressively
(`.tar.gz` or `.tar.zst`) and confirm the **upload file** is still ≤ 50 GB.

### Generate locally

Run only after the v2.3.0 production pipeline is verified:

```bash
# Diagnostics
.venv/bin/python scripts/diagnostics/summarize_mesh_daily_peaks.py
.venv/bin/python scripts/diagnostics/hail_day_climatology.py

# PNAS figures
.venv/bin/python scripts/diagnostics/render_pnas_article_figures.py

# Supplementary maps
.venv/bin/python scripts/14_render_figures.py
```

### Build the upload tarball

From the repository root:

```bash
VERSION=v2.3.0
BUNDLE="us-hail-cat-model-${VERSION}-generated-outputs"

mkdir -p "/tmp/${BUNDLE}"
cp -R data docs/figures "/tmp/${BUNDLE}/"

tar -czf "${BUNDLE}.tar.gz" -C /tmp "${BUNDLE}"
ls -lh "${BUNDLE}.tar.gz"
```

Omit `logs/` unless needed for audit; omit raw GridRad staging trees under
`data/historical/gridrad*` if present and already reproduced by Stage 04c.

### Upload to Zenodo

1. [zenodo.org/deposit/new](https://zenodo.org/deposit/new)
2. **Upload type:** Dataset
3. **Title:** `CONUS Hail Catastrophe Model v2.X.X — generated outputs`
4. **Creators:** Christopher Melhauser — ORCID `0009-0000-4234-5419`;
   theonlymuffinbot (AI collaborator pseudonym)
5. **Description:** List major paths (`mesh_0.05deg_corrected/`, `events/`,
   `analysis/cdf/`, `stochastic/`, `docs/figures/`, diagnostics). Link to the
   **code version DOI** for the same `v2.X.X` tag and the GitHub commit SHA.
6. **Related identifiers:** Link to the code Zenodo record (`isDocumentedBy` /
   `isSupplementTo` the code release).
7. **License:** MIT for code-derived artifacts, or CC-BY-4.0 for figures if preferred.
8. Upload `${BUNDLE}.tar.gz` (single file stays under the 100-file limit).
9. Publish and record the DOI in § Identifiers above.

For each future model release, publish a new GitHub Release **`v2.X.X`**, a new
code version DOI (automatic), and a matching generated-outputs dataset (manual).

**Moving data between machines (pre-release):** Copy the `data/` and
`docs/figures/` trees locally (e.g. external USB drive). Paths match the repo
layout; after `git clone`, paste them at the repository root. Do not commit
these directories to git.

---

## 4. Manuscript text (PNAS data availability)

After DOIs are minted, use language like:

> Source code for the CONUS Hail Catastrophe Model v2.3.0 is available at
> https://github.com/cmelhauser/us-hail-cat-model (commit `<SHA>`) and archived
> on Zenodo (DOI `<code-version-doi>`). Generated pipeline outputs and figures
> for the same release are archived on Zenodo (DOI `<outputs-doi>`). Outputs are
> not committed to the source repository because of size; they can also be
> reproduced from public radar and reanalysis inputs following `docs/reproduce.md`.

---

## 5. Pre-submission checklist

- [ ] ORCID [0009-0000-4234-5419](https://orcid.org/0009-0000-4234-5419) linked on Zenodo
- [ ] GitHub repository enabled on Zenodo (profile → GitHub → sync)
- [ ] GitHub Release `v2.3.0` published → real code version DOI recorded
- [ ] Generated-outputs tarball (≤ 50 GB) uploaded → outputs DOI recorded
- [ ] Commit SHA recorded for manuscript
- [ ] `CITATION.cff` updated with code DOI
- [ ] `docs/pnas_article_ai_hail_model.md` § Data and code availability updated
- [ ] README DOI badge added (optional)

---

## Related documents

- [`reproduce.md`](reproduce.md) — full pipeline reproduction
- [`data_dictionary.md`](data_dictionary.md) — output schemas
- [`pnas_publication_readiness.md`](pnas_publication_readiness.md) — submission checklist
- [`../CITATION.cff`](../CITATION.cff) — citation metadata
- [`../.zenodo.json`](../.zenodo.json) — Zenodo deposit metadata for GitHub releases
