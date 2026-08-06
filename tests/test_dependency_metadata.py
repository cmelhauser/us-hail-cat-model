from pathlib import Path


def test_grib_readers_are_runtime_dependencies():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project_dependencies = pyproject.read_text().split(
        "dependencies = [", 1
    )[1].split("]", 1)[0]
    assert '"cfgrib>=0.9.10"' in project_dependencies
    assert '"eccodes>=1.5"' in project_dependencies
