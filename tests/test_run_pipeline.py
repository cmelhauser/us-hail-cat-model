"""Extended tests for run_pipeline.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import load_stage


@pytest.fixture
def rp():
    return load_stage("run_pipeline.py")


def test_run_pipeline_stage_ids_are_unique_and_complete(rp):
    ids = [s[0] for s in rp.STAGES]
    assert len(ids) == len(set(ids))
    assert ids == [
        "01", "02", "03", "04a", "04b", "04c", "05", "06", "07", "08", "09",
        "10", "11", "11b", "12", "13", "14",
    ]
    assert "15" not in ids


def test_run_pipeline_formats_duration(rp):
    assert rp.fmt_duration(45) == "45s"
    assert rp.fmt_duration(75) == "1m 15s"
    assert rp.fmt_duration(3665) == "1h 01m"


def test_apply_streaming_gridrad_skip_defaults(rp):
    ids = [s[0] for s in rp.STAGES]
    f = rp.apply_streaming_gridrad_skip_defaults

    assert "04b" in f(set(), only_stage=None, from_stage=None, all_ids=ids)
    assert "04b" not in f({"04c"}, only_stage=None, from_stage=None, all_ids=ids)
    assert "04b" not in f(set(), only_stage="04b", from_stage=None, all_ids=ids)
    assert "04b" in f(set(), only_stage=None, from_stage="04a", all_ids=ids)
    assert "04b" not in f(set(), only_stage=None, from_stage="04b", all_ids=ids)
    assert "04b" not in f(set(), only_stage=None, from_stage="04c", all_ids=ids)


def test_print_header(rp, capsys):
    rp.print_header()
    out = capsys.readouterr().out
    assert "Pipeline Runner" in out
    assert "Stages:" in out


def test_check_dependencies_missing(rp, monkeypatch):
    real_import = rp.importlib.import_module

    def fake_import(name):
        if name == "nonexistent_pkg_xyz":
            raise ImportError
        return real_import(name)

    monkeypatch.setattr(rp, "REQUIRED_PACKAGES", [("fake-pkg", "nonexistent_pkg_xyz")])
    monkeypatch.setattr(rp.importlib, "import_module", fake_import)
    assert rp.check_dependencies() is False


def test_check_dependencies_ok(rp):
    assert rp.check_dependencies() is True


def test_run_stage_dry_run(rp, capsys):
    ok = rp.run_stage("01", "01_download_myrorss.py", "desc", "1m", dry_run=True)
    assert ok is True
    assert "DRY RUN" in capsys.readouterr().out


def test_run_stage_missing_script(rp, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rp, "SCRIPTS", tmp_path)
    monkeypatch.setattr(rp, "LOGS", tmp_path)
    ok = rp.run_stage("01", "missing.py", "desc", "1m", dry_run=False)
    assert ok is False
    assert "Script not found" in capsys.readouterr().out


def test_run_stage_success(tmp_path, rp, monkeypatch):
    monkeypatch.setattr(rp, "LOGS", tmp_path)
    monkeypatch.setattr(rp, "SCRIPTS", tmp_path)
    script = tmp_path / "01_download_myrorss.py"
    script.write_text("#!/usr/bin/env python3\n")

    class FakeProc:
        returncode = 0
        stdout = iter(["Done\n"])

        def wait(self):
            return 0

        def poll(self):
            return 0

        def terminate(self):
            return None

    monkeypatch.setattr(rp.subprocess, "Popen", lambda *_a, **_kw: FakeProc())
    assert rp.run_stage("01", "01_download_myrorss.py", "desc", "1m", False) is True


def test_run_stage_failure(tmp_path, rp, monkeypatch):
    monkeypatch.setattr(rp, "LOGS", tmp_path)
    monkeypatch.setattr(rp, "SCRIPTS", tmp_path)
    (tmp_path / "01_download_myrorss.py").write_text("#!/usr/bin/env python3\n")

    class FakeProc:
        returncode = 2
        stdout = iter([])

        def wait(self):
            return 2

    monkeypatch.setattr(rp.subprocess, "Popen", lambda *_a, **_kw: FakeProc())
    assert rp.run_stage("01", "01_download_myrorss.py", "desc", "1m", False) is False


def test_run_stage_validate_only_adds_flag(tmp_path, rp, monkeypatch):
    monkeypatch.setattr(rp, "LOGS", tmp_path)
    monkeypatch.setattr(rp, "SCRIPTS", tmp_path)
    (tmp_path / "01_download_myrorss.py").write_text("#!/usr/bin/env python3\n")
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = iter([])

        def wait(self):
            return 0

    monkeypatch.setattr(
        rp.subprocess,
        "Popen",
        lambda cmd, **_kw: (captured.__setitem__("cmd", list(cmd)) or FakeProc()),
    )
    rp.run_stage("01", "01_download_myrorss.py", "desc", "1m", False, validate_only=True)
    assert "--validate" in captured["cmd"]


def test_run_stage_04c_extra_args(tmp_path, rp, monkeypatch):
    monkeypatch.setattr(rp, "LOGS", tmp_path)
    monkeypatch.setattr(rp, "SCRIPTS", tmp_path)
    (tmp_path / "04c_fill_gridrad_gap.py").write_text("#!/usr/bin/env python3\n")
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = iter([])

        def wait(self):
            return 0

    monkeypatch.setattr(
        rp.subprocess,
        "Popen",
        lambda cmd, **_kw: (captured.__setitem__("cmd", list(cmd)) or FakeProc()),
    )
    rp.run_stage("04c", "04c_fill_gridrad_gap.py", "desc", "1m", False)
    assert "--with-04b-download" in captured["cmd"]
    assert "--workers" in captured["cmd"]


def test_run_stage_handles_interrupt_before_process_initialization(tmp_path, rp, monkeypatch):
    monkeypatch.setattr(rp, "LOGS", tmp_path)

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.open", interrupt)
    with pytest.raises(SystemExit) as exc_info:
        rp.run_stage("01", "01_download_myrorss.py", "test", "unknown", False)
    assert exc_info.value.code == 1


def test_run_stage_keyboard_interrupt_terminates_proc(tmp_path, rp, monkeypatch):
    monkeypatch.setattr(rp, "LOGS", tmp_path)
    monkeypatch.setattr(rp, "SCRIPTS", tmp_path)
    (tmp_path / "01_download_myrorss.py").write_text("#!/usr/bin/env python3\n")

    class FakeProc:
        returncode = None
        stdout = iter(["line\n"])
        terminated = False

        def wait(self):
            raise KeyboardInterrupt

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

    proc = FakeProc()
    monkeypatch.setattr(rp.subprocess, "Popen", lambda *_a, **_kw: proc)
    with pytest.raises(SystemExit) as exc:
        rp.run_stage("01", "01_download_myrorss.py", "desc", "1m", False)
    assert exc.value.code == 1
    assert proc.terminated is True


def test_run_stage_exception_returns_false(tmp_path, rp, monkeypatch):
    monkeypatch.setattr(rp, "LOGS", tmp_path)
    monkeypatch.setattr(rp, "SCRIPTS", tmp_path)
    (tmp_path / "01_download_myrorss.py").write_text("#!/usr/bin/env python3\n")
    monkeypatch.setattr(rp.subprocess, "Popen", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("boom")))
    assert rp.run_stage("01", "01_download_myrorss.py", "desc", "1m", False) is False


def test_run_stage_never_forwards_spc_hazard_adjustments(tmp_path, rp, monkeypatch):
    monkeypatch.setattr(rp, "LOGS", tmp_path)
    monkeypatch.setattr(rp, "SCRIPTS", tmp_path)
    script = tmp_path / "05_apply_mesh_bias_correction.py"
    script.write_text("#!/usr/bin/env python3\n")
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = iter([])

        def wait(self):
            return 0

        def poll(self):
            return 0

        def terminate(self):
            return None

    monkeypatch.setattr(
        rp.subprocess,
        "Popen",
        lambda cmd, **_kw: (captured.__setitem__("cmd", list(cmd)) or FakeProc()),
    )
    ok = rp.run_stage(
        "05",
        "05_apply_mesh_bias_correction.py",
        "test",
        "1m",
        False,
        retrain_models=True,
        skip_ml=True,
        skip_calibration=True,
    )
    assert ok is True
    assert "--retrain-models" in captured["cmd"]
    assert "--skip-ml" in captured["cmd"]
    assert "--skip-calibration" in captured["cmd"]
    assert "--allow-spc-derived-adjustments" not in captured["cmd"]


def test_main_dry_run(rp, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--dry-run", "--only", "01"])
    rp.main()
    assert "Dry run complete" in capsys.readouterr().out


def test_main_validate_only(rp, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--validate", "--only", "01"])
    monkeypatch.setattr(rp, "run_stage", lambda *_a, **_kw: True)
    rp.main()
    assert "VALIDATE ONLY" in capsys.readouterr().out


def test_main_only_unknown_stage(rp, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--only", "nope"])
    with pytest.raises(SystemExit) as exc:
        rp.main()
    assert exc.value.code == 1


def test_main_from_unknown_stage(rp, monkeypatch):
    # apply_streaming_gridrad_skip_defaults indexes from_stage first; bypass it
    # so main()'s own ValueError handler (lines 316-318) is exercised.
    monkeypatch.setattr(rp, "apply_streaming_gridrad_skip_defaults", lambda skip, **_k: skip)
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--from", "nope"])
    with pytest.raises(SystemExit) as exc:
        rp.main()
    assert exc.value.code == 1


def test_main_from_unknown_raises_in_skip_defaults(rp, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--from", "nope"])
    with pytest.raises(ValueError):
        rp.main()


def test_scripts_dir_path_insert_on_reload(monkeypatch):
    """Cover run_pipeline.py line 45 by reloading with scripts/ absent from sys.path."""
    import importlib
    import run_pipeline as rp_mod

    scripts = str(Path(rp_mod.__file__).resolve().parent / "scripts")
    saved = [p for p in sys.path if p == scripts]
    sys.path[:] = [p for p in sys.path if p != scripts]
    try:
        importlib.reload(rp_mod)
    finally:
        for p in saved:
            if p not in sys.path:
                sys.path.insert(0, p)
        # Ensure subsequent tests see a healthy module
        importlib.reload(rp_mod)


def test_main_skip_and_from(rp, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--from", "13", "--skip", "14", "--dry-run"])
    rp.main()
    out = capsys.readouterr().out
    assert "Stages to run: 1" in out


def test_main_clean_from_invalid(rp, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--clean-from", "bad"])
    with pytest.raises(SystemExit) as exc:
        rp.main()
    assert exc.value.code == 1


def test_main_clean_from_and_run(rp, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--clean-from", "14", "--only", "14", "--dry-run"])
    removed = [tmp_path / "fig.png"]

    def fake_clean(stage_id, dry_run=False, include_diagnostics=False):
        assert stage_id == "14"
        return removed

    monkeypatch.setattr("scripts._pipeline_cleanup.clean_from_stage", fake_clean)
    # dry-run skips clean_from; exercise non-dry path with mocked run_stage
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--clean-from", "14", "--only", "14"])
    monkeypatch.setattr(rp, "run_stage", lambda *_a, **_kw: True)
    rp.main()
    assert "Cleaned" in capsys.readouterr().out


def test_main_dependency_failure(rp, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--only", "01"])
    monkeypatch.setattr(rp, "check_dependencies", lambda: False)
    with pytest.raises(SystemExit) as exc:
        rp.main()
    assert exc.value.code == 1


def test_main_stage_failure_stops(rp, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--only", "01"])
    monkeypatch.setattr(rp, "run_stage", lambda *_a, **_kw: False)
    with pytest.raises(SystemExit) as exc:
        rp.main()
    assert exc.value.code == 1


def test_main_success_message(rp, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--only", "01"])
    monkeypatch.setattr(rp, "run_stage", lambda *_a, **_kw: True)
    rp.main()
    assert "completed successfully" in capsys.readouterr().out


def test_main_auto_skip_04b_banner(rp, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--dry-run"])
    rp.main()
    assert "Skipping stage 04b" in capsys.readouterr().out


def test_main_retrain_and_skip_ml_banners(rp, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_pipeline.py", "--dry-run", "--retrain-models", "--skip-ml"],
    )
    rp.main()
    out = capsys.readouterr().out
    assert "RETRAIN OPTIONAL v2.1 MODELS" in out
    assert "SKIP OPTIONAL ML" in out


def test_main_from_valid_stage_dry_run(rp, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--from", "13", "--dry-run"])
    rp.main()
    assert "Stages to run: 2" in capsys.readouterr().out


def test_main_full_pipeline_dry_run(rp, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--dry-run"])
    rp.main()
    assert "Stages to run: 16" in capsys.readouterr().out
