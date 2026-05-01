#!/usr/bin/env python3
"""
03_download_spc.py — Download SPC Hail Reports (Validation / Calibration)
==========================================================================
Downloads daily storm report CSVs from NOAA SPC for 2004 through yesterday.

In v2.0, SPC hail reports are used for VALIDATION and CALIBRATION only —
the primary hazard input is radar-derived MESH from stages 01, 02, and 04b.
SPC reports serve three purposes:

  1. Cross-validation of corrected MESH75 against ground truth (stage 06)
  2. Building the GridRad cross-calibration overlap sample (stage 05)
  3. Independent check of return period plausibility

Source: https://www.spc.noaa.gov/climo/reports/YYMMDD_rpts_TYPE.csv
Output: data/historical/spc/YYYY/YYMMDD_rpts_{torn,hail,wind}.csv

Usage:
  python scripts/03_download_spc.py
  python scripts/03_download_spc.py --validate
"""

import os
import sys
import time
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
LOGS_ROOT = REPO_ROOT / "logs"

BASE_URL = "https://www.spc.noaa.gov/climo/reports"
OUT_DIR  = DATA_ROOT / "historical" / "spc"
LOG_FILE = LOGS_ROOT / "03_download_spc.log"
TYPES = ["torn", "hail", "wind"]
WORKERS = 10
HEADER_SIZE = 60  # bytes — header-only files are ~52 bytes (no data)

def log(msg):
    print(msg, flush=True)
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

def download_one(url, outfile):
    if os.path.exists(outfile) and os.path.getsize(outfile) > HEADER_SIZE:
        return "skip"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (research/archive-download)"})
        with urlopen(req, timeout=15) as resp:
            content = resp.read()
        if len(content) > HEADER_SIZE:
            os.makedirs(os.path.dirname(outfile), exist_ok=True)
            with open(outfile, "wb") as f:
                f.write(content)
            return "ok"
        return "empty"
    except HTTPError:
        return "miss"
    except Exception as e:
        return f"err:{e}"

def validate_outputs() -> bool:
    """Validate all outputs produced by this stage."""
    import csv as _csv
    import random
    errors = []

    if not OUT_DIR.exists():
        errors.append(f"Missing directory: {OUT_DIR}")
    else:
        csv_files = list(OUT_DIR.rglob("*.csv"))
        if len(csv_files) <= 1000:
            errors.append(f"Too few CSV files: {len(csv_files)} (expected >1000)")
        else:
            log(f"  Found {len(csv_files):,} SPC report files")
            sample = random.sample(csv_files, min(5, len(csv_files)))
            for p in sample:
                try:
                    with open(p, newline="") as f:
                        rows = list(_csv.reader(f))
                    if len(rows) == 0:
                        errors.append(f"Empty CSV: {p.name}")
                except Exception as e:
                    errors.append(f"Cannot read {p.name}: {e}")

    if errors:
        log("CRITICAL: Output validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True


def main():
    log(f"\n{'='*60}")
    log(f"  SPC Storm Reports Download — Stage 03 (validation data)")
    log(f"{'='*60}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = date(2004, 3, 1)
    end = date.today() - timedelta(days=1)

    # Build task list
    tasks = []
    d = start
    while d <= end:
        yy = d.strftime("%y")
        mm = d.strftime("%m")
        dd = d.strftime("%d")
        year = d.strftime("%Y")
        for t in TYPES:
            filename = f"{yy}{mm}{dd}_rpts_{t}.csv"
            url = f"{BASE_URL}/{filename}"
            outfile = str(OUT_DIR / year / filename)
            tasks.append((url, outfile))
        d += timedelta(days=1)

    total = len(tasks)
    log(f"  Files to check: {total:,}")
    log(f"  Output: {OUT_DIR}")

    counts = {"ok": 0, "skip": 0, "miss": 0, "empty": 0, "err": 0}
    done = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(download_one, url, outfile): (url, outfile) for url, outfile in tasks}
        for future in as_completed(futures):
            result = future.result()
            done += 1
            key = result if result in counts else "err"
            counts[key] += 1
            if done % 500 == 0 or done == total:
                pct = done / total * 100
                log(f"  [{done}/{total}] {pct:.1f}% — saved:{counts['ok']} "
                    f"skipped:{counts['skip']} empty/404:{counts['miss']+counts['empty']} "
                    f"errors:{counts['err']}")

    log(f"\n{'='*60}")
    log(f"  Done! New: {counts['ok']}, Already had: {counts['skip']}")
    log(f"{'='*60}\n")

    if not validate_outputs():
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Download SPC storm reports (validation/calibration data).")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        ok = validate_outputs()
        sys.exit(0 if ok else 1)
    main()
