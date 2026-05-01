from pathlib import Path
from conftest import load_stage


def test_stage03_download_one_skips_existing_nonempty_file(tmp_path):
    s = load_stage("03_download_spc.py")
    f = tmp_path / "240501_rpts_hail.csv"
    f.write_bytes(b"x" * (s.HEADER_SIZE + 1))
    assert s.download_one("https://example.invalid/file.csv", str(f)) == "skip"
