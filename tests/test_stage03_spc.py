
def test_stage03_spc_constants(load_script):
    s = load_script("03_download_spc.py")
    assert "hail" in s.TYPES
    assert s.HEADER_SIZE > 0
    assert s.OUT_DIR.name == "spc"
