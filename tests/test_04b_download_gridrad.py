from __future__ import annotations

from datetime import date


def test_stage04b_download_gridrad_workers_default(load_script):
    s = load_script("04b_download_gridrad.py")
    p = s.build_arg_parser()
    assert p.parse_args([]).workers == 4


def test_stage04b_download_gridrad_catalog_url_shape(load_script):
    s = load_script("04b_download_gridrad.py")
    d = date(2015, 5, 1)
    url = s._catalog_url(s.DS_HOURLY, d)
    assert s.DS_HOURLY in url
    assert "catalog.xml" in url
    assert "2015" in url
    assert "201505" in url

