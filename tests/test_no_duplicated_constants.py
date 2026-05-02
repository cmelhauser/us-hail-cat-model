"""
test_no_duplicated_constants.py
================================
Enforces that stage scripts use canonical constant values matching
scripts/_config.py.

After the _config.py import refactor (post-run priority #2), all stage scripts
should import grid constants from _config rather than redefining them inline.
Until then, this test validates that any inline definitions still agree with
the canonical source of truth.

What this test catches:
  - Inline grid constants that drift from _config.py values (e.g., someone
    changes NROWS to 521 inline without updating _config.py)
  - New inline constants added to a script after the refactor is applied to
    that script (regression guard)
  - The known MAX_CENTROID_KM_DAY discrepancy (stage 08 = 100, _config = 150)
    is tracked as an explicit xfail until resolved

After the refactor is complete, these tests continue to pass because each
script's attribute is the value imported from _config, which equals the
expected canonical value.

Implementation note:
  Scripts 01 and 02 use native-grid→output-grid derivation with variable
  names OUT_NROWS, OUT_NCOLS, OUT_LAT_MAX, OUT_LON_MIN rather than NROWS etc.
  Those are checked by their output names. Scripts 03, 04a, 14 have no grid
  constants and are not listed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ── Canonical values from _config.py ─────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"


def _load_config():
    spec = importlib.util.spec_from_file_location("_config", SCRIPTS / "_config.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_config"] = mod
    spec.loader.exec_module(mod)
    return mod


cfg = _load_config()


def _load(filename: str):
    path = SCRIPTS / filename
    module_name = "stage_const_" + filename.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# 1. Grid geometry: NROWS = 520
#
# Scripts 04b, 05, 06, 07, 08, 09, 10, 11, 12, 13, 15 define NROWS = 520.
# Scripts 01, 02 define OUT_NROWS (derived from native grid, same value).
# ─────────────────────────────────────────────────────────────────────────────

SCRIPTS_WITH_NROWS = [
    "06_validate_mesh_vs_spc.py",
    "07_build_hail_climo.py",
    "08_build_event_catalog.py",
    "09_fit_cdf_regional.py",
    "10_build_smooth_cdf.py",
    "11_build_occurrence_probs.py",
    "12_apply_conus_mask.py",
    "13_generate_stochastic_catalog.py",
    "15_render_figures.py",
]

SCRIPTS_WITH_OUT_NROWS = [
    "01_download_myrorss.py",
    "02_download_mrms_mesh.py",
    "04b_fill_gridrad_gap.py",
    "05_apply_mesh_bias_correction.py",
]


@pytest.mark.parametrize("script", SCRIPTS_WITH_NROWS)
def test_nrows_matches_config(script):
    s = _load(script)
    assert s.NROWS == cfg.NROWS, (
        f"{script}: NROWS={s.NROWS} does not match _config.NROWS={cfg.NROWS}"
    )


@pytest.mark.parametrize("script", SCRIPTS_WITH_OUT_NROWS)
def test_out_nrows_matches_config(script):
    s = _load(script)
    assert s.OUT_NROWS == cfg.NROWS, (
        f"{script}: OUT_NROWS={s.OUT_NROWS} does not match _config.NROWS={cfg.NROWS}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Grid geometry: NCOLS = 1180
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("script", SCRIPTS_WITH_NROWS)  # same scripts have NCOLS
def test_ncols_matches_config(script):
    s = _load(script)
    assert s.NCOLS == cfg.NCOLS, (
        f"{script}: NCOLS={s.NCOLS} does not match _config.NCOLS={cfg.NCOLS}"
    )


@pytest.mark.parametrize("script", SCRIPTS_WITH_OUT_NROWS)
def test_out_ncols_matches_config(script):
    s = _load(script)
    assert s.OUT_NCOLS == cfg.NCOLS, (
        f"{script}: OUT_NCOLS={s.OUT_NCOLS} does not match _config.NCOLS={cfg.NCOLS}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. RP_YEARS must match _config wherever defined inline
#
# Scripts 09, 10, 13, 15 still define RP_YEARS inline. These should agree
# with _config.RP_YEARS.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPTS_WITH_RP_YEARS = [
    "09_fit_cdf_regional.py",
    "10_build_smooth_cdf.py",
    "13_generate_stochastic_catalog.py",
    "15_render_figures.py",
]


@pytest.mark.parametrize("script", SCRIPTS_WITH_RP_YEARS)
def test_rp_years_matches_config(script):
    s = _load(script)
    script_rp = tuple(s.RP_YEARS)
    assert script_rp == cfg.RP_YEARS, (
        f"{script}: RP_YEARS={script_rp} does not match _config.RP_YEARS={cfg.RP_YEARS}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. DAMAGE_THRESH_MM must match _config wherever defined inline
#
# Scripts 08 and 13 define DAMAGE_THRESH_MM or DAMAGE_THRESHOLD_MM inline.
# ─────────────────────────────────────────────────────────────────────────────

def test_damage_threshold_stage08_matches_config():
    s = _load("08_build_event_catalog.py")
    # Stage 08 uses DAMAGE_THRESHOLD_MM (note: _MM not _THRESH)
    script_val = getattr(s, "DAMAGE_THRESHOLD_MM", getattr(s, "DAMAGE_THRESH_MM", None))
    assert script_val is not None, "Stage 08: could not find DAMAGE_THRESHOLD_MM or DAMAGE_THRESH_MM"
    assert script_val == cfg.DAMAGE_THRESH_MM, (
        f"Stage 08 damage threshold {script_val} != _config {cfg.DAMAGE_THRESH_MM}"
    )


def test_damage_threshold_stage13_matches_config():
    s = _load("13_generate_stochastic_catalog.py")
    script_val = getattr(s, "DAMAGE_THRESH_MM", getattr(s, "DAMAGE_THRESHOLD_MM", None))
    assert script_val is not None, "Stage 13: could not find DAMAGE_THRESH_MM or DAMAGE_THRESHOLD_MM"
    assert script_val == cfg.DAMAGE_THRESH_MM, (
        f"Stage 13 damage threshold {script_val} != _config {cfg.DAMAGE_THRESH_MM}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. MAX_CENTROID_KM_DAY discrepancy — tracked as xfail
#
# Stage 08 defines MAX_CENTROID_KM_DAY = 100.0 while _config.py has 150.0.
# This is a known bug (see SKILL.md ⚠️, HANDOFF.md §Known Issues).
# The canonical value must be decided before the _config import refactor.
# When the discrepancy is resolved, this test should be updated to a normal
# (non-xfail) assertion.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN BUG: stage 08 MAX_CENTROID_KM_DAY=100.0 vs _config.py=150.0. "
        "Resolve canonical value before _config import refactor. "
        "See SKILL.md ⚠️ Known Issues and HANDOFF.md."
    ),
)
def test_max_centroid_km_day_stage08_matches_config():
    """This test is expected to fail until the MAX_CENTROID_KM_DAY discrepancy is fixed."""
    s = _load("08_build_event_catalog.py")
    assert s.MAX_CENTROID_KM_DAY == cfg.MAX_CENTROID_KM_DAY, (
        f"Stage 08 MAX_CENTROID_KM_DAY={s.MAX_CENTROID_KM_DAY} != "
        f"_config.MAX_CENTROID_KM_DAY={cfg.MAX_CENTROID_KM_DAY}. "
        "Decide the canonical value and update either the script or _config."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. MAX_HAIL_MM in Stage 13 must match _config
# ─────────────────────────────────────────────────────────────────────────────

def test_max_hail_mm_stage13_matches_config():
    s = _load("13_generate_stochastic_catalog.py")
    assert s.MAX_HAIL_MM == cfg.MAX_HAIL_MM, (
        f"Stage 13 MAX_HAIL_MM={s.MAX_HAIL_MM} != _config.MAX_HAIL_MM={cfg.MAX_HAIL_MM}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. _config.py completeness — all expected constants are defined
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "NROWS", "NCOLS", "DX", "LAT_MAX", "LON_MIN",
    "DAMAGE_THRESH_MM", "MAX_HAIL_MM",
    "RP_YEARS", "POOL_RADIUS_KM", "DECAY_KM",
    "N_REGIONS_DEFAULT", "GPD_THRESH_MM_DEFAULT",
    "RNG_SEED", "N_SIM_YEARS", "TRANSLATE_CELLS",
    "MAX_CENTROID_KM_DAY", "MAX_INTENSITY_RATIO",
])
def test_config_defines_required_constant(name):
    assert hasattr(cfg, name), f"_config.py is missing required constant: {name}"
