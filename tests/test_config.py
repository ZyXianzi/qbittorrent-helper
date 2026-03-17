from __future__ import annotations

from pathlib import Path

import pytest

from qb_helper.config import load_config


def test_load_config_parses_expected_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[qbittorrent]
url = "http://127.0.0.1:8080"
username = "admin"
password = "secret"
request_timeout = 15

[logging]
file = "./logs/qb-helper.log"
level = "info"
retention_hours = 24
rotate_when = "H"
rotate_interval = 1

[runtime]
state_file = "./data/state.json"
dry_run = true

[modules.stalled_cleanup]
enabled = true

[modules.stalled_cleanup.options]
candidate_seconds = 300
delete_seconds = 600
candidate_tag = "stalled-long"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.qbittorrent.url == "http://127.0.0.1:8080"
    assert config.logging.file == Path("./logs/qb-helper.log")
    assert config.logging.level == "INFO"
    assert config.runtime.state_file == Path("./data/state.json")
    assert config.runtime.dry_run is True
    assert config.modules["stalled_cleanup"].enabled is True
    assert config.modules["stalled_cleanup"].options == {
        "candidate_seconds": 300,
        "delete_seconds": 600,
        "candidate_tag": "stalled-long",
    }


def test_load_config_rejects_non_boolean_module_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[qbittorrent]
url = "http://127.0.0.1:8080"
username = "admin"
password = "secret"
request_timeout = 15

[logging]
file = "./logs/qb-helper.log"
level = "INFO"
retention_hours = 24
rotate_when = "H"
rotate_interval = 1

[runtime]
state_file = "./data/state.json"
dry_run = true

[modules.stalled_cleanup]
enabled = "yes"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match=r"modules\.stalled_cleanup\.enabled must be a boolean"
    ):
        load_config(config_path)


def test_load_config_preserves_nested_value_retention_options(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[qbittorrent]
url = "http://127.0.0.1:8080"
username = "admin"
password = "secret"
request_timeout = 15

[logging]
file = "./logs/qb-helper.log"
level = "INFO"
retention_hours = 24
rotate_when = "H"
rotate_interval = 1

[runtime]
state_file = "./data/state.json"
dry_run = true

[modules.value_retention_cleanup]
enabled = true

[modules.value_retention_cleanup.options]
min_free_space_gb = 80
target_free_space_gb = 150
max_deletions_per_run = 4
history_hours = 48
recent_window_hours = 6
long_window_hours = 24
delete_low_value_after_base_seed = true
resume_error_downloads_after_cleanup = true
protected_tags = ["manual-keep"]
protected_categories = ["do-not-delete"]
protected_tracker_contains = []

[modules.value_retention_cleanup.options.score_weights]
recent_upload_per_gib = 4.0
long_upload_per_gib = 2.0
current_upspeed_mib = 0.3
idle_hours = 0.5
size_root = 0.4

[modules.value_retention_cleanup.options.default_policy]
name = "default"
priority = 0.0
base_seed_hours = 12
max_seed_hours = 24
min_score_to_keep = 1.0

[[modules.value_retention_cleanup.options.policies]]
name = "adult-large"
match_categories = ["adult"]
min_size_gb = 50
priority = 6.0
base_seed_hours = 24
max_seed_hours = 72
min_score_to_keep = 1.5
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.modules["value_retention_cleanup"].enabled is True
    assert (
        config.modules["value_retention_cleanup"].options["target_free_space_gb"] == 150
    )
    assert config.modules["value_retention_cleanup"].options["score_weights"] == {
        "recent_upload_per_gib": 4.0,
        "long_upload_per_gib": 2.0,
        "current_upspeed_mib": 0.3,
        "idle_hours": 0.5,
        "size_root": 0.4,
    }
    assert config.modules["value_retention_cleanup"].options["policies"] == [
        {
            "name": "adult-large",
            "match_categories": ["adult"],
            "min_size_gb": 50,
            "priority": 6.0,
            "base_seed_hours": 24,
            "max_seed_hours": 72,
            "min_score_to_keep": 1.5,
        }
    ]
