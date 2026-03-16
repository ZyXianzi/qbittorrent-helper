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
