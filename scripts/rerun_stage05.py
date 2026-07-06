#!/usr/bin/env python3
"""
rerun_stage05.py — Wait, clean Stage 05+ outputs, and rerun Stage 05 (blocking).

Use this instead of background shell wrappers so the process is not killed when
an agent or terminal session ends. Stage 05 runs in the foreground and is waited
on to completion.

Usage (repo root):
  python scripts/rerun_stage05.py
  python scripts/rerun_stage05.py --no-wait          # do not wait for a running Stage 05
  python scripts/rerun_stage05.py --dry-run          # print actions only
  python scripts/rerun_stage05.py --with-validate    # chain Stage 06 after Stage 05

Equivalent via run_pipeline.py:
  python run_pipeline.py --only 05 --clean-from 05 --skip-ml --skip-calibration
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts._pipeline_cleanup import STAGE05_PID, clean_from_stage  # noqa: E402

STAGE05_SCRIPT = _REPO / "scripts" / "05_apply_mesh_bias_correction.py"
STAGE06_SCRIPT = _REPO / "scripts" / "06_validate_mesh_vs_spc.py"
LOG_DIR = _REPO / "logs"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_stage05_pid() -> int | None:
    if not STAGE05_PID.exists():
        return None
    try:
        return int(STAGE05_PID.read_text().strip())
    except (ValueError, OSError):
        return None


def wait_for_stage05(*, poll_sec: float = 10.0, log=print) -> None:
    """Block until no Stage 05 process is running (pid file + process scan)."""
    while True:
        pid = _read_stage05_pid()
        if pid is not None and _pid_alive(pid):
            log(f"  Stage 05 running (pid {pid}); waiting {poll_sec:.0f}s...")
            time.sleep(poll_sec)
            continue
        # Fallback: match script name in process list (pid file may be stale).
        try:
            out = subprocess.check_output(["pgrep", "-f", "05_apply_mesh_bias_correction.py"], text=True)
            pids = [int(x) for x in out.split() if x.strip()]
            pids = [p for p in pids if p != os.getpid()]
            if pids:
                log(f"  Stage 05 running (pids {pids}); waiting {poll_sec:.0f}s...")
                time.sleep(poll_sec)
                continue
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        if STAGE05_PID.exists():
            try:
                STAGE05_PID.unlink()
            except OSError:
                pass
        return


def run_stage05(*, extra_args: list[str], log_path: Path, log=print) -> int:
    """Run Stage 05 in the foreground; stream output to log and stdout."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(STAGE05_SCRIPT), *extra_args]
    env = os.environ.copy()
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("MPLCONFIGDIR", str(LOG_DIR / "mplconfig"))

    log(f"  Command: {' '.join(cmd)}")
    log(f"  Log:     {log_path}")
    t0 = time.time()
    with log_path.open("w", encoding="utf-8") as log_fh:
        log_fh.write(f"[{datetime.now(timezone.utc).isoformat()}] {' '.join(cmd)}\n\n")
        log_fh.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(_REPO),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            log_fh.write(line)
            log_fh.flush()
            stripped = line.rstrip()
            if stripped and any(m in stripped for m in ("done=", "Complete", "ERROR", "ETA=", "validation")):
                print(stripped, flush=True)
        proc.wait()
        elapsed = time.time() - t0
        log_fh.write(f"\n[{datetime.now(timezone.utc).isoformat()}] exit {proc.returncode} ({elapsed:.1f}s)\n")
    log(f"  Stage 05 finished in {elapsed / 60:.1f} min (exit {proc.returncode})")
    return int(proc.returncode)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Clean Stage 05+ outputs and rerun Stage 05 (blocking).")
    p.add_argument("--no-wait", action="store_true", help="Do not wait for an in-flight Stage 05")
    p.add_argument("--no-clean", action="store_true", help="Skip deleting Stage 05+ outputs")
    p.add_argument("--dry-run", action="store_true", help="Print cleanup paths only; do not run Stage 05")
    p.add_argument("--with-validate", action="store_true", help="Run Stage 06 after Stage 05 completes")
    p.add_argument("--skip-calibration", action="store_true", default=True,
                   help="Pass --skip-calibration to Stage 05 (default: on)")
    p.add_argument("--no-skip-calibration", action="store_false", dest="skip_calibration")
    p.add_argument("--skip-ml", action="store_true", default=True,
                   help="Pass --skip-ml to Stage 05 (default: on)")
    p.add_argument("--no-skip-ml", action="store_false", dest="skip_ml")
    p.add_argument("--log", type=Path, default=LOG_DIR / "stage05_rerun.run.log")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    print("rerun_stage05 — clean Stage 05+ outputs and rebuild corrected archive")
    print(f"  repo: {_REPO}")

    if not args.no_wait:
        print("\n[1/3] Waiting for any running Stage 05 to finish...")
        wait_for_stage05()
        print("  No Stage 05 process running.")
    else:
        print("\n[1/3] Skipped wait (--no-wait)")

    print("\n[2/3] Cleaning Stage 05+ generated outputs...")
    removed = clean_from_stage("05", dry_run=args.dry_run, include_diagnostics=True)
    if removed:
        for p in removed:
            print(f"  {'would remove' if args.dry_run else 'removed'}: {p}")
    else:
        print("  (nothing to remove)")

    if args.dry_run:
        print("\nDry run complete — Stage 05 not executed.")
        return

    print("\n[3/3] Running Stage 05 (foreground, blocking)...")
    stage05_args: list[str] = []
    if args.skip_calibration:
        stage05_args.append("--skip-calibration")
    if args.skip_ml:
        stage05_args.append("--skip-ml")

    rc = run_stage05(extra_args=stage05_args, log_path=args.log)
    if rc != 0:
        print(f"Stage 05 failed with exit code {rc}", file=sys.stderr)
        sys.exit(rc)

    if args.with_validate:
        print("\nRunning Stage 06 validation...")
        env = os.environ.copy()
        env.setdefault("OPENBLAS_NUM_THREADS", "1")
        env.setdefault("PYTHONUNBUFFERED", "1")
        rc6 = subprocess.run(
            [sys.executable, str(STAGE06_SCRIPT)],
            cwd=str(_REPO),
            env=env,
            check=False,
        ).returncode
        if rc6 != 0:
            sys.exit(rc6)

    print("\nDone.")


if __name__ == "__main__":
    main()
