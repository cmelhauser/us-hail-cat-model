"""Coverage tests for Stage 04b — download helpers, THREDDS mocks, main()."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import requests


def test_stage04b_request_session_and_auth(load_script, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    sess = s._request_session()
    assert sess.trust_env is True
    sess.close()

    monkeypatch.delenv("GDEX_TOKEN", raising=False)
    monkeypatch.delenv("GDEX_API_TOKEN", raising=False)
    assert s._auth_params() == {}

    monkeypatch.setenv("GDEX_TOKEN", "tok")
    assert s._auth_params() == {"token": "tok"}


def test_stage04b_retry_helpers(load_script, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    assert s._retryable_http_error(requests.ConnectionError())
    resp = type("R", (), {"status_code": 503})()
    err = requests.HTTPError(response=resp)
    assert s._retryable_http_error(err)
    assert not s._retryable_http_error(ValueError("nope"))
    monkeypatch.setattr(s, "time", type("T", (), {"sleep": lambda *_a, **_k: None})())
    s._sleep_backoff(1)


def test_stage04b_catalog_get_retries(load_script, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    calls = {"n": 0}

    class Resp:
        status_code = 503

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

    class Sess:
        def get(self, url, timeout=60, stream=False):
            calls["n"] += 1
            if calls["n"] < 2:
                raise requests.HTTPError(response=Resp())
            r = Resp()
            r.status_code = 200
            r.text = "ok"
            r.raise_for_status = lambda: None
            return r

    monkeypatch.setattr(s, "time", type("T", (), {"sleep": lambda *_a, **_k: None})())
    out = s._catalog_get(Sess(), "http://x", timeout=(1.0, 1.0))
    assert out.status_code == 200

    class NotFound:
        status_code = 404
        text = ""

        def raise_for_status(self):
            return None

    class Sess404:
        def get(self, url, timeout=60, stream=False):
            return NotFound()

    assert s._catalog_get(Sess404(), "http://x", timeout=(1.0, 1.0)).status_code == 404


def test_stage04b_fileserver_url_errors(load_script):
    s = load_script("04b_download_gridrad.py")
    with pytest.raises(ValueError):
        s._fileserver_url("bad", date(2015, 1, 1), "x.nc")
    with pytest.raises(ValueError):
        s._catalog_url("bad", date(2015, 1, 1))


def _download_item(s, tmp_path, day, *, name="nexrad_3d_v3_1_20150501T120000Z.nc"):
    return s.DownloadItem(
        dsid=s.DS_HOURLY,
        convective_day=day,
        catalog_day=day,
        filename=name,
        url="http://example.com/file.nc",
        out_path=tmp_path / name,
    )


def test_stage04b_download_one_paths(load_script, tmp_path, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    day = date(2015, 5, 1)
    item = _download_item(s, tmp_path, day)

    class Sess:
        pass

    existing = tmp_path / "exists.nc"
    existing.write_bytes(b"data")
    item2 = _download_item(s, tmp_path, day, name="exists.nc")
    item2 = s.DownloadItem(
        dsid=item2.dsid,
        convective_day=item2.convective_day,
        catalog_day=item2.catalog_day,
        filename=item2.filename,
        url=item2.url,
        out_path=existing,
    )
    _, status = s._download_one(Sess(), item2, connect_timeout=1.0, read_timeout=1.0)
    assert status == "skipped"

    class Resp404:
        status_code = 404

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=0):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Sess404:
        def get(self, url, params=None, stream=True, timeout=None):
            return Resp404()

    _, status = s._download_one(Sess404(), item, connect_timeout=1.0, read_timeout=1.0)
    assert status == "missing"

    class RespOK:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=0):
            yield b"nc-bytes"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class SessOK:
        def get(self, url, params=None, stream=True, timeout=None):
            return RespOK()

    monkeypatch.setattr(s, "_auth_params", lambda: {})
    _, status = s._download_one(SessOK(), item, connect_timeout=1.0, read_timeout=1.0)
    assert status == "downloaded"
    assert item.out_path.exists()


def test_stage04b_download_planned_items_and_merge(load_script, tmp_path, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    day = date(2015, 5, 1)
    item = _download_item(s, tmp_path, day, name="f.nc")
    item.out_path.write_bytes(b"x")

    class Sess:
        pass

    stats = s.download_planned_items(
        Sess(), [item], connect_timeout=1.0, read_timeout=1.0, max_workers=2,
    )
    assert stats["skipped"] == 1
    assert s.download_planned_items(Sess(), [], connect_timeout=1.0, read_timeout=1.0, max_workers=1)["downloaded"] == 0

    merged = s._merge_download_stats(
        {"downloaded": 1, "skipped": 0, "missing": 0, "errors": 0},
        {"downloaded": 2, "skipped": 1, "missing": 0, "errors": 1},
    )
    assert merged["downloaded"] == 3 and merged["errors"] == 1


def test_stage04b_severe_staging_covers_day(load_script, tmp_path, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    monkeypatch.setattr(s, "GRIDRAD_SEV_DIR", tmp_path)
    day = date(2015, 5, 1)
    d = tmp_path / "by_convective_day" / "20150501"
    d.mkdir(parents=True)
    # Dense 5-min coverage across convective window
    for hour in range(12, 36):
        (d / f"nexrad_3d_v4_2_2015050{'1' if hour < 24 else '2'}T{hour % 24:02d}0000Z.nc").write_bytes(b"x")
    monkeypatch.setattr(
        s,
        "staged_nc_files_for_convective_day",
        lambda base, cd: list((base / "by_convective_day" / cd.strftime("%Y%m%d")).glob("*.nc")),
    )
    monkeypatch.setattr(
        s,
        "observation_times_from_paths",
        lambda paths, cd: [cd for _ in paths],
    )
    monkeypatch.setattr(s, "convective_window_coverage_ok", lambda *_a, **_k: True)
    assert s._severe_staging_covers_day(day) is True


def test_stage04b_download_for_day_adaptive_local_severe(load_script, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    day = date(2015, 5, 1)
    monkeypatch.setattr(s, "_severe_staging_covers_day", lambda _d: True)
    monkeypatch.setattr(s, "staged_nc_files_for_convective_day", lambda *_a, **_k: [Path("a.nc"), Path("b.nc")])

    class Sess:
        def close(self):
            return None

    stats = s.download_for_day_adaptive(
        Sess(), day, catalog_timeout=(1.0, 1.0), connect_timeout=1.0, read_timeout=1.0, max_workers=1,
    )
    assert stats["source_mode"] == "severe-only-local"


def test_stage04b_main_branches(load_script, monkeypatch, tmp_path):
    s = load_script("04b_download_gridrad.py")
    day = date(2015, 5, 1)
    item = _download_item(s, tmp_path, day)

    class Sess:
        def close(self):
            return None

    monkeypatch.setattr(s, "_request_session", lambda: Sess())
    monkeypatch.setattr(s, "plan_downloads_for_day", lambda *_a, **_k: [item])
    monkeypatch.setattr(
        s,
        "download_planned_items",
        lambda *_a, **_k: {"downloaded": 1, "skipped": 0, "missing": 0, "errors": 0},
    )
    monkeypatch.setattr(
        s,
        "download_for_day",
        lambda *_a, **_k: {"downloaded": 1, "skipped": 0, "missing": 0, "errors": 0},
    )

    with pytest.raises(SystemExit) as exc:
        s.main(["--check-data", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--dry-run", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0

    s.main(["--plan-all-days-first", "--year", "2015", "--month", "5", "--workers", "2"])

    s.main(["--year", "2015", "--month", "5", "--workers", "11"])

    s.main(["--year", "2015", "--month", "5"])

    with pytest.raises(SystemExit):
        s.main(["--hourly-only", "--severe-only"])

    monkeypatch.setenv("GDEX_API_TOKEN", "x")
    with pytest.raises(SystemExit) as exc:
        s.main(["--plan-all-days-first", "--check-data", "--year", "2015"])
    assert exc.value.code == 0
