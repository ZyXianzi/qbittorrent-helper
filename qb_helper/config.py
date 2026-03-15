from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QBittorrentConfig:
    url: str
    username: str
    password: str
    request_timeout: int


@dataclass(frozen=True)
class LoggingConfig:
    file: Path
    level: str
    retention_hours: int
    rotate_when: str
    rotate_interval: int


@dataclass(frozen=True)
class RuntimeConfig:
    state_file: Path
    dry_run: bool


@dataclass(frozen=True)
class ModuleConfig:
    enabled: bool
    options: dict[str, Any]


@dataclass(frozen=True)
class AppConfig:
    qbittorrent: QBittorrentConfig
    logging: LoggingConfig
    runtime: RuntimeConfig
    modules: dict[str, ModuleConfig]


DEFAULT_CONFIG_PATH = Path("./config.json")


def _expect_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _expect_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _expect_int(value: Any, label: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _expect_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    root = _expect_dict(raw, "root")
    qb_section = _expect_dict(root.get("qbittorrent"), "qbittorrent")
    logging_section = _expect_dict(root.get("logging"), "logging")
    runtime_section = _expect_dict(root.get("runtime"), "runtime")
    modules_section = _expect_dict(root.get("modules"), "modules")

    modules: dict[str, ModuleConfig] = {}
    for module_name, module_value in modules_section.items():
        module_section = _expect_dict(module_value, f"modules.{module_name}")
        enabled = _expect_bool(module_section.get("enabled"), f"modules.{module_name}.enabled")
        options = module_section.get("options", {})
        modules[module_name] = ModuleConfig(
            enabled=enabled,
            options=_expect_dict(options, f"modules.{module_name}.options"),
        )

    return AppConfig(
        qbittorrent=QBittorrentConfig(
            url=_expect_str(qb_section.get("url"), "qbittorrent.url"),
            username=_expect_str(qb_section.get("username"), "qbittorrent.username"),
            password=_expect_str(qb_section.get("password"), "qbittorrent.password"),
            request_timeout=_expect_int(
                qb_section.get("request_timeout"),
                "qbittorrent.request_timeout",
            ),
        ),
        logging=LoggingConfig(
            file=Path(_expect_str(logging_section.get("file"), "logging.file")).expanduser(),
            level=_expect_str(logging_section.get("level"), "logging.level").upper(),
            retention_hours=_expect_int(
                logging_section.get("retention_hours"),
                "logging.retention_hours",
            ),
            rotate_when=_expect_str(logging_section.get("rotate_when"), "logging.rotate_when"),
            rotate_interval=_expect_int(
                logging_section.get("rotate_interval"),
                "logging.rotate_interval",
            ),
        ),
        runtime=RuntimeConfig(
            state_file=Path(
                _expect_str(runtime_section.get("state_file"), "runtime.state_file")
            ).expanduser(),
            dry_run=_expect_bool(runtime_section.get("dry_run"), "runtime.dry_run"),
        ),
        modules=modules,
    )
