"""Tests for hail_aws.config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hail_aws.config import (
    ConfigError,
    default_config_path,
    load_pipeline_config,
    validate_ephemeral,
    validate_fargate_size,
)


def test_load_default_pipeline_yaml(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    assert cfg.project_name == "us-hail-cat-model"
    assert cfg.version == "2.3.0"
    assert set(cfg.parallel_downloads) == {
        "download_myrorss",
        "download_mrms",
        "download_gridrad",
    }
    assert cfg.finalize_task == "finalize"
    assert cfg.tasks["download_gridrad"].cpu == 2048
    assert cfg.tasks["download_gridrad"].memory == 16384
    assert cfg.gridrad_fanout.enabled is True
    assert cfg.gridrad_fanout.max_concurrent == 10
    assert cfg.image_uri_suffix == "hail-cat-model:2.3.0"


def test_default_config_path_exists() -> None:
    assert default_config_path().is_file()


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_pipeline_config(tmp_path / "missing.yaml")


def test_root_must_be_mapping(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- not a map\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="root must be a mapping"):
        load_pipeline_config(p)


def test_invalid_fargate_cpu() -> None:
    with pytest.raises(ConfigError, match="not a valid Fargate CPU"):
        validate_fargate_size(999, 2048, "t")


def test_invalid_fargate_memory() -> None:
    with pytest.raises(ConfigError, match="memory="):
        validate_fargate_size(4096, 1000, "t")


def test_ephemeral_bounds() -> None:
    validate_ephemeral(20, "t")
    validate_ephemeral(200, "t")
    with pytest.raises(ConfigError, match="ephemeral"):
        validate_ephemeral(19, "t")
    with pytest.raises(ConfigError, match="ephemeral"):
        validate_ephemeral(201, "t")


def _mutate(minimal_yaml: Path, mutator) -> Path:
    data = yaml.safe_load(minimal_yaml.read_text(encoding="utf-8"))
    mutator(data)
    minimal_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    return minimal_yaml


def test_missing_project_key(minimal_yaml: Path) -> None:
    def mut(d):
        del d["project"]["name"]

    with pytest.raises(ConfigError, match="Missing required key 'name'"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_bad_tags(minimal_yaml: Path) -> None:
    def mut(d):
        d["project"]["tags"] = {"x": 1}

    with pytest.raises(ConfigError, match="tags"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_unknown_parallel_task(minimal_yaml: Path) -> None:
    def mut(d):
        d["workflow"]["parallel_downloads"] = ["nope"]

    with pytest.raises(ConfigError, match="unknown task"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_unknown_finalize_task(minimal_yaml: Path) -> None:
    def mut(d):
        d["workflow"]["finalize_task"] = "nope"

    with pytest.raises(ConfigError, match="finalize_task"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_bad_command(minimal_yaml: Path) -> None:
    def mut(d):
        d["tasks"]["finalize"]["command"] = []

    with pytest.raises(ConfigError, match="command"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_bad_cpu_type(minimal_yaml: Path) -> None:
    def mut(d):
        d["tasks"]["finalize"]["cpu"] = "4096"

    with pytest.raises(ConfigError, match="must be an int"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_vpc_and_secrets_optional_strings(minimal_yaml: Path) -> None:
    def mut(d):
        d["network"]["vpc_id"] = "vpc-123"
        d["network"]["subnet_ids"] = ["subnet-a"]
        d["secrets"]["cdsapi_secret_arn"] = "arn:aws:secretsmanager:us-east-1:1:secret:cds"
        d["secrets"]["ncar_rda_secret_arn"] = "arn:aws:secretsmanager:us-east-1:1:secret:ncar"

    cfg = load_pipeline_config(_mutate(minimal_yaml, mut))
    assert cfg.vpc_id == "vpc-123"
    assert cfg.subnet_ids == ["subnet-a"]
    assert cfg.cdsapi_secret_arn.endswith("cds")
    assert cfg.ncar_rda_secret_arn.endswith("ncar")


def test_assign_public_ip_must_be_bool(minimal_yaml: Path) -> None:
    def mut(d):
        d["network"]["assign_public_ip"] = "yes"

    with pytest.raises(ConfigError, match="assign_public_ip"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_empty_project_name(minimal_yaml: Path) -> None:
    def mut(d):
        d["project"]["name"] = "  "

    with pytest.raises(ConfigError, match="non-empty string"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_tasks_must_be_mapping(minimal_yaml: Path) -> None:
    def mut(d):
        d["tasks"] = []

    with pytest.raises(ConfigError, match="tasks must be a non-empty mapping"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_task_body_must_be_mapping(minimal_yaml: Path) -> None:
    def mut(d):
        d["tasks"]["finalize"] = "nope"

    with pytest.raises(ConfigError, match="must be a mapping"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_invalid_memory_in_yaml(minimal_yaml: Path) -> None:
    def mut(d):
        d["tasks"]["finalize"]["memory"] = 1000

    with pytest.raises(ConfigError, match="memory="):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_section_type_checks(minimal_yaml: Path) -> None:
    for section in ("project", "image", "network", "storage", "ecs", "workflow"):
        data = yaml.safe_load(minimal_yaml.read_text(encoding="utf-8"))
        data[section] = []
        p = minimal_yaml.parent / f"bad_{section}.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_pipeline_config(p)


def test_secrets_must_be_mapping(minimal_yaml: Path) -> None:
    def mut(d):
        d["secrets"] = []

    with pytest.raises(ConfigError, match="secrets must be a mapping"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_subnet_ids_type(minimal_yaml: Path) -> None:
    def mut(d):
        d["network"]["subnet_ids"] = [1]

    with pytest.raises(ConfigError, match="subnet_ids"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_parallel_downloads_type(minimal_yaml: Path) -> None:
    def mut(d):
        d["workflow"]["parallel_downloads"] = "x"

    with pytest.raises(ConfigError, match="list of non-empty strings"):
        load_pipeline_config(_mutate(minimal_yaml, mut))


def test_gridrad_fanout_validation(minimal_yaml: Path, config_path: Path) -> None:
    def fresh() -> dict:
        return yaml.safe_load(config_path.read_text(encoding="utf-8"))

    def write(data: dict) -> Path:
        minimal_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
        return minimal_yaml

    data = fresh()
    data["workflow"]["gridrad_fanout"] = {
        "enabled": True,
        "task": "nope",
        "max_concurrent": 2,
    }
    with pytest.raises(ConfigError, match="unknown task"):
        load_pipeline_config(write(data))

    data = fresh()
    data["workflow"]["parallel_downloads"] = ["download_myrorss", "download_mrms"]
    data["workflow"]["gridrad_fanout"] = {
        "enabled": True,
        "task": "download_gridrad",
        "max_concurrent": 2,
    }
    with pytest.raises(ConfigError, match="parallel_downloads"):
        load_pipeline_config(write(data))

    data = fresh()
    data["workflow"]["gridrad_fanout"]["from_date"] = "not-a-date"
    with pytest.raises(ConfigError, match="YYYY-MM-DD"):
        load_pipeline_config(write(data))

    data = fresh()
    data["workflow"]["gridrad_fanout"]["from_date"] = "2015-05-21"
    data["workflow"]["gridrad_fanout"]["until_date"] = "2015-05-20"
    with pytest.raises(ConfigError, match="until_date"):
        load_pipeline_config(write(data))

    data = fresh()
    data["workflow"]["gridrad_fanout"]["max_concurrent"] = 0
    with pytest.raises(ConfigError, match="max_concurrent"):
        load_pipeline_config(write(data))

    data = fresh()
    data["workflow"]["gridrad_fanout"] = []
    with pytest.raises(ConfigError, match="gridrad_fanout must be a mapping"):
        load_pipeline_config(write(data))

    data = fresh()
    data["workflow"]["gridrad_fanout"]["from_date"] = "1999-01-01"
    with pytest.raises(ConfigError, match="within"):
        load_pipeline_config(write(data))


def test_gridrad_fanout_defaults_when_absent(minimal_yaml: Path) -> None:
    def mut(d):
        d["workflow"].pop("gridrad_fanout", None)

    cfg = load_pipeline_config(_mutate(minimal_yaml, mut))
    assert cfg.gridrad_fanout.enabled is False


def test_gridrad_fanout_empty_string_date(minimal_yaml: Path, config_path: Path) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["workflow"]["gridrad_fanout"]["from_date"] = "   "
    minimal_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="YYYY-MM-DD or null"):
        load_pipeline_config(minimal_yaml)


def test_gridrad_fanout_bad_workers(minimal_yaml: Path, config_path: Path) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["workflow"]["gridrad_fanout"]["workers"] = 0
    minimal_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="workers must be >= 1"):
        load_pipeline_config(minimal_yaml)


def test_gridrad_fanout_until_out_of_gap(minimal_yaml: Path, config_path: Path) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["workflow"]["gridrad_fanout"]["until_date"] = "2025-01-01"
    minimal_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="within"):
        load_pipeline_config(minimal_yaml)
