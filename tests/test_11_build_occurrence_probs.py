from conftest import load_stage


def test_stage11_thresholds_are_increasing():
    s = load_stage("11_build_occurrence_probs.py")
    mm = [x * s.MM_PER_IN for x in s.THRESHOLDS_IN]
    assert all(b > a for a, b in zip(mm, mm[1:]))
