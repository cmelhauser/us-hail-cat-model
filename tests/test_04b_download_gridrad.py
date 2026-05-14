from __future__ import annotations

from datetime import date


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

