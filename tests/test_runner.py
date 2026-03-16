from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

from qb_helper import runner
from qb_helper.config import (
    AppConfig,
    LoggingConfig,
    ModuleConfig,
    QBittorrentConfig,
    RuntimeConfig,
)
from qb_helper.modules.base import ModuleResult


def test_runner_main_executes_enabled_modules_and_saves_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    saved: dict[str, object] = {}
    module_logger = MagicMock()
    app_logger = MagicMock()
    client = MagicMock()
    client.get_torrents.return_value = []
    config = AppConfig(
        qbittorrent=QBittorrentConfig(
            url="http://127.0.0.1:8080",
            username="admin",
            password="secret",
            request_timeout=15,
        ),
        logging=LoggingConfig(
            file=tmp_path / "qb-helper.log",
            level="INFO",
            retention_hours=24,
            rotate_when="H",
            rotate_interval=1,
        ),
        runtime=RuntimeConfig(state_file=tmp_path / "state.json", dry_run=False),
        modules={"fake_module": ModuleConfig(enabled=True, options={"flag": True})},
    )

    class FakeModule:
        name = "fake_module"

        def __init__(self, options: dict[str, object]) -> None:
            assert options == {"flag": True}

        def run(self, context, previous_state):  # noqa: ANN001
            assert context.client is client
            assert context.torrents == []
            assert context.dry_run is False
            assert context.now > 0
            assert context.logger is module_logger
            assert previous_state == {"seen": True}
            return ModuleResult(state={"done": True})

    monkeypatch.setattr(runner, "load_config", lambda path: config)
    monkeypatch.setattr(runner, "setup_logging", lambda cfg: app_logger)
    monkeypatch.setattr(
        runner, "load_state", lambda path: {"fake_module": {"seen": True}}
    )
    monkeypatch.setattr(runner, "_create_client", lambda cfg: client)
    monkeypatch.setattr(runner, "get_module_logger", lambda logger, name: module_logger)
    monkeypatch.setattr(
        runner,
        "save_state",
        lambda path, state: saved.update({"path": path, "state": state}),
    )
    monkeypatch.setattr(runner, "MODULE_REGISTRY", {"fake_module": FakeModule})

    result = runner.main(["--config", str(tmp_path / "config.toml")])

    assert result == 0
    client.login.assert_called_once_with()
    client.get_torrents.assert_called_once_with()
    assert saved == {
        "path": tmp_path / "state.json",
        "state": {"fake_module": {"done": True}},
    }


def test_runner_main_returns_error_when_config_load_fails(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runner,
        "load_config",
        lambda path: (_ for _ in ()).throw(ValueError("bad config")),
    )

    result = runner.main(["--config", str(tmp_path / "config.toml")])

    assert result == 1
    captured = capsys.readouterr()
    assert "Failed to load config" in captured.err
    assert "bad config" in captured.err


def test_runner_main_marks_unknown_modules_as_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    saved: dict[str, object] = {}
    app_logger = logging.getLogger("tests.runner")
    client = MagicMock()
    client.get_torrents.return_value = []
    config = AppConfig(
        qbittorrent=QBittorrentConfig(
            url="http://127.0.0.1:8080",
            username="admin",
            password="secret",
            request_timeout=15,
        ),
        logging=LoggingConfig(
            file=tmp_path / "qb-helper.log",
            level="INFO",
            retention_hours=24,
            rotate_when="H",
            rotate_interval=1,
        ),
        runtime=RuntimeConfig(state_file=tmp_path / "state.json", dry_run=False),
        modules={"missing_module": ModuleConfig(enabled=True, options={})},
    )

    monkeypatch.setattr(runner, "load_config", lambda path: config)
    monkeypatch.setattr(runner, "setup_logging", lambda cfg: app_logger)
    monkeypatch.setattr(runner, "load_state", lambda path: {})
    monkeypatch.setattr(runner, "_create_client", lambda cfg: client)
    monkeypatch.setattr(
        runner,
        "save_state",
        lambda path, state: saved.update({"path": path, "state": state}),
    )
    monkeypatch.setattr(runner, "MODULE_REGISTRY", {})

    result = runner.main(["--config", str(tmp_path / "config.toml")])

    assert result == 1
    assert saved == {"path": tmp_path / "state.json", "state": {}}
