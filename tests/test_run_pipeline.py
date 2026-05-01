from conftest import load_stage


def test_run_pipeline_stage_ids_are_unique_and_complete():
    p = load_stage("run_pipeline.py")
    ids = [s[0] for s in p.STAGES]
    assert len(ids) == len(set(ids))
    assert ids == ["01", "02", "03", "04a", "04b", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15"]


def test_run_pipeline_formats_duration():
    p = load_stage("run_pipeline.py")
    assert p.fmt_duration(45) == "45s"
    assert p.fmt_duration(75) == "1m 15s"
