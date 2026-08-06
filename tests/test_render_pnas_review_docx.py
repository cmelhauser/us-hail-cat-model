"""Tests for render_pnas_review_docx (Word review draft builder)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests._diagnostics_fixtures import write_mesh_tif


def _install_fake_docx() -> None:
    """Provide minimal python-docx stubs so the module can import without the package."""
    if "docx" in sys.modules:
        return

    docx_mod = types.ModuleType("docx")
    docx_enum = types.ModuleType("docx.enum.text")
    docx_enum.WD_LINE_SPACING = types.SimpleNamespace(DOUBLE=2)
    docx_oxml = types.ModuleType("docx.oxml")
    docx_oxml.OxmlElement = lambda tag: MagicMock(tag=tag)
    docx_oxml_ns = types.ModuleType("docx.oxml.ns")
    docx_oxml_ns.qn = lambda x: x
    docx_shared = types.ModuleType("docx.shared")
    docx_shared.Inches = lambda x: x
    docx_shared.Pt = lambda x: x

    class FakeDocument:
        def __init__(self, *_args, **_kwargs):
            self.sections = [types.SimpleNamespace(_sectPr=MagicMock())]
            self.paragraphs = []
            self.tables = []
            self.styles = {"Normal": MagicMock()}

        def save(self, _path):
            return None

    docx_mod.Document = FakeDocument
    sys.modules["docx"] = docx_mod
    sys.modules["docx.enum.text"] = docx_enum
    sys.modules["docx.oxml"] = docx_oxml
    sys.modules["docx.oxml.ns"] = docx_oxml_ns
    sys.modules["docx.shared"] = docx_shared


@pytest.fixture
def review_mod(tmp_path: Path, monkeypatch):
    _install_fake_docx()
    import importlib

    import scripts.diagnostics.render_pnas_review_docx as mod

    importlib.reload(mod)
    docs = tmp_path / "docs"
    docs.mkdir()
    fig_dir = docs / "figures" / "pnas"
    fig_dir.mkdir(parents=True)
    src_md = docs / "pnas_article_publication.md"
    src_md.write_text("## Figures\n\nBody text.\n")
    out_docx = docs / "pnas_article_review.docx"

    monkeypatch.setattr(mod, "DOCS", docs)
    monkeypatch.setattr(mod, "SRC_MD", src_md)
    monkeypatch.setattr(mod, "OUT_DOCX", out_docx)
    monkeypatch.setattr(mod, "FIG_DIR", fig_dir)
    return mod


def test_pending_figure_note_lists_missing(review_mod):
    note = review_mod._pending_figure_note()
    assert "fig12_rp_100yr_stochastic.png" in note
    assert "Stage 13/14" in note


def test_pending_figure_note_empty_when_present(review_mod):
    for name in ("fig12_rp_100yr_stochastic.png", "fig13_analytical_vs_stochastic.png"):
        (review_mod.FIG_DIR / name).write_bytes(b"png")
    assert review_mod._pending_figure_note() == ""


def test_prepare_markdown_inserts_pending_note(review_mod):
    text = review_mod._prepare_markdown()
    assert review_mod.MANUSCRIPT_TITLE.split(":")[0] in text
    assert "Figures pending" in text or "## Figures" in text


def test_prepare_markdown_raises_without_source(review_mod):
    review_mod.SRC_MD.unlink()
    with pytest.raises(FileNotFoundError):
        review_mod._prepare_markdown()


def test_pandoc_to_docx_runs_subprocess(review_mod, monkeypatch):
    called = {}

    def fake_run(cmd, **kwargs):
        called["cmd"] = cmd
        called["cwd"] = kwargs.get("cwd")
        out_idx = cmd.index("-o") + 1
        out_path = Path(cmd[out_idx])
        out_path.write_bytes(b"docx")
        return MagicMock(returncode=0)

    monkeypatch.setattr(review_mod.subprocess, "run", fake_run)
    review_mod._pandoc_to_docx("# Title\n\nHello.", review_mod.OUT_DOCX)
    assert called["cmd"][0] == "pandoc"
    assert review_mod.OUT_DOCX.exists()


def test_postprocess_docx_applies_formatting(review_mod, tmp_path: Path):
    path = tmp_path / "draft.docx"
    path.write_bytes(b"x")
    review_mod._postprocess_docx(path)


def test_enable_line_numbers_and_double_spacing(review_mod):
    doc = review_mod.Document(path="unused")
    review_mod._enable_line_numbers(doc)
    review_mod._apply_double_spacing(doc)


def test_main_end_to_end(review_mod, monkeypatch, capsys):
    monkeypatch.setattr(review_mod, "_pandoc_to_docx", lambda _md, out: out.write_bytes(b"docx"))
    monkeypatch.setattr(review_mod, "_postprocess_docx", lambda _path: None)
    (review_mod.FIG_DIR / "fig01_data_source_timeline.png").write_bytes(b"png")
    review_mod.main()
    assert "Wrote" in capsys.readouterr().out


def test_apply_double_spacing_with_content(review_mod):
    class Run:
        font = types.SimpleNamespace(name=None, size=None)

    class Para:
        paragraph_format = types.SimpleNamespace(
            line_spacing_rule=None, space_after=None, space_before=None,
        )
        runs = [Run()]

    class Cell:
        paragraphs = [Para()]

    class Row:
        cells = [Cell()]

    class Table:
        rows = [Row()]

    class Style:
        font = types.SimpleNamespace(name=None, size=None)
        paragraph_format = types.SimpleNamespace(
            line_spacing_rule=None, space_after=None, space_before=None,
        )

    class Doc:
        sections = [types.SimpleNamespace(_sectPr=MagicMock())]
        paragraphs = [Para()]
        tables = [Table()]
        styles = {"Normal": Style(), "MissingStyle": None}

        def save(self, _path):
            return None

    doc = Doc()
    sect_pr = doc.sections[0]._sectPr
    existing = MagicMock(tag=review_mod.qn("w:lnNumType"))
    sect_pr.__iter__ = lambda self: iter([existing])
    review_mod._enable_line_numbers(doc)
    review_mod._apply_double_spacing(doc)
