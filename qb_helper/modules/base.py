from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from qb_helper.client import QBittorrentClient
from qb_helper.models import Torrent


@dataclass(frozen=True)
class ModuleContext:
    client: QBittorrentClient
    torrents: list[Torrent]
    dry_run: bool
    logger: logging.LoggerAdapter
    now: int


@dataclass(frozen=True)
class ModuleResult:
    state: dict[str, Any]


class HelperModule(Protocol):
    name: str

    def run(
        self, context: ModuleContext, previous_state: dict[str, Any]
    ) -> ModuleResult: ...
