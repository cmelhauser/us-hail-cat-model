"""Tests for scripts/rerun_stage05.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import load_stage


@pytest.fixture
def rerun():
    return load_stage("rerun_stage05.py")


def test_pid_alive_branches(rerun, monkeypatch):
    assert rerun._pid_alive(0) is False
    assert rerun._pid_alive(-1) is False

    def kill_ok(pid, sig):
        return None

    monkeypatch.setattr(rerun.os, "kill", kill_ok)
    assert rerun._pid_alive(123) is True

    def kill_missing(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(rerun.os, "kill", kill_missing)
    assert rerun._pid_alive(123) is False

    def kill_perm(pid, sig):
        raise PermissionError

    monkeypatch.setattr(rerun.os, "kill", kill_perm)
    assert rerun._pid_alive(123) is True


def test_read_stage05_pid(rerun, tmp_path, monkeypatch):
    pid_file = tmp_path / "stage05.pid"
    monkeypatch.setattr(rerun, "STAGE05_PID", pid_file)
    assert rerun._read_stage05_pid() is None
    pid_file.write_text("not-an-int")
    assert rerun._read_stage05_pid() is None
    pid_file.write_text("42\n")
    assert rerun._read_stage05_pid() == 42


def test_wait_for_stage05(rerun, tmp_path, monkeypatch):
    pid_file = tmp_path / "stage05.pid"
    monkeypatch.setattr(rerun, "STAGE05_PID", pid_file)
    sleeps: list[float] = []

    monkeypatch.setattr(rerun.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(rerun, "_read_stage05_pid", lambda: None)

    calls = {"n": 0}

    def fake_check_output(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return f"{rerun.os.getpid()}\n99999\n"
        raise subprocess.CalledProcessError(1, "pgrep")

    monkeypatch.setattr(rerun.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(rerun, "_pid_alive", lambda pid: False)
    logs: list[str] = []
    rerun.wait_for_stage05(poll_sec=0.01, log=logs.append)
    assert sleeps  # waited once for pgrep match
    assert not pid_file.exists()


def test_run_stage05_streams(rerun, tmp_path, monkeypatch):
    monkeypatch.setattr(rerun, "LOG_DIR", tmp_path)
    monkeypatch.setattr(rerun, "STAGE05_SCRIPT", tmp_path / "05.py")
    log_path = tmp_path / "run.log"

    class FakeProc:
        returncode = 0
        stdout = iter(["progress done=1\n", "noise\n", "Complete\n"])

        def wait(self):
            return 0

    monkeypatch.setattr(rerun.subprocess, "Popen", lambda *a, **k: FakeProc())
    rc = rerun.run_stage05(extra_args=["--skip-ml"], log_path=log_path, log=lambda *_: None)
    assert rc == 0
    assert log_path.exists()


def test_main_dry_run_and_failure(rerun, tmp_path, monkeypatch):
    monkeypatch.setattr(rerun, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        rerun,
        "parse_args",
        lambda: SimpleNamespace(
            no_wait=True,
            no_clean=False,
            dry_run=True,
            with_validate=False,
            skip_calibration=True,
            skip_ml=True,
            log=tmp_path / "x.log",
        ),
    )
    monkeypatch.setattr(rerun, "clean_from_stage", lambda *a, **k: [])
    rerun.main()

    monkeypatch.setattr(
        rerun,
        "parse_args",
        lambda: SimpleNamespace(
            no_wait=True,
            no_clean=False,
            dry_run=False,
            with_validate=False,
            skip_calibration=True,
            skip_ml=True,
            log=tmp_path / "x.log",
        ),
    )
    monkeypatch.setattr(rerun, "clean_from_stage", lambda *a, **k: [tmp_path / "gone"])
    monkeypatch.setattr(rerun, "run_stage05", lambda **k: 7)
    with pytest.raises(SystemExit) as exc:
        rerun.main()
    assert exc.value.code == 7


def test_main_with_validate(rerun, tmp_path, monkeypatch):
    monkeypatch.setattr(rerun, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        rerun,
        "parse_args",
        lambda: SimpleNamespace(
            no_wait=False,
            no_clean=False,
            dry_run=False,
            with_validate=True,
            skip_calibration=False,
            skip_ml=False,
            log=tmp_path / "x.log",
        ),
    )
    monkeypatch.setattr(rerun, "wait_for_stage05", lambda **k: None)
    monkeypatch.setattr(rerun, "clean_from_stage", lambda *a, **k: [Path("a")])
    monkeypatch.setattr(rerun, "run_stage05", lambda **k: 0)

    class RR:
        returncode = 3

    monkeypatch.setattr(rerun.subprocess, "run", lambda *a, **k: RR())
    with pytest.raises(SystemExit) as exc:
        rerun.main()
    assert exc.value.code == 3

    class RR0:
        returncode = 0

    monkeypatch.setattr(rerun.subprocess, "run", lambda *a, **k: RR0())
    rerun.main()


def test_parse_args_defaults(rerun, monkeypatch):
    monkeypatch.setattr("sys.argv", ["rerun_stage05.py", "--dry-run", "--no-wait"])
    args = rerun.parse_args()
    assert args.dry_run is True
    assert args.no_wait is True
