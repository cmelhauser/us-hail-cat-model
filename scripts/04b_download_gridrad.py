#!/usr/bin/env python3
"""
04b_download_gridrad.py — Download GridRad / GridRad-Severe NetCDF Inputs (2012–2019)
=====================================================================================
Downloads the GridRad NetCDF inputs required by Stage 04c (gap-fill SHI → MESH75).

This stage exists because GridRad is hosted behind NCAR RDA / GDEX, unlike the
public NOAA S3 radar sources used by Stages 01–02. Stage 04c is *compute-only* and
expects files to already exist on disk; Stage 04b populates the required local
directory structure under `data/historical/`.

Data Sources
-----------
  GridRad (hourly):       NCAR RDA d841000
  GridRad-Severe (5-min): NCAR RDA d841006

Local Layout (expected by Stage 04c)
------------------------------------
  data/historical/gridrad/YYYY/YYYYMMDD/*.nc
  data/historical/gridrad_severe/YYYY/YYYYMMDD/*.nc

Authentication
--------------
NCAR RDA/GDEX requires authentication to download protected files.

This script supports two common setups:
  1) **GDEX API token** (recommended): set env var `GDEX_TOKEN`.
     Token is available from your profile page: https://gdex.ucar.edu/accounts/profile
  2) **RDA HTTPS + ~/.netrc**: create `~/.netrc` entry for `rda.ucar.edu` and set
     permissions `chmod 600 ~/.netrc`.

The exact dataset file paths are discovered via the public THREDDS catalog and the
files are downloaded from the corresponding fileServer endpoints.

Concurrency / throughput
------------------------
Uses a bounded thread pool (`--workers`, default 4). Respect NCAR guidance:
keep concurrent download streams <= 10.

Usage
-----
  python scripts/04b_download_gridrad.py --check-data
  python scripts/04b_download_gridrad.py --year 2015 --month 5 --workers 4
  python scripts/04b_download_gridrad.py --hourly-only
  python scripts/04b_download_gridrad.py --severe-only
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import DATA_ROOT, LOG_ROOT
    from _logging import get_logger
except ImportError:  # pragma: no cover
    from scripts._config import DATA_ROOT, LOG_ROOT
    from scripts._logging import get_logger

GRIDRAD_DIR = DATA_ROOT / "historical" / "gridrad"
GRIDRAD_SEV_DIR = DATA_ROOT / "historical" / "gridrad_severe"

# Public THREDDS catalogs (listing is public; downloads may require auth).
# GridRad hourly is under files/g/d841000/YYYYMM/.
THREDDS_BASE_HOURLY = "https://thredds.rda.ucar.edu/thredds/catalog/files/g/"
FILESERVER_BASE_HOURLY = "https://thredds.rda.ucar.edu/thredds/fileServer/files/g/"
#
# GridRad-Severe lives under files/d841006/volumes/YYYY/YYYYMMDD/.
THREDDS_BASE_SEVERE = "https://thredds.rda.ucar.edu/thredds/catalog/files/d841006/volumes/"
FILESERVER_BASE_SEVERE = "https://thredds.rda.ucar.edu/thredds/fileServer/files/d841006/volumes/"

DS_HOURLY = "d841000"
DS_SEVERE = "d841006"

GAP_START = date(2012, 1, 1)
GAP_END = date(2020, 10, 13)

log = get_logger("04b_download_gridrad", LOG_ROOT).info


def iter_dates(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Download GridRad inputs for Stage 04c.")
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--month", type=int, default=None)
    p.add_argument("--workers", type=int, default=4, metavar="N")
    p.add_argument("--hourly-only", action="store_true", help="Download only d841000 hourly")
    p.add_argument("--severe-only", action="store_true", help="Download only d841006 severe (5-min)")
    p.add_argument("--check-data", action="store_true", help="Only check what is present/missing")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be downloaded, but do not download",
    )
    return p


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _day_out_dir(base: Path, day: date) -> Path:
    return base / f"{day.year}" / _ymd(day)


def _catalog_url(dsid: str, day: date) -> str:
    if dsid == DS_HOURLY:
        # GridRad hourly: month catalogs under files/g/d841000/YYYYMM/catalog.xml
        return f"{THREDDS_BASE_HOURLY}{dsid}/{day.year}{day.month:02d}/catalog.xml"
    if dsid == DS_SEVERE:
        # GridRad-Severe: day catalogs under files/d841006/volumes/YYYY/YYYYMMDD/catalog.xml
        return f"{THREDDS_BASE_SEVERE}{day.year}/{_ymd(day)}/catalog.xml"
    raise ValueError(f"Unknown dsid: {dsid}")


def _fileserver_url(dsid: str, day: date, filename: str) -> str:
    if dsid == DS_HOURLY:
        # Hourly files are stored under .../d841000/YYYYMM/
        return f"{FILESERVER_BASE_HOURLY}{dsid}/{day.year}{day.month:02d}/{filename}"
    if dsid == DS_SEVERE:
        return f"{FILESERVER_BASE_SEVERE}{day.year}/{_ymd(day)}/{filename}"
    raise ValueError(f"Unknown dsid: {dsid}")


def _request_session() -> requests.Session:
    s = requests.Session()
    # Allow user to use ~/.netrc automatically if present.
    s.trust_env = True
    return s


def _auth_params() -> dict:
    token = os.environ.get("GDEX_TOKEN") or os.environ.get("GDEX_API_TOKEN")
    if token:
        return {"token": token}
    return {}


def list_day_catalog_files(session: requests.Session, dsid: str, day: date) -> list[str]:
    """
    Return list of `.nc` filenames present in the THREDDS catalog for this day.

    Implementation note: for GridRad hourly (d841000), catalogs are month-level.
    We load the month catalog and then filter filenames by YYYYMMDD substring.
    """
    ns = {"t": "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"}

    if dsid == DS_HOURLY:
        url = _catalog_url(dsid, day)
        r = session.get(url, timeout=60)
        if r.status_code == 404:
            return []
        r.raise_for_status()

        root = ET.fromstring(r.text)
        ymd = _ymd(day)
        out: list[str] = []
        for el in root.findall(".//t:dataset", ns):
            name = el.attrib.get("name", "")
            if name.endswith(".nc") and ymd in name:
                out.append(name)
        return sorted(set(out))

    if dsid == DS_SEVERE:
        # Not every day exists; check whether the year catalog links to it.
        year_url = f"{THREDDS_BASE_SEVERE}{day.year}/catalog.xml"
        r = session.get(year_url, timeout=60)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        year_root = ET.fromstring(r.text)
        ymd = _ymd(day)
        # Find a catalogRef titled YYYYMMDD
        href = None
        for ref in year_root.findall(".//t:catalogRef", ns):
            title = ref.attrib.get("{http://www.w3.org/1999/xlink}title", "")
            if title == ymd:
                href = ref.attrib.get("{http://www.w3.org/1999/xlink}href", "")
                break
        if not href:
            return []
        day_url = f"{THREDDS_BASE_SEVERE}{day.year}/{href}"
        rr = session.get(day_url, timeout=60)
        if rr.status_code == 404:
            return []
        rr.raise_for_status()
        root = ET.fromstring(rr.text)
        out = []
        for el in root.findall(".//t:dataset", ns):
            name = el.attrib.get("name", "")
            if name.endswith(".nc"):
                out.append(name)
        return sorted(set(out))

    raise ValueError(f"Unknown dsid: {dsid}")


@dataclass(frozen=True)
class DownloadItem:
    dsid: str
    day: date
    filename: str
    url: str
    out_path: Path


def plan_downloads_for_day(
    session: requests.Session,
    day: date,
    hourly: bool,
    severe: bool,
) -> list[DownloadItem]:
    items: list[DownloadItem] = []

    if severe:
        for fn in list_day_catalog_files(session, DS_SEVERE, day):
            out_dir = _day_out_dir(GRIDRAD_SEV_DIR, day)
            out_path = out_dir / fn
            url = _fileserver_url(DS_SEVERE, day, fn)
            items.append(DownloadItem(DS_SEVERE, day, fn, url, out_path))

    if hourly:
        for fn in list_day_catalog_files(session, DS_HOURLY, day):
            out_dir = _day_out_dir(GRIDRAD_DIR, day)
            out_path = out_dir / fn
            url = _fileserver_url(DS_HOURLY, day, fn)
            items.append(DownloadItem(DS_HOURLY, day, fn, url, out_path))

    return items


def _download_one(session: requests.Session, item: DownloadItem) -> tuple[DownloadItem, str]:
    """
    Download one file if needed. Returns (item, status_string).
    """
    if item.out_path.exists() and item.out_path.stat().st_size > 0:
        return item, "skipped"

    item.out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = item.out_path.with_suffix(item.out_path.suffix + ".tmp")

    params = _auth_params()
    with session.get(item.url, params=params, stream=True, timeout=180) as r:
        if r.status_code == 404:
            return item, "missing"
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(item.out_path)
    return item, "downloaded"


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.hourly_only and args.severe_only:
        raise SystemExit("Choose at most one of --hourly-only / --severe-only.")

    hourly = not args.severe_only
    severe = not args.hourly_only

    # Date range selection
    if args.year and args.month:
        import calendar

        d_start = date(args.year, args.month, 1)
        d_end = date(args.year, args.month, calendar.monthrange(args.year, args.month)[1])
    elif args.year:
        d_start = date(args.year, 1, 1)
        d_end = date(args.year, 12, 31)
    else:
        d_start = GAP_START
        d_end = GAP_END

    d_start = max(d_start, GAP_START)
    d_end = min(d_end, GAP_END)

    w = max(1, int(args.workers))
    if w > 10:
        log("  WARNING: NCAR guidance limits concurrent download streams to 10.")

    log(f"\n{'='*60}")
    log("  GridRad Download (RDA/GDEX) — Stage 04b")
    log(f"{'='*60}")
    log(f"  Period:   {d_start} → {d_end}")
    log(f"  Workers:  {w}")
    log(f"  Hourly:   {hourly} ({DS_HOURLY})  → {GRIDRAD_DIR}")
    log(f"  Severe:   {severe} ({DS_SEVERE})  → {GRIDRAD_SEV_DIR}")
    if os.environ.get("GDEX_TOKEN") or os.environ.get("GDEX_API_TOKEN"):
        log("  Auth:     GDEX token (env var)")
    else:
        log("  Auth:     requests default (supports ~/.netrc if configured)")

    session = _request_session()

    # Plan downloads by querying per-day catalogs.
    planned: list[DownloadItem] = []
    missing_days = 0
    for day in iter_dates(d_start, d_end):
        items = plan_downloads_for_day(session, day, hourly=hourly, severe=severe)
        if not items:
            missing_days += 1
        planned.extend(items)

    log(f"\n  Planned files: {len(planned):,}  |  Days with empty catalogs: {missing_days:,}\n")

    if args.check_data or args.dry_run:
        # Minimal presence summary.
        have = 0
        for it in planned:
            if it.out_path.exists() and it.out_path.stat().st_size > 0:
                have += 1
        log(f"  Present locally: {have:,}/{len(planned):,}")
        sys.exit(0)

    downloaded = skipped = missing = errors = 0
    with ThreadPoolExecutor(max_workers=w) as ex:
        for item, status in ex.map(lambda it: _download_one(session, it), planned):
            if status == "downloaded":
                downloaded += 1
            elif status == "skipped":
                skipped += 1
            elif status == "missing":
                missing += 1
            else:
                errors += 1

    log(f"\n{'='*60}")
    log(f"  Downloaded: {downloaded:,}")
    log(f"  Skipped:    {skipped:,}")
    log(f"  Missing:    {missing:,}")
    log(f"  Errors:     {errors:,}")
    log(f"{'='*60}\n")


if __name__ == "__main__":
    main()

