from conftest import load_stage


def test_run_pipeline_stage_ids_are_unique_and_complete():
    p = load_stage("run_pipeline.py")
    ids = [s[0] for s in p.STAGES]
    assert len(ids) == len(set(ids))
    assert ids == ["01", "02", "03", "04a", "04b", "04c", "05", "06", "07", "08", "09", "10", "11", "11b", "12", "13", "14", "15"]


def test_run_pipeline_formats_duration():
    p = load_stage("run_pipeline.py")
    assert p.fmt_duration(45) == "45s"
    assert p.fmt_duration(75) == "1m 15s"


def test_apply_streaming_gridrad_skip_defaults():
    p = load_stage("run_pipeline.py")
    ids = [s[0] for s in p.STAGES]
    f = p.apply_streaming_gridrad_skip_defaults

    assert "04b" in f(set(), only_stage=None, from_stage=None, all_ids=ids)
    assert "04b" not in f({"04c"}, only_stage=None, from_stage=None, all_ids=ids)
    assert "04b" not in f(set(), only_stage="04b", from_stage=None, all_ids=ids)
    assert "04b" in f(set(), only_stage=None, from_stage="04a", all_ids=ids)
    assert "04b" not in f(set(), only_stage=None, from_stage="04b", all_ids=ids)
    assert "04b" not in f(set(), only_stage=None, from_stage="04c", all_ids=ids)
