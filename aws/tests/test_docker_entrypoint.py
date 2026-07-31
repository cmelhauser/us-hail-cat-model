"""Smoke tests for aws/docker-entrypoint.sh (no Docker daemon required)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[1] / "docker-entrypoint.sh"


def _env_with_python_shim(tmp_path: Path, **extra: str) -> dict[str, str]:
    """Ensure ``python`` resolves even when only ``python3`` is on PATH."""
    shim = tmp_path / "bin"
    shim.mkdir(parents=True, exist_ok=True)
    link = shim / "python"
    if not link.exists():
        link.symlink_to(sys.executable)
    env = {**os.environ, **extra}
    env["PATH"] = f"{shim}:{env.get('PATH', '')}"
    return env


def test_entrypoint_writes_cdsapirc(tmp_path: Path) -> None:
    env = _env_with_python_shim(
        tmp_path,
        HOME=str(tmp_path),
        CDSAPI_URL="https://cds.example/api",
        CDSAPI_KEY="token-xyz",
    )
    # Use python -c as the payload so we do not need the pipeline installed.
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "python", "-c", "print('ok')"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
    cds = tmp_path / ".cdsapirc"
    assert cds.is_file()
    text = cds.read_text(encoding="utf-8")
    assert "https://cds.example/api" in text
    assert "token-xyz" in text
    assert (cds.stat().st_mode & 0o077) == 0  # umask 077 → owner-only


def test_entrypoint_passes_through_python_args(tmp_path: Path) -> None:
    env = _env_with_python_shim(tmp_path)
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "python", "-c", "import sys; print(sys.argv[1])", "hello"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"


def test_entrypoint_default_invokes_python_on_script_args(tmp_path: Path) -> None:
    # Without a leading "python", args are passed to `python "$@"`.
    env = _env_with_python_shim(tmp_path)
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "probe.py"
        script.write_text("print('probe')\n", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(ENTRYPOINT), str(script)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=td,
        )
    assert result.returncode == 0
    assert "probe" in result.stdout
