#!/usr/bin/env python3
"""Fail if mandated coverage / CI / agent policy text drifts out of sync."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []

    pyproject = _read("pyproject.toml")
    m = re.search(r"^fail_under\s*=\s*(\d+)", pyproject, flags=re.M)
    if not m or int(m.group(1)) != 100:
        errors.append("pyproject.toml must set [tool.coverage.report] fail_under = 100")
    if 'source = ["scripts", "run_pipeline"]' not in pyproject:
        errors.append(
            'pyproject.toml coverage source must include ["scripts", "run_pipeline"]'
        )

    ci = _read(".github/workflows/tests.yml")
    if "--cov-fail-under=100" not in ci:
        errors.append(".github/workflows/tests.yml must enforce --cov-fail-under=100")
    if "--cov=scripts" not in ci or "--cov=run_pipeline" not in ci:
        errors.append(
            ".github/workflows/tests.yml unit tests must cover scripts and run_pipeline"
        )
    if re.search(r"--cov-fail-under=35\b", ci):
        errors.append(".github/workflows/tests.yml still references cov-fail-under=35")

    agents = _read("AGENTS.md")
    if "fail_under = 100" not in agents and "fail_under=100" not in agents:
        errors.append("AGENTS.md must document the 100% scripts coverage gate")
    if "quality_gate" not in agents and "Quality gate" not in agents:
        errors.append("AGENTS.md must document the mandatory pre-commit quality gate")

    ai = _read("docs/ai_instructions.md")
    if "100%" not in ai or "quality_gate" not in ai.lower():
        errors.append(
            "docs/ai_instructions.md must require 100% coverage and the quality gate"
        )

    # Stale SPC hazard opt-in must not reappear in operator docs.
    operator_paths = [
        "AGENTS.md",
        "README.md",
        "docs/RUN_NOTES.md",
        "docs/HANDOFF.md",
        "docs/reproduce.md",
        "docs/FAQ.md",
        "docs/technical_documentation.md",
    ]
    for rel in operator_paths:
        text = _read(rel)
        if "--allow-spc-derived-adjustments" in text:
            errors.append(
                f"{rel}: remove --allow-spc-derived-adjustments "
                "(SPC is validation-only; never a hazard input)"
            )

    aws_readme = _read("aws/README.md")
    if "fail_under = 35" in aws_readme or "fail_under=35" in aws_readme:
        errors.append("aws/README.md still documents the obsolete scripts fail_under=35")

    if errors:
        print("Policy consistency check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("Policy consistency check passed (coverage=100%, CI/docs aligned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
