from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

from qb_helper.client import QBittorrentClient
from qb_helper.config import DEFAULT_CONFIG_PATH, AppConfig, load_config
from qb_helper.logging_utils import get_module_logger, setup_logging
from qb_helper.modules import MODULE_REGISTRY
from qb_helper.modules.base import ModuleContext
from qb_helper.state import load_state, save_state


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="qBittorrent helper")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to TOML config file",
    )
    return parser.parse_args(argv)


def _load_state_or_empty(path: Path, logger: logging.Logger) -> dict[str, Any]:
    try:
        return load_state(path)
    except Exception as exc:
        logger.warning("Failed to load state file %s: %s. Resetting state.", path, exc)
        return {}


def _create_client(config: AppConfig) -> QBittorrentClient:
    return QBittorrentClient(
        base_url=config.qbittorrent.url,
        username=config.qbittorrent.username,
        password=config.qbittorrent.password,
        timeout=config.qbittorrent.request_timeout,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Failed to load config {args.config}: {exc}", file=sys.stderr)
        return 1

    logger = setup_logging(config.logging)
    logger.info("Loaded config from %s", args.config)

    state = _load_state_or_empty(config.runtime.state_file, logger)
    client = _create_client(config)

    try:
        client.login()
        torrents = client.get_torrents()
    except Exception as exc:
        logger.exception("Failed to communicate with qBittorrent: %s", exc)
        return 1

    next_state: dict[str, Any] = {}
    now = int(time.time())
    failed_modules = False

    for module_name, module_config in config.modules.items():
        if not module_config.enabled:
            logger.info(
                "Module disabled: %s", module_name, extra={"module_name": module_name}
            )
            continue

        module_class = MODULE_REGISTRY.get(module_name)
        if module_class is None:
            logger.warning(
                "Unknown module in config: %s",
                module_name,
                extra={"module_name": module_name},
            )
            failed_modules = True
            continue

        module_logger = get_module_logger(logger, module_name)
        module_state = state.get(module_name, {})
        if not isinstance(module_state, dict):
            module_logger.warning("Invalid module state type. Resetting state.")
            module_state = {}

        try:
            module = module_class(module_config.options)
            result = module.run(
                ModuleContext(
                    client=client,
                    torrents=torrents,
                    dry_run=config.runtime.dry_run,
                    logger=module_logger,
                    now=now,
                ),
                module_state,
            )
            next_state[module_name] = result.state
        except Exception as exc:
            module_logger.exception("Module execution failed: %s", exc)
            failed_modules = True

    try:
        save_state(config.runtime.state_file, next_state)
    except Exception as exc:
        logger.exception("Failed to save state: %s", exc)
        return 1

    logger.info("Finished helper run. active_modules=%d", len(next_state))
    return 1 if failed_modules else 0
