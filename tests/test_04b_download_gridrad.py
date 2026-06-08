from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def test_stage04b_download_gridrad_workers_default(load_script):
    s = load_script("04b_download_gridrad.py")
    p = s.build_arg_parser()
    assert p.parse_args([]).workers == 1


def test_stage04b_download_gridrad_catalog_url_shape(load_script):
    s = load_script("04b_download_gridrad.py")
    d = date(2015, 5, 1)
    url = s._catalog_url(s.DS_HOURLY, d)
    assert s.DS_HOURLY in url
    assert "catalog.xml" in url
    assert "2015" in url
    assert "201505" in url

    sev_url = s._catalog_url(s.DS_SEVERE, d)
    assert "d841006" in sev_url
    assert "2015" in sev_url
    assert "20150501" in sev_url


def test_stage04b_download_gridrad_list_day_catalog_files_hourly_filters_by_day(load_script):
    s = load_script("04b_download_gridrad.py")

    class Resp:
        status_code = 200

        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class FakeSession:
        def __init__(self, text):
            self._text = text

        def get(self, url, timeout=60, stream=False):
            return Resp(self._text)

    # Month catalog contains many datasets; only ones with 20150501 should be kept.
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2">
  <dataset name="root">
    <dataset name="nexrad_3d_v4_2_20150501T000000Z.nc" />
    <dataset name="nexrad_3d_v4_2_20150502T000000Z.nc" />
    <dataset name="not_a_netcdf.txt" />
  </dataset>
</catalog>
"""
    fs = FakeSession(xml)
    out = s.list_day_catalog_files(fs, s.DS_HOURLY, date(2015, 5, 1), timeout=(10.0, 10.0))
    assert out == ["nexrad_3d_v4_2_20150501T000000Z.nc"]


def test_stage04b_download_gridrad_list_day_catalog_files_severe_uses_year_catalogref(load_script):
    s = load_script("04b_download_gridrad.py")

    class Resp:
        def __init__(self, text, status=200):
            self.text = text
            self.status_code = status

        def raise_for_status(self):
            return None

    class FakeSession:
        def __init__(self, mapping):
            self._mapping = mapping

        def get(self, url, timeout=60, stream=False):
            return Resp(self._mapping[url])

    year_xml = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2">
  <catalogRef xlink:title="20150508" xlink:href="20150508/catalog.xml" />
</catalog>
"""
    day_xml = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2">
  <dataset name="root">
    <dataset name="nexrad_3d_v4_2_20150508T120000Z.nc" />
    <dataset name="nexrad_3d_v4_2_20150508T120500Z.nc" />
  </dataset>
</catalog>
"""
    y = 2015
    base = s._thredds_base_severe()
    mapping = {
        f"{base}{y}/catalog.xml": year_xml,
        f"{base}{y}/20150508/catalog.xml": day_xml,
    }
    fs = FakeSession(mapping)
    out = s.list_day_catalog_files(fs, s.DS_SEVERE, date(2015, 5, 8), timeout=(10.0, 10.0))
    assert out == [
        "nexrad_3d_v4_2_20150508T120000Z.nc",
        "nexrad_3d_v4_2_20150508T120500Z.nc",
    ]


def test_stage04b_plan_downloads_for_day_convective_window(load_script):
    s = load_script("04b_download_gridrad.py")

    class Resp:
        status_code = 200

        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class FakeSession:
        def __init__(self, mapping):
            self._mapping = mapping

        def get(self, url, timeout=60, stream=False):
            return Resp(self._mapping[url])

    year_xml = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2">
  <catalogRef xlink:title="20160721" xlink:href="20160721/catalog.xml" />
  <catalogRef xlink:title="20160722" xlink:href="20160722/catalog.xml" />
</catalog>
"""
    day21_xml = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2">
  <dataset name="root">
    <dataset name="nexrad_3d_v4_2_20160721T110000Z.nc" />
    <dataset name="nexrad_3d_v4_2_20160721T130000Z.nc" />
  </dataset>
</catalog>
"""
    day22_xml = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2">
  <dataset name="root">
    <dataset name="nexrad_3d_v4_2_20160722T110000Z.nc" />
    <dataset name="nexrad_3d_v4_2_20160722T130000Z.nc" />
  </dataset>
</catalog>
"""
    base = s._thredds_base_severe()
    mapping = {
        f"{base}2016/catalog.xml": year_xml,
        f"{base}2016/20160721/catalog.xml": day21_xml,
        f"{base}2016/20160722/catalog.xml": day22_xml,
    }
    fs = FakeSession(mapping)
    items = s.plan_downloads_for_day(
        fs,
        date(2016, 7, 21),
        hourly=False,
        severe=True,
        catalog_timeout=(10.0, 10.0),
    )
    names = sorted(it.filename for it in items)
    assert names == [
        "nexrad_3d_v4_2_20160721T130000Z.nc",
        "nexrad_3d_v4_2_20160722T110000Z.nc",
    ]
    assert all(
        it.out_path.parent == s._convective_stage_dir(s.GRIDRAD_SEV_DIR, date(2016, 7, 21))
        for it in items
    )


def test_stage04b_download_for_day_adaptive_skips_hourly_when_severe_covers(
    load_script, tmp_path, monkeypatch
):
    s = load_script("04b_download_gridrad.py")
    sev_base = tmp_path / "gridrad_severe"
    hr_base = tmp_path / "gridrad"
    monkeypatch.setattr(s, "GRIDRAD_SEV_DIR", sev_base)
    monkeypatch.setattr(s, "GRIDRAD_DIR", hr_base)

    day = date(2016, 7, 21)
    stage = sev_base / "by_convective_day" / "20160721"
    stage.mkdir(parents=True)
    start = datetime(2016, 7, 21, 12, 0, tzinfo=timezone.utc)
    for i in range(288):
        t = start + timedelta(minutes=5 * i)
        ymd = t.strftime("%Y%m%d")
        hms = t.strftime("%H%M%S")
        (stage / f"nexrad_3d_v4_2_{ymd}T{hms}Z.nc").write_text("x", encoding="utf-8")

    class FakeSession:
        def close(self):
            return None

    stats = s.download_for_day_adaptive(
        FakeSession(),
        day,
        catalog_timeout=(10.0, 10.0),
        connect_timeout=10.0,
        read_timeout=10.0,
        max_workers=1,
    )
    assert stats["source_mode"] == "severe-only-local"
    assert not list(hr_base.rglob("*.nc"))


def test_stage04b_download_for_day_adaptive_hourly_only_without_severe_catalog(
    load_script, tmp_path, monkeypatch
):
    s = load_script("04b_download_gridrad.py")
    sev_base = tmp_path / "gridrad_severe"
    hr_base = tmp_path / "gridrad"
    monkeypatch.setattr(s, "GRIDRAD_SEV_DIR", sev_base)
    monkeypatch.setattr(s, "GRIDRAD_DIR", hr_base)

    day = date(2016, 7, 21)
    monkeypatch.setattr(s, "severe_catalog_has_convective_data", lambda *a, **k: False)

    planned = [object()]
    monkeypatch.setattr(
        s,
        "download_for_day",
        lambda *a, **k: {
            "downloaded": 2,
            "skipped": 0,
            "missing": 0,
            "errors": 0,
        },
    )
    monkeypatch.setattr(
        s,
        "plan_downloads_for_day",
        lambda *a, **k: planned if k.get("hourly") else [],
    )

    class FakeSession:
        def close(self):
            return None

    stats = s.download_for_day_adaptive(
        FakeSession(),
        day,
        catalog_timeout=(10.0, 10.0),
        connect_timeout=10.0,
        read_timeout=10.0,
        max_workers=1,
    )
    assert stats["source_mode"] == "hourly-only"
    assert stats["downloaded"] == 2

