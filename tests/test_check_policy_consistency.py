"""Tests for scripts/check_policy_consistency.py."""

from __future__ import annotations

import scripts.check_policy_consistency as policy


def _write_tree(root, *, pyproject: str, ci: str, agents: str, ai: str, aws: str, operator: str = "ok\n"):
    (root / "scripts").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    (root / "aws").mkdir(exist_ok=True)
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (root / ".github" / "workflows" / "tests.yml").write_text(ci, encoding="utf-8")
    (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    (root / "docs" / "ai_instructions.md").write_text(ai, encoding="utf-8")
    (root / "aws" / "README.md").write_text(aws, encoding="utf-8")
    for name in (
        "README.md",
        "docs/RUN_NOTES.md",
        "docs/HANDOFF.md",
        "docs/reproduce.md",
        "docs/FAQ.md",
        "docs/technical_documentation.md",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(operator, encoding="utf-8")


def test_policy_consistency_passes_on_current_repo():
    assert policy.main() == 0


def test_policy_consistency_detects_fail_under_drift(tmp_path, monkeypatch):
    _write_tree(
        tmp_path,
        pyproject='[tool.coverage.report]\nfail_under = 35\n',
        ci="--cov=scripts\n--cov-fail-under=35\n",
        agents="no gate here\n",
        ai="no gate here\n",
        aws="fail_under = 35\n",
        operator="uses --allow-spc-derived-adjustments\n",
    )
    monkeypatch.setattr(policy, "ROOT", tmp_path)
    assert policy.main() == 1


def test_policy_consistency_detects_missing_coverage_source(tmp_path, monkeypatch):
    _write_tree(
        tmp_path,
        pyproject='[tool.coverage.report]\nfail_under = 100\nsource = ["scripts"]\n',
        ci="--cov=scripts\n--cov-fail-under=100\n",
        agents="fail_under = 100\nquality_gate\n",
        ai="100% quality_gate\n",
        aws="ok\n",
    )
    monkeypatch.setattr(policy, "ROOT", tmp_path)
    assert policy.main() == 1
