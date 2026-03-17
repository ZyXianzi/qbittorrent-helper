from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, Unpack
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if TYPE_CHECKING:
    from qb_helper.models import Torrent
    from qb_helper.modules.base import ModuleContext


class TorrentOverrides(TypedDict, total=False):
    hash: str
    name: str
    state: str
    progress: float
    added_on: int
    completion_on: int
    last_activity: int
    size: int
    amount_left: int
    uploaded: int
    upspeed: int
    ratio: float
    seeding_time: int
    tags: str
    category: str
    tracker: str
    seeding_time_limit: int


@pytest.fixture
def make_torrent() -> Callable[..., Torrent]:
    def _make_torrent(**overrides: Unpack[TorrentOverrides]) -> Torrent:
        from qb_helper.models import Torrent

        values: TorrentOverrides = {
            "hash": "torrent-hash",
            "name": "Example Torrent",
            "state": "downloading",
            "progress": 0.5,
            "added_on": 1,
            "completion_on": 0,
            "last_activity": 0,
            "size": 1024,
            "amount_left": 512,
            "uploaded": 0,
            "upspeed": 0,
            "ratio": 0.0,
            "seeding_time": 0,
            "tags": "",
            "category": "",
            "tracker": "",
            "seeding_time_limit": -2,
        }
        values.update(overrides)
        return Torrent(**values)

    return _make_torrent


@pytest.fixture
def make_context() -> Callable[..., ModuleContext]:
    def _make_context(
        *,
        client: MagicMock | None = None,
        torrents: list[Torrent] | None = None,
        dry_run: bool = False,
        now: int = 1_000,
        module_name: str = "test_module",
    ) -> ModuleContext:
        from qb_helper.modules.base import ModuleContext

        logger = logging.getLogger(f"tests.{module_name}")
        logger.setLevel(logging.INFO)
        return ModuleContext(
            client=client or MagicMock(),
            torrents=torrents or [],
            dry_run=dry_run,
            logger=logging.LoggerAdapter(logger, {"module_name": module_name}),
            now=now,
        )

    return _make_context
