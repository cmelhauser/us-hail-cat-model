#!/usr/bin/env python3
"""
run_pipeline.py — CONUS Hail Cat Model v2.0: Full Pipeline Runner
==================================================================
Runs all pipeline stages in order. Stops on any failure.

Usage:
    python run_pipeline.py              # Run all stages
    python run_pipeline.py --from 5     # Resume from stage 5
    python run_pipeline.py --only 4b    # Run a single stage
    python run_pipeline.py --dry-run    # Print stages without running
    python run_pipeline.py --skip 14,15 # Skip stages
    python run_pipeline.py --validate   # Validate outputs only
"""

import argparse
import importlib
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REQUIRED_PACKAGES = [
    ("numpy",       "numpy"),
    ("pandas",      "pandas"),
    ("scipy",       "scipy"),
    ("rasterio",    "rasterio"),
    ("xarray",      "xarray"),
    ("regionmask",  "regionmask"),
    ("lmoments3",   "lmoments3"),
    ("pyarrow",     "pyarrow"),
    ("matplotlib",  "matplotlib"),
    ("cartopy",     "cartopy"),
    ("boto3",       "boto3"),
    ("netCDF4",     "netCDF4"),
    ("cfgrib",      "cfgrib"),
    ("sklearn",     "sklearn"),
]

def check_dependencies() -> bool:
    missing = []
    for pip_name, import_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)
    if missing:
        print(f"\033[91m✗ Missing: {', '.join(missing)}\033[0m")
        print(f"  pip install -r requirements.txt\n")
        return False
    return True

REPO_ROOT = Path(__file__).resolve().parent
SCRIPTS   = REPO_ROOT / "scripts"
LOGS      = REPO_ROOT / "logs"

# Stage ID, script filename, description, estimated runtime
STAGES = [
    ("01",  "01_download_myrorss.py",          "Download MYRORSS MESH (1998–2011)",                "~2–6 hrs"),
    ("02",  "02_download_mrms_mesh.py",        "Download operational MRMS MESH (2020–present)",    "~3–8 hrs"),
    ("03",  "03_download_spc.py",              "Download SPC hail reports (validation)",           "~5 min"),
    ("04a", "04a_download_era5_isotherms.py",  "Download ERA5 monthly isotherm heights",           "~30 min"),
    ("04b", "04b_fill_gridrad_gap.py",         "Compute MESH75 from GridRad (2012–2019)",          "~8–24 hrs"),
    ("05",  "05_apply_mesh_bias_correction.py","Unified bias correction + cross-calibration",      "~1 hr"),
    ("06",  "06_validate_mesh_vs_spc.py",      "Validate corrected MESH vs SPC reports",           "~15 min"),
    ("07",  "07_build_hail_climo.py",          "Build 366-day daily climatology",                  "~10 min"),
    ("08",  "08_build_event_catalog.py",       "Event identification + catalog",                   "~15 min"),
    ("09",  "09_fit_cdf_regional.py",          "CDF fitting: lognormal + GPD (regional ξ)",        "~30 min"),
    ("10",  "10_build_smooth_cdf.py",          "Spatially-pooled smooth CDF rebuild",              "~30 min"),
    ("11",  "11_build_occurrence_probs.py",    "Annual occurrence probability rasters",            "~10 min"),
    ("12",  "12_apply_conus_mask.py",          "CONUS mask + topographic correction",              "~10 min"),
    ("13",  "13_generate_stochastic_catalog.py","50,000-yr stochastic catalog",                    "~3 hrs"),
    ("14",  "14_build_vulnerability.py",       "MDR vulnerability curves [placeholder]",           "~5 min"),
    ("15",  "15_render_figures.py",            "Render all figures + validation report",            "~45 min"),
]

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"

def print_header():
    n = len(STAGES)
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  CONUS Hail Cat Model v2.0 — Pipeline Runner{RESET}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Repo:   {REPO_ROOT}")
    print(f"  Stages: {n}")
    print(f"{BOLD}{'='*60}{RESET}\n")

def run_stage(stage_id: str, script: str, desc: str, eta: str,
              dry_run: bool, validate_only: bool = False) -> bool:
    script_path = SCRIPTS / script
    log_path    = LOGS / f"{script.replace('.py', '')}.log"
    LOGS.mkdir(exist_ok=True)

    mode = "validate" if validate_only else "run"
    print(f"{BOLD}[{stage_id}]{RESET} {desc}")
    print(f"       Script: {script}  (est. {eta})")

    if dry_run:
        print(f"       {YELLOW}[DRY RUN — skipped]{RESET}\n")
        return True

    if not script_path.exists():
        print(f"       {RED}✗ Script not found: {script_path}{RESET}\n")
        return False

    t0 = time.time()
    print(f"       {CYAN}▶ {'Validating' if validate_only else 'Running'}...{RESET}", flush=True)

    cmd = [sys.executable, str(script_path)]
    if validate_only:
        cmd.append("--validate")

    try:
        with open(log_path, "w") as log_fh:
            log_fh.write(f"[{datetime.now().isoformat()}] Starting {script} ({mode})\n\n")
            proc = subprocess.Popen(
                cmd, cwd=str(SCRIPTS),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout:
                log_fh.write(line)
                log_fh.flush()
                stripped = line.strip()
                if stripped and any(m in stripped for m in [
                    "[", "Done", "Error", "WARNING", "✓", "✗",
                    "written", "complete", "finished", "failed", "ETA=",
                ]):
                    print(f"       {stripped}")
            proc.wait()
            elapsed = time.time() - t0
            log_fh.write(f"\n[{datetime.now().isoformat()}] Exit code: {proc.returncode} ({fmt_duration(elapsed)})\n")
    except KeyboardInterrupt:
        proc.terminate()
        print(f"\n       {YELLOW}⚠ Interrupted{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"       {RED}✗ Exception: {e}{RESET}\n")
        return False

    elapsed = time.time() - t0
    if proc.returncode == 0:
        print(f"       {GREEN}✓ Done in {fmt_duration(elapsed)}{RESET}\n")
        return True
    else:
        print(f"       {RED}✗ Failed (exit {proc.returncode}) — see {log_path.name}{RESET}\n")
        return False

def main():
    parser = argparse.ArgumentParser(description="Run the CONUS hail cat model v2.0 pipeline.")
    parser.add_argument("--from",   dest="from_stage", type=str, default=None,
                        help="Start from this stage ID (e.g., 05 or 04b)")
    parser.add_argument("--only",   dest="only_stage", type=str, default=None,
                        help="Run only this stage ID")
    parser.add_argument("--skip",   dest="skip_stages", type=str, default="",
                        help="Comma-separated stage IDs to skip")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    parser.add_argument("--validate", dest="validate_only", action="store_true")
    args = parser.parse_args()

    if not args.dry_run:
        if not check_dependencies():
            sys.exit(1)

    skip = set()
    if args.skip_stages:
        skip = {s.strip() for s in args.skip_stages.split(",")}

    print_header()

    if args.validate_only:
        print(f"  {YELLOW}Mode: VALIDATE ONLY{RESET}\n")

    # Determine stages to run
    all_ids = [s[0] for s in STAGES]

    if args.only_stage:
        stages_to_run = [s for s in STAGES if s[0] == args.only_stage]
        if not stages_to_run:
            print(f"{RED}No stage with ID '{args.only_stage}'{RESET}")
            print(f"Available: {', '.join(all_ids)}")
            sys.exit(1)
    elif args.from_stage:
        try:
            start_idx = all_ids.index(args.from_stage)
        except ValueError:
            print(f"{RED}No stage with ID '{args.from_stage}'{RESET}")
            sys.exit(1)
        stages_to_run = [s for s in STAGES[start_idx:] if s[0] not in skip]
    else:
        stages_to_run = [s for s in STAGES if s[0] not in skip]

    print(f"  Stages to run: {len(stages_to_run)}")
    if skip:
        print(f"  Skipping: {sorted(skip)}")
    print()

    t_start = time.time()
    results = []

    for stage_id, script, desc, eta in stages_to_run:
        ok = run_stage(stage_id, script, desc, eta, args.dry_run, args.validate_only)
        results.append((stage_id, desc, ok))
        if not ok and not args.dry_run:
            print(f"{RED}{BOLD}Pipeline stopped at stage {stage_id}.{RESET}")
            print(f"Fix and resume: python run_pipeline.py --from {stage_id}\n")
            break

    total_elapsed = time.time() - t_start
    passed = sum(1 for _, _, ok in results if ok)
    failed = sum(1 for _, _, ok in results if not ok)

    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Summary{RESET}  ({fmt_duration(total_elapsed)} total)")
    print(f"{BOLD}{'='*60}{RESET}")
    for sid, desc, ok in results:
        icon = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {icon}  [{sid}] {desc}")
    print()

    if failed == 0 and not args.dry_run:
        print(f"{GREEN}{BOLD}  ✓ All {passed} stages completed successfully!{RESET}\n")
    elif args.dry_run:
        print(f"{YELLOW}  Dry run complete — nothing executed.{RESET}\n")
    else:
        print(f"{RED}{BOLD}  {failed} stage(s) failed. {passed} succeeded.{RESET}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
