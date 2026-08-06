"""Extended tests for scripts/03_download_spc.py."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import pytest

from conftest import load_stage


@pytest.fixture
def spc():
    return load_stage("03_download_spc.py")


def test_download_one_ok_and_empty(tmp_path, spc, monkeypatch):
    out = tmp_path / "sub" / "file.csv"
    content = b"x" * (spc.HEADER_SIZE + 10)

    class FakeResp:
        def read(self):
            return content

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(spc, "urlopen", lambda *_a, **_k: FakeResp())
    assert spc.download_one("https://example.invalid/x.csv", str(out)) == "ok"
    assert out.is_file()

    small = b"h" * (spc.HEADER_SIZE - 1)
    out2 = tmp_path / "sub" / "file2.csv"

    class SmallResp:
        def read(self):
            return small

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(spc, "urlopen", lambda *_a, **_k: SmallResp())
    assert spc.download_one("https://example.invalid/y.csv", str(out2)) == "empty"


def test_download_one_http_error_and_generic_err(tmp_path, spc, monkeypatch):
    out = str(tmp_path / "f.csv")

    def raise_http(*_a, **_k):
        raise HTTPError("url", 404, "missing", None, None)

    monkeypatch.setattr(spc, "urlopen", raise_http)
    assert spc.download_one("https://example.invalid/x.csv", out) == "miss"

    def raise_other(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr(spc, "urlopen", raise_other)
    assert spc.download_one("https://example.invalid/x.csv", out) == "err:network down"


def test_validate_outputs_missing_dir(spc, tmp_path, monkeypatch):
    monkeypatch.setattr(spc, "OUT_DIR", tmp_path / "missing")
    assert spc.validate_outputs() is False


def test_validate_outputs_too_few_files(spc, tmp_path, monkeypatch):
    out_dir = tmp_path / "spc"
    out_dir.mkdir()
    for i in range(5):
        (out_dir / f"f{i}.csv").write_text("a,b\n1,2\n")
    monkeypatch.setattr(spc, "OUT_DIR", out_dir)
    assert spc.validate_outputs() is False


def test_validate_outputs_passes_with_sample(spc, tmp_path, monkeypatch):
    out_dir = tmp_path / "spc" / "2020"
    out_dir.mkdir(parents=True)
    for i in range(1001):
        (out_dir / f"200101{i:02d}_rpts_hail.csv").write_text("Time,Size\n2020,1.0\n")
    monkeypatch.setattr(spc, "OUT_DIR", tmp_path / "spc")
    assert spc.validate_outputs() is True


def test_validate_outputs_bad_csv_sample(spc, tmp_path, monkeypatch):
    out_dir = tmp_path / "spc"
    out_dir.mkdir()
    for i in range(1001):
        (out_dir / f"file_{i:04d}.csv").write_text("")
    monkeypatch.setattr(spc, "OUT_DIR", out_dir)

    class FixedRandom:
        def __init__(self, _seed):
            pass

        def sample(self, population, k):
            return population[:k]

    monkeypatch.setattr("random.Random", FixedRandom)
    assert spc.validate_outputs() is False


def test_stage03_download_one_skips_existing_nonempty_file(tmp_path, spc):
    f = tmp_path / "240501_rpts_hail.csv"
    f.write_bytes(b"x" * (spc.HEADER_SIZE + 1))
    assert spc.download_one("https://example.invalid/file.csv", str(f)) == "skip"


def test_cli_validate_only_success(spc, monkeypatch):
    monkeypatch.setattr(spc, "validate_outputs", lambda: True)
    monkeypatch.setattr(sys, "argv", ["03_download_spc.py", "--validate"])
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    with pytest.raises(SystemExit) as exc:
        if args.validate:
            sys.exit(0 if spc.validate_outputs() else 1)
    assert exc.value.code == 0


def test_cli_validate_only_failure(spc, monkeypatch):
    monkeypatch.setattr(spc, "validate_outputs", lambda: False)
    monkeypatch.setattr(sys, "argv", ["03_download_spc.py", "--validate"])
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    with pytest.raises(SystemExit) as exc:
        if args.validate:
            sys.exit(0 if spc.validate_outputs() else 1)
    assert exc.value.code == 1


def test_main_download_flow(spc, tmp_path, monkeypatch):
    import datetime as dt

    out_dir = tmp_path / "spc"
    monkeypatch.setattr(spc, "OUT_DIR", out_dir)
    monkeypatch.setattr(spc, "validate_outputs", lambda: True)
    monkeypatch.setattr(spc, "download_one", lambda _u, _o: "skip")

    class PatchedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2004, 3, 2)

    monkeypatch.setattr(spc, "date", PatchedDate)

    class ImmediateExecutor:
        def __init__(self, max_workers=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def submit(self, fn, url, outfile):
            class Fut:
                def result(self):
                    return fn(url, outfile)

            return Fut()

    import concurrent.futures as cf

    monkeypatch.setattr(cf, "ThreadPoolExecutor", ImmediateExecutor)
    spc.main()


def test_main_validate_failure_exits(spc, monkeypatch):
    import datetime as dt

    monkeypatch.setattr(spc, "OUT_DIR", Path("/tmp/unused"))
    monkeypatch.setattr(spc, "validate_outputs", lambda: False)

    class PatchedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2004, 3, 1)

    monkeypatch.setattr(spc, "date", PatchedDate)

    class ImmediateExecutor:
        def __init__(self, max_workers=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def submit(self, fn, url, outfile):
            class Fut:
                def result(self):
                    return fn(url, outfile)

            return Fut()

    import concurrent.futures as cf

    monkeypatch.setattr(cf, "ThreadPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr(spc, "download_one", lambda _u, _o: "ok")
    with pytest.raises(SystemExit) as exc:
        spc.main()
    assert exc.value.code == 1
