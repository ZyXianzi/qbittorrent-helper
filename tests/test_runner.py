from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

from qb_helper import runner
from qb_helper.config import (
    AppConfig,
    LoggingConfig,
    ModuleConfig,
    ProtectionConfig,
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
        protection=ProtectionConfig(tags=(), categories=(), tracker_contains=()),
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
            assert context.protection == ProtectionConfig(
                tags=(), categories=(), tracker_contains=()
            )
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
        protection=ProtectionConfig(tags=(), categories=(), tracker_contains=()),
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


def test_runner_main_passes_prior_module_runtime_to_later_modules(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
        protection=ProtectionConfig(tags=(), categories=(), tracker_contains=()),
        modules={
            "first_module": ModuleConfig(enabled=True, options={}),
            "second_module": ModuleConfig(enabled=True, options={}),
        },
    )

    class FirstModule:
        name = "first_module"

        def __init__(self, options: dict[str, object]) -> None:
            assert options == {}

        def run(self, context, previous_state):  # noqa: ANN001
            assert previous_state == {}
            assert context.module_runtime == {}
            assert context.protection == ProtectionConfig(
                tags=(), categories=(), tracker_contains=()
            )
            return ModuleResult(state={"done": True}, runtime={"flag": "set"})

    class SecondModule:
        name = "second_module"

        def __init__(self, options: dict[str, object]) -> None:
            assert options == {}

        def run(self, context, previous_state):  # noqa: ANN001
            assert previous_state == {}
            assert context.module_runtime == {"first_module": {"flag": "set"}}
            assert context.protection == ProtectionConfig(
                tags=(), categories=(), tracker_contains=()
            )
            return ModuleResult(state={"seen": True})

    monkeypatch.setattr(runner, "load_config", lambda path: config)
    monkeypatch.setattr(runner, "setup_logging", lambda cfg: app_logger)
    monkeypatch.setattr(runner, "load_state", lambda path: {})
    monkeypatch.setattr(runner, "_create_client", lambda cfg: client)
    monkeypatch.setattr(runner, "get_module_logger", lambda logger, name: MagicMock())
    monkeypatch.setattr(runner, "save_state", lambda path, state: None)
    monkeypatch.setattr(
        runner,
        "MODULE_REGISTRY",
        {"first_module": FirstModule, "second_module": SecondModule},
    )

    result = runner.main(["--config", str(tmp_path / "config.toml")])

    assert result == 0


def test_runner_main_runs_incomplete_followup_then_resumes_errors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    call_order: list[str] = []
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
        protection=ProtectionConfig(tags=(), categories=(), tracker_contains=()),
        modules={
            "value_retention_cleanup": ModuleConfig(
                enabled=True, options={"flag": True}
            )
        },
    )

    class FakeValueRetentionModule:
        name = "value_retention_cleanup"

        def __init__(self, options: dict[str, object]) -> None:
            assert options == {"flag": True}

        def run(self, context, previous_state):  # noqa: ANN001
            call_order.append("value")
            assert previous_state == {}
            return ModuleResult(
                state={"done": True},
                runtime={
                    "space_pressure_triggered": True,
                    "target_free_space_bytes": 150,
                    "deleted_count": 1,
                    "resume_error_downloads_after_cleanup": True,
                },
            )

    class FakeIncompleteSpaceCleanupModule:
        name = "incomplete_space_cleanup"

        def run(self, context, previous_state):  # noqa: ANN001
            call_order.append("incomplete")
            assert previous_state == {}
            assert context.module_runtime["value_retention_cleanup"] == {
                "space_pressure_triggered": True,
                "target_free_space_bytes": 150,
                "deleted_count": 1,
                "resume_error_downloads_after_cleanup": True,
            }
            return ModuleResult(state={}, runtime={"deleted_count": 1})

    def fake_resume(context):  # noqa: ANN001
        assert context.module_runtime["incomplete_space_cleanup"] == {
            "deleted_count": 1
        }
        call_order.append("resume")

    monkeypatch.setattr(runner, "load_config", lambda path: config)
    monkeypatch.setattr(runner, "setup_logging", lambda cfg: MagicMock())
    monkeypatch.setattr(runner, "load_state", lambda path: {})
    monkeypatch.setattr(runner, "_create_client", lambda cfg: client)
    monkeypatch.setattr(runner, "get_module_logger", lambda logger, name: MagicMock())
    monkeypatch.setattr(runner, "save_state", lambda path, state: None)
    monkeypatch.setattr(
        runner,
        "MODULE_REGISTRY",
        {"value_retention_cleanup": FakeValueRetentionModule},
    )
    monkeypatch.setattr(
        runner, "IncompleteSpaceCleanupModule", FakeIncompleteSpaceCleanupModule
    )
    monkeypatch.setattr(runner, "resume_error_downloads_after_cleanup", fake_resume)

    result = runner.main(["--config", str(tmp_path / "config.toml")])

    assert result == 0
    assert call_order == ["value", "incomplete", "resume"]
