from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qb_helper.models import Torrent
from qb_helper.modules.base import ModuleContext, ModuleResult


def _bytes_to_gib(value: int) -> float:
    return value / (1024**3)


def _is_seed_candidate(torrent: Torrent) -> bool:
    return torrent.progress >= 1.0 and torrent.amount_left == 0


@dataclass(frozen=True)
class DiskSpaceCleanupSettings:
    min_free_space_gb: int

    @property
    def min_free_space_bytes(self) -> int:
        return self.min_free_space_gb * 1024**3

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> "DiskSpaceCleanupSettings":
        min_free_space_gb = options.get("min_free_space_gb")
        if not isinstance(min_free_space_gb, int) or min_free_space_gb <= 0:
            raise ValueError(
                "modules.disk_space_cleanup.options.min_free_space_gb must be a positive integer"
            )
        return cls(min_free_space_gb=min_free_space_gb)


class DiskSpaceCleanupModule:
    name = "disk_space_cleanup"

    def __init__(self, options: dict[str, Any]) -> None:
        self.settings = DiskSpaceCleanupSettings.from_options(options)

    def run(
        self, context: ModuleContext, previous_state: dict[str, Any]
    ) -> ModuleResult:
        del previous_state

        free_space = context.client.get_free_space_on_disk()
        context.logger.info(
            "Disk space check: free=%.2f GiB | threshold=%d GiB",
            _bytes_to_gib(free_space),
            self.settings.min_free_space_gb,
        )

        if free_space >= self.settings.min_free_space_bytes:
            return ModuleResult(state={})

        candidate = self._pick_largest_seed_torrent(context.torrents)
        if candidate is None:
            context.logger.warning(
                "Disk space below threshold but no completed seeding torrent is available to delete"
            )
            return ModuleResult(state={})

        if context.dry_run:
            context.logger.warning(
                "[DRY RUN] Would delete largest completed torrent to free space: %s | size=%.2f GiB | free=%.2f GiB",
                candidate.name,
                _bytes_to_gib(candidate.size),
                _bytes_to_gib(free_space),
            )
            return ModuleResult(state={})

        try:
            context.client.delete_torrent(candidate.hash, delete_files=True)
            context.logger.warning(
                "Deleted largest completed torrent to free space: %s | size=%.2f GiB | free_before=%.2f GiB",
                candidate.name,
                _bytes_to_gib(candidate.size),
                _bytes_to_gib(free_space),
            )
        except Exception as exc:
            context.logger.exception(
                "Failed to delete torrent %s while freeing disk space: %s",
                candidate.name,
                exc,
            )
            return ModuleResult(state={})

        self._resume_error_downloads(context)
        return ModuleResult(state={})

    def _pick_largest_seed_torrent(self, torrents: list[Torrent]) -> Torrent | None:
        candidates = [torrent for torrent in torrents if _is_seed_candidate(torrent)]
        if not candidates:
            return None
        return max(candidates, key=lambda torrent: (torrent.size, torrent.added_on))

    def _resume_error_downloads(self, context: ModuleContext) -> None:
        try:
            refreshed_torrents = context.client.get_torrents()
        except Exception as exc:
            context.logger.exception(
                "Failed to refresh torrents after disk cleanup: %s", exc
            )
            return

        error_downloads = [
            torrent
            for torrent in refreshed_torrents
            if torrent.state == "error" and torrent.amount_left > 0
        ]
        if not error_downloads:
            context.logger.info("No errored downloads found after disk cleanup")
            return

        hashes = [torrent.hash for torrent in error_downloads]
        names = ", ".join(torrent.name for torrent in error_downloads)
        try:
            context.client.start_torrents(hashes)
            context.logger.info(
                "Resumed errored downloads after disk cleanup: count=%d | torrents=%s",
                len(error_downloads),
                names,
            )
        except Exception as exc:
            context.logger.exception(
                "Failed to resume errored downloads after disk cleanup: %s", exc
            )
