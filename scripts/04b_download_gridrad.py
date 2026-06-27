#!/usr/bin/env python3
"""
04b_download_gridrad.py — Download GridRad / GridRad-Severe NetCDF Inputs (2012–2020-10-13)
=====================================================================================
Downloads the GridRad NetCDF inputs required by Stage 04c (gap-fill SHI → MESH75).

This stage exists because GridRad is hosted behind NCAR RDA / GDEX, unlike the
public NOAA S3 radar sources used by Stages 01–02. Stage 04c reads those inputs
from `data/historical/` (or you can chain **04b → 04c** in one pass with
``04c_fill_gridrad_gap.py --with-04b-download``). When chained from **04c**,
downloads use **`download_for_day_adaptive`** (severe-first: GridRad-Severe when
the catalog lists it; hourly only when severe is absent or does not cover the
full convective window).

**Convective day (v2.2):** each download batch targets one **12 UTC → 12 UTC**
window (label = date at window start). Timesteps are filtered from two UTC
calendar catalogs and staged under ``by_convective_day/YYYYMMDD/``.

**Default behavior (disk / memory friendly):** catalogs and downloads are driven
**one convective day at a time**. Use ``--plan-all-days-first`` only if you
need the legacy “plan everything, then download” schedule (higher peak RAM / disk
for the plan list).

Data Sources
-----------
  GridRad hourly (V3.1):  NCAR RDA d841000  (1995–2017, all months)
  GridRad hourly (V4.2):  NCAR RDA d841001  (Apr–Aug warm season, 2008–2021;
                          used as hourly fallback after 2017 when Severe is absent)
  GridRad-Severe (5-min): NCAR RDA d841006

  Files are discovered via THREDDS catalogs and fetched from the matching
  THREDDS ``fileServer`` endpoints on ``thredds.rda.ucar.edu``. NCAR also lists
  **GDEX** (interactive/API) and **Globus** for bulk transfers on the dataset
  pages; those use different workflows — this script only automates THREDDS.

  If THREDDS is flaky (503 / read timeouts), this stage retries with backoff and
  exposes longer timeouts on the CLI. You may override the THREDDS host with
  ``RDA_THREDDS_ORIGIN`` (rare; default ``https://thredds.rda.ucar.edu``) if
  NCAR documents an alternate mirror with the same path layout.

Local Layout (expected by Stage 04c)
------------------------------------
  data/historical/gridrad/by_convective_day/YYYYMMDD/*.nc
  data/historical/gridrad_severe/by_convective_day/YYYYMMDD/*.nc

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
Within each day, file downloads use a bounded thread pool (``--workers``,
default **1** for minimum memory / open handles). Respect NCAR guidance: keep
concurrent download streams ≤ 10.

Usage
-----
  python scripts/04b_download_gridrad.py --check-data
  python scripts/04b_download_gridrad.py --year 2015 --month 5 --workers 4
  python scripts/04b_download_gridrad.py --plan-all-days-first --workers 4
  python scripts/04b_download_gridrad.py --hourly-only
  python scripts/04b_download_gridrad.py --severe-only
  python scripts/04b_download_gridrad.py --connect-timeout 45 --read-timeout 900
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from collections.abc import Iterable
from xml.etree import ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ChunkedEncodingError
from urllib3.util.retry import Retry

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import DATA_ROOT, LOG_ROOT
    from _io import (
        calendar_days_for_convective_day,
        convective_window_coverage_ok,
        observation_times_from_paths,
        observation_utc_to_convective_day,
        parse_observation_utc_from_name,
        staged_nc_files_for_convective_day,
    )
    from _logging import get_logger
except ImportError:  # pragma: no cover
    from scripts._config import DATA_ROOT, LOG_ROOT
    from scripts._io import (
        calendar_days_for_convective_day,
        convective_window_coverage_ok,
        observation_times_from_paths,
        observation_utc_to_convective_day,
        parse_observation_utc_from_name,
        staged_nc_files_for_convective_day,
    )
    from scripts._logging import get_logger

GRIDRAD_DIR = DATA_ROOT / "historical" / "gridrad"
GRIDRAD_SEV_DIR = DATA_ROOT / "historical" / "gridrad_severe"


def _rda_thredds_origin() -> str:
    """THREDDS origin (scheme + host, no path). Override with RDA_THREDDS_ORIGIN."""
    return os.environ.get("RDA_THREDDS_ORIGIN", "https://thredds.rda.ucar.edu").rstrip("/")


def _thredds_base_hourly() -> str:
    return f"{_rda_thredds_origin()}/thredds/catalog/files/g/"


def _fileserver_base_hourly() -> str:
    return f"{_rda_thredds_origin()}/thredds/fileServer/files/g/"


def _thredds_base_severe() -> str:
    return f"{_rda_thredds_origin()}/thredds/catalog/files/d841006/volumes/"


def _fileserver_base_severe() -> str:
    return f"{_rda_thredds_origin()}/thredds/fileServer/files/d841006/volumes/"


# Back-compat for tests / introspection (evaluated at import; matches default origin).
THREDDS_BASE_HOURLY = _thredds_base_hourly()
FILESERVER_BASE_HOURLY = _fileserver_base_hourly()
THREDDS_BASE_SEVERE = _thredds_base_severe()
FILESERVER_BASE_SEVERE = _fileserver_base_severe()

DS_HOURLY = "d841000"  # GridRad V3.1 hourly
DS_HOURLY_V42 = "d841001"  # GridRad V4.2 warm-season hourly (Apr–Aug)
DS_SEVERE = "d841006"
_HOURLY_DSIDS = frozenset({DS_HOURLY, DS_HOURLY_V42})

V31_HOURLY_END = date(2017, 12, 31)
V42_HOURLY_START = date(2008, 4, 1)
V42_HOURLY_END = date(2021, 8, 31)
V42_HOURLY_MONTHS = frozenset({4, 5, 6, 7, 8})

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
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Parallel download threads per day (default: 1; max 10 per NCAR)",
    )
    p.add_argument(
        "--plan-all-days-first",
        action="store_true",
        help="Legacy: build one global download plan for all days, then download "
        "(higher peak memory). Default is one-day-at-a-time planning + download.",
    )
    p.add_argument("--hourly-only", action="store_true", help="Download only hourly (d841000 + d841001 fallback)")
    p.add_argument("--severe-only", action="store_true", help="Download only d841006 severe (5-min)")
    p.add_argument("--check-data", action="store_true", help="Only check what is present/missing")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be downloaded, but do not download",
    )
    p.add_argument(
        "--connect-timeout",
        type=float,
        default=30.0,
        metavar="SEC",
        help="HTTP connect timeout in seconds (default: 30)",
    )
    p.add_argument(
        "--read-timeout",
        type=float,
        default=180.0,
        metavar="SEC",
        help="HTTP read timeout for THREDDS catalog GETs (default: 180)",
    )
    p.add_argument(
        "--download-read-timeout",
        type=float,
        default=900.0,
        metavar="SEC",
        help="HTTP read timeout for NetCDF downloads (default: 900)",
    )
    return p


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _v42_hourly_eligible(convective_day: date) -> bool:
    """
    True when d841001 (V4.2 warm-season hourly) may contain this convective day.

    Used only after the V3.1 archive ends (2018+). V4.2 is Apr–Aug only.
    """
    if convective_day < V42_HOURLY_START:
        return False
    if convective_day > min(GAP_END, V42_HOURLY_END):
        return False
    if convective_day <= V31_HOURLY_END:
        return False
    return convective_day.month in V42_HOURLY_MONTHS


def _hourly_dataset_ids(convective_day: date) -> list[str]:
    """Ordered hourly THREDDS dataset IDs to query for one convective day."""
    ids = [DS_HOURLY]
    if _v42_hourly_eligible(convective_day):
        ids.append(DS_HOURLY_V42)
    return ids


def _convective_stage_dir(base: Path, convective_day: date) -> Path:
    return base / "by_convective_day" / _ymd(convective_day)


def _catalog_url(dsid: str, day: date) -> str:
    if dsid in _HOURLY_DSIDS:
        # GridRad hourly (V3.1 or V4.2): month catalogs under files/g/{dsid}/YYYYMM/
        return f"{_thredds_base_hourly()}{dsid}/{day.year}{day.month:02d}/catalog.xml"
    if dsid == DS_SEVERE:
        # GridRad-Severe: day catalogs under files/d841006/volumes/YYYY/YYYYMMDD/catalog.xml
        return f"{_thredds_base_severe()}{day.year}/{_ymd(day)}/catalog.xml"
    raise ValueError(f"Unknown dsid: {dsid}")


def _fileserver_url(dsid: str, day: date, filename: str) -> str:
    if dsid in _HOURLY_DSIDS:
        return f"{_fileserver_base_hourly()}{dsid}/{day.year}{day.month:02d}/{filename}"
    if dsid == DS_SEVERE:
        return f"{_fileserver_base_severe()}{day.year}/{_ymd(day)}/{filename}"
    raise ValueError(f"Unknown dsid: {dsid}")


def _request_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = True
    # Retry slow connections and HTTP 429/5xx before any response body is consumed.
    # read=0 avoids re-issuing partial streaming downloads at the urllib3 layer.
    retry = Retry(
        total=12,
        connect=12,
        read=0,
        backoff_factor=1.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=32)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def _retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout, ChunkedEncodingError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


def _sleep_backoff(attempt: int) -> None:
    time.sleep(min(120.0, 2.0 * (2**attempt)))


def _catalog_get(session: requests.Session, url: str, *, timeout: tuple[float, float]) -> requests.Response:
    """GET catalog XML with exponential backoff on transient errors."""
    for attempt in range(10):
        try:
            r = session.get(url, timeout=timeout, stream=False)
            if r.status_code == 404:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                r.raise_for_status()
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            if not _retryable_http_error(e) or attempt >= 9:
                raise
        except (requests.ConnectionError, requests.Timeout, ChunkedEncodingError):
            if attempt >= 9:
                raise
        _sleep_backoff(attempt)
    raise RuntimeError("_catalog_get exhausted retries")


def _auth_params() -> dict:
    token = os.environ.get("GDEX_TOKEN") or os.environ.get("GDEX_API_TOKEN")
    if token:
        return {"token": token}
    return {}


def list_day_catalog_files(
    session: requests.Session,
    dsid: str,
    day: date,
    *,
    timeout: tuple[float, float],
) -> list[str]:
    """
    Return list of `.nc` filenames present in the THREDDS catalog for this day.

    Implementation note: for GridRad hourly (d841000), catalogs are month-level.
    We load the month catalog and then filter filenames by YYYYMMDD substring.
    """
    ns = {"t": "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"}

    if dsid in _HOURLY_DSIDS:
        url = _catalog_url(dsid, day)
        r = _catalog_get(session, url, timeout=timeout)
        if r.status_code == 404:
            return []

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
        year_url = f"{_thredds_base_severe()}{day.year}/catalog.xml"
        r = _catalog_get(session, year_url, timeout=timeout)
        if r.status_code == 404:
            return []

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
        day_url = f"{_thredds_base_severe()}{day.year}/{href}"
        rr = _catalog_get(session, day_url, timeout=timeout)
        if rr.status_code == 404:
            return []

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
    convective_day: date
    catalog_day: date
    filename: str
    url: str
    out_path: Path


def plan_downloads_for_day(
    session: requests.Session,
    convective_day: date,
    hourly: bool,
    severe: bool,
    *,
    catalog_timeout: tuple[float, float],
) -> list[DownloadItem]:
    """Plan downloads for one convective day (12 UTC → 12 UTC)."""
    items: list[DownloadItem] = []
    cal_a, cal_b = calendar_days_for_convective_day(convective_day)

    for catalog_day in (cal_a, cal_b):
        if severe:
            for fn in list_day_catalog_files(
                session, DS_SEVERE, catalog_day, timeout=catalog_timeout
            ):
                obs = parse_observation_utc_from_name(fn)
                if obs is None or observation_utc_to_convective_day(obs) != convective_day:
                    continue
                out_path = _convective_stage_dir(GRIDRAD_SEV_DIR, convective_day) / fn
                url = _fileserver_url(DS_SEVERE, catalog_day, fn)
                items.append(
                    DownloadItem(DS_SEVERE, convective_day, catalog_day, fn, url, out_path)
                )

        if hourly:
            for dsid in _hourly_dataset_ids(convective_day):
                for fn in list_day_catalog_files(
                    session, dsid, catalog_day, timeout=catalog_timeout
                ):
                    obs = parse_observation_utc_from_name(fn)
                    if obs is None or observation_utc_to_convective_day(obs) != convective_day:
                        continue
                    out_path = _convective_stage_dir(GRIDRAD_DIR, convective_day) / fn
                    url = _fileserver_url(dsid, catalog_day, fn)
                    items.append(
                        DownloadItem(dsid, convective_day, catalog_day, fn, url, out_path)
                    )

    # One row per destination path (two catalog days can list the same filename).
    by_path = {it.out_path: it for it in items}
    return list(by_path.values())


def _download_one(
    session: requests.Session,
    item: DownloadItem,
    *,
    connect_timeout: float,
    read_timeout: float,
) -> tuple[DownloadItem, str]:
    """
    Download one file if needed. Returns (item, status_string).
    Retries transient THREDDS errors and read timeouts (clears partial .tmp).
    """
    if item.out_path.exists() and item.out_path.stat().st_size > 0:
        return item, "skipped"

    item.out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = item.out_path.with_suffix(item.out_path.suffix + ".tmp")
    timeout = (connect_timeout, read_timeout)
    params = _auth_params()

    for attempt in range(8):
        try:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            with session.get(item.url, params=params, stream=True, timeout=timeout) as r:
                if r.status_code == 404:
                    if tmp.exists():
                        tmp.unlink(missing_ok=True)
                    return item, "missing"
                if r.status_code in (429, 500, 502, 503, 504):
                    r.raise_for_status()
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            break
        except requests.HTTPError as e:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            if not _retryable_http_error(e) or attempt >= 7:
                raise
            _sleep_backoff(attempt)
        except (requests.ConnectionError, requests.Timeout, ChunkedEncodingError):
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            if attempt >= 7:
                raise
            _sleep_backoff(attempt)
    tmp.replace(item.out_path)
    return item, "downloaded"


def download_planned_items(
    session: requests.Session,
    planned: list[DownloadItem],
    *,
    connect_timeout: float,
    read_timeout: float,
    max_workers: int,
) -> dict[str, int]:
    """Download a list of items (typically one day). Returns count dict."""
    downloaded = skipped = missing = errors = 0
    w = max(1, int(max_workers))
    if not planned:
        return {
            "downloaded": 0,
            "skipped": 0,
            "missing": 0,
            "errors": 0,
        }
    with ThreadPoolExecutor(max_workers=w) as ex:
        for item, status in ex.map(
            lambda it: _download_one(
                session,
                it,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            ),
            planned,
        ):
            if status == "downloaded":
                downloaded += 1
            elif status == "skipped":
                skipped += 1
            elif status == "missing":
                missing += 1
            else:
                errors += 1
    return {
        "downloaded": downloaded,
        "skipped": skipped,
        "missing": missing,
        "errors": errors,
    }


def download_for_day(
    session: requests.Session,
    convective_day: date,
    *,
    hourly: bool,
    severe: bool,
    catalog_timeout: tuple[float, float],
    connect_timeout: float,
    read_timeout: float,
    max_workers: int,
) -> dict[str, int]:
    """
    Plan and download GridRad inputs for one convective day (12 UTC → 12 UTC).

    Files are staged under ``by_convective_day/YYYYMMDD/`` for Stage 04c.
    """
    planned = plan_downloads_for_day(
        session,
        convective_day,
        hourly=hourly,
        severe=severe,
        catalog_timeout=catalog_timeout,
    )
    return download_planned_items(
        session,
        planned,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        max_workers=max_workers,
    )


def _merge_download_stats(
    base: dict[str, int],
    extra: dict[str, int],
) -> dict[str, int]:
    out = dict(base)
    for key in ("downloaded", "skipped", "missing", "errors"):
        out[key] = int(out.get(key, 0)) + int(extra.get(key, 0))
    return out


def severe_catalog_has_convective_data(
    session: requests.Session,
    convective_day: date,
    *,
    catalog_timeout: tuple[float, float],
) -> bool:
    """True if THREDDS lists any GridRad-Severe file in this convective window."""
    return bool(
        plan_downloads_for_day(
            session,
            convective_day,
            hourly=False,
            severe=True,
            catalog_timeout=catalog_timeout,
        )
    )


def _severe_staging_covers_day(convective_day: date) -> bool:
    """True if staged severe NetCDFs span the convective window without large gaps."""
    sev_paths = staged_nc_files_for_convective_day(GRIDRAD_SEV_DIR, convective_day)
    sev_times = observation_times_from_paths(sev_paths, convective_day)
    return convective_window_coverage_ok(
        sev_times,
        convective_day,
        max_gap_minutes=15.0,
    )


def download_for_day_adaptive(
    session: requests.Session,
    convective_day: date,
    *,
    catalog_timeout: tuple[float, float],
    connect_timeout: float,
    read_timeout: float,
    max_workers: int,
) -> dict[str, int | str]:
    """
    Download GridRad inputs with severe-first policy for Stage 04c.

    1. If staged GridRad-Severe already covers the convective window, skip downloads.
    2. If the severe catalog lists timesteps for this window, download severe only.
    3. After severe download, re-check window coverage; if gaps remain, add hourly
       (V3.1 d841000, then V4.2 d841001 for Apr–Aug 2018+ when V3.1 is empty).
    4. If no severe catalog data exists, download hourly only (same V3.1 → V4.2 order).
    """
    empty = {
        "downloaded": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 0,
        "source_mode": "none",
    }

    if _severe_staging_covers_day(convective_day):
        n_local = len(staged_nc_files_for_convective_day(GRIDRAD_SEV_DIR, convective_day))
        out = dict(empty)
        out["skipped"] = n_local
        out["source_mode"] = "severe-only-local"
        return out

    has_severe = severe_catalog_has_convective_data(
        session,
        convective_day,
        catalog_timeout=catalog_timeout,
    )

    if has_severe:
        stats = download_for_day(
            session,
            convective_day,
            hourly=False,
            severe=True,
            catalog_timeout=catalog_timeout,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            max_workers=max_workers,
        )
        stats = dict(stats)
        stats["source_mode"] = "severe-only"

        if _severe_staging_covers_day(convective_day):
            return stats

        hourly_stats = download_for_day(
            session,
            convective_day,
            hourly=True,
            severe=False,
            catalog_timeout=catalog_timeout,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            max_workers=max_workers,
        )
        merged = _merge_download_stats(stats, hourly_stats)
        merged["source_mode"] = "severe+hourly-fill"
        return merged

    stats = download_for_day(
        session,
        convective_day,
        hourly=True,
        severe=False,
        catalog_timeout=catalog_timeout,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        max_workers=max_workers,
    )
    stats = dict(stats)
    stats["source_mode"] = "hourly-only"
    return stats


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
    log(f"  Workers:  {w} (per-day download threads)")
    log(f"  Schedule: {'legacy global plan' if args.plan_all_days_first else 'one day at a time'}")
    log(f"  Hourly:   {DS_HOURLY} (V3.1) + {DS_HOURLY_V42} (V4.2 Apr–Aug after 2017)  → {GRIDRAD_DIR}")
    log(f"  Severe:   {severe} ({DS_SEVERE})  → {GRIDRAD_SEV_DIR}")
    if os.environ.get("GDEX_TOKEN") or os.environ.get("GDEX_API_TOKEN"):
        log("  Auth:     GDEX token (env var)")
    else:
        log("  Auth:     requests default (supports ~/.netrc if configured)")
    co = float(args.connect_timeout)
    cr = float(args.read_timeout)
    dr = float(args.download_read_timeout)
    catalog_timeout = (co, cr)
    log(f"  THREDDS:  {_rda_thredds_origin()}")
    log(f"  Timeouts: connect={co:g}s  catalog_read={cr:g}s  download_read={dr:g}s")

    session = _request_session()

    if args.plan_all_days_first:
        planned: list[DownloadItem] = []
        missing_days = 0
        for day in iter_dates(d_start, d_end):
            items = plan_downloads_for_day(
                session,
                day,
                hourly=hourly,
                severe=severe,
                catalog_timeout=catalog_timeout,
            )
            if not items:
                missing_days += 1
            planned.extend(items)

        log(f"\n  Planned files: {len(planned):,}  |  Days with empty catalogs: {missing_days:,}\n")

        if args.check_data or args.dry_run:
            have = 0
            for it in planned:
                if it.out_path.exists() and it.out_path.stat().st_size > 0:
                    have += 1
            log(f"  Present locally: {have:,}/{len(planned):,}")
            sys.exit(0)

        stats = download_planned_items(
            session,
            planned,
            connect_timeout=co,
            read_timeout=dr,
            max_workers=w,
        )
    else:
        if args.check_data or args.dry_run:
            planned_count = 0
            missing_days = 0
            have = 0
            for day in iter_dates(d_start, d_end):
                items = plan_downloads_for_day(
                    session,
                    day,
                    hourly=hourly,
                    severe=severe,
                    catalog_timeout=catalog_timeout,
                )
                planned_count += len(items)
                if not items:
                    missing_days += 1
                for it in items:
                    if it.out_path.exists() and it.out_path.stat().st_size > 0:
                        have += 1
            log(
                f"\n  One-day-at-a-time mode (dry check): {planned_count:,} file rows catalogued "
                f"across {(d_end - d_start).days + 1:,} days  |  empty catalog days: {missing_days:,}\n"
            )
            log(f"  Present locally: {have:,}/{planned_count:,}")
            sys.exit(0)

        downloaded = skipped = missing = errors = 0
        for day in iter_dates(d_start, d_end):
            st = download_for_day(
                session,
                day,
                hourly=hourly,
                severe=severe,
                catalog_timeout=catalog_timeout,
                connect_timeout=co,
                read_timeout=dr,
                max_workers=w,
            )
            downloaded += st["downloaded"]
            skipped += st["skipped"]
            missing += st["missing"]
            errors += st["errors"]
        stats = {
            "downloaded": downloaded,
            "skipped": skipped,
            "missing": missing,
            "errors": errors,
        }

    log(f"\n{'='*60}")
    log(f"  Downloaded: {stats['downloaded']:,}")
    log(f"  Skipped:    {stats['skipped']:,}")
    log(f"  Missing:    {stats['missing']:,}")
    log(f"  Errors:     {stats['errors']:,}")
    log(f"{'='*60}\n")


if __name__ == "__main__":
    main()

