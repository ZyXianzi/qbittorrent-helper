from __future__ import annotations

from dataclasses import dataclass

from qb_helper.models import Torrent
from qb_helper.modules.base import ModuleContext, ModuleResult


def _bytes_to_gib(value: int) -> float:
    return value / (1024**3)


def _split_tags(raw_tags: str) -> set[str]:
    return {tag.strip() for tag in raw_tags.split(",") if tag.strip()}


@dataclass(frozen=True)
class CandidateTorrent:
    torrent: Torrent
    occupied_bytes: int


class IncompleteSpaceCleanupModule:
    name = "incomplete_space_cleanup"
    _trigger_module = "value_retention_cleanup"

    def run(
        self, context: ModuleContext, previous_state: dict[str, object]
    ) -> ModuleResult:
        del previous_state

        free_space = context.client.get_free_space_on_disk()
        value_retention_runtime = context.module_runtime.get(self._trigger_module, {})
        triggered_by_value_retention = bool(
            value_retention_runtime.get("space_pressure_triggered", False)
        )
        target_free_space_bytes = value_retention_runtime.get("target_free_space_bytes")
        if not isinstance(target_free_space_bytes, int) or target_free_space_bytes <= 0:
            raise RuntimeError(
                "value_retention_cleanup runtime missing target_free_space_bytes"
            )

        if not triggered_by_value_retention:
            context.logger.info(
                "Not triggered: %s did not report disk-pressure cleanup this run",
                self._trigger_module,
            )
            return ModuleResult(state={}, runtime={"deleted_count": 0})

        if free_space >= target_free_space_bytes:
            context.logger.info(
                "Not triggered: free space already meets target | free=%.2f GiB | target=%.2f GiB",
                _bytes_to_gib(free_space),
                _bytes_to_gib(target_free_space_bytes),
            )
            return ModuleResult(state={}, runtime={"deleted_count": 0})

        context.logger.info(
            "Incomplete space cleanup triggered: free=%.2f GiB | target=%.2f GiB",
            _bytes_to_gib(free_space),
            _bytes_to_gib(target_free_space_bytes),
        )

        candidates = sorted(
            (
                candidate
                for torrent in context.torrents
                if (candidate := self._build_candidate(context, torrent)) is not None
            ),
            key=self._sort_key,
        )

        if not candidates:
            context.logger.info(
                "No unprotected incomplete torrents are eligible for emergency cleanup"
            )
            return ModuleResult(state={}, runtime={"deleted_count": 0})

        deleted_count = 0
        dry_run_count = 0
        estimated_free_space = free_space
        for candidate in candidates:
            if estimated_free_space >= target_free_space_bytes:
                break

            torrent = candidate.torrent
            message = (
                "%s | occupied=%.2f GiB | size=%.2f GiB | left=%.2f GiB | progress=%.4f"
            )
            args = (
                torrent.name,
                _bytes_to_gib(candidate.occupied_bytes),
                _bytes_to_gib(torrent.size),
                _bytes_to_gib(torrent.amount_left),
                torrent.progress,
            )

            if context.dry_run:
                context.logger.warning(
                    "[DRY RUN] Would delete incomplete torrent for emergency space recovery: "
                    + message,
                    *args,
                )
                dry_run_count += 1
                estimated_free_space += candidate.occupied_bytes
                continue

            try:
                context.client.delete_torrent(torrent.hash, delete_files=True)
                deleted_count += 1
                estimated_free_space += candidate.occupied_bytes
                context.logger.warning(
                    "Deleted incomplete torrent for emergency space recovery: "
                    + message,
                    *args,
                )
            except Exception as exc:
                context.logger.exception(
                    "Failed to delete incomplete torrent %s during emergency cleanup: %s",
                    torrent.name,
                    exc,
                )

        context.logger.info(
            "Done. deleted=%d | dry_run_deleted=%d | free_before=%.2f GiB | free_after_est=%.2f GiB",
            deleted_count,
            dry_run_count,
            _bytes_to_gib(free_space),
            _bytes_to_gib(estimated_free_space),
        )
        return ModuleResult(
            state={},
            runtime={
                "deleted_count": deleted_count,
                "dry_run_deleted_count": dry_run_count,
                "estimated_free_space_bytes": estimated_free_space,
            },
        )

    def _build_candidate(
        self, context: ModuleContext, torrent: Torrent
    ) -> CandidateTorrent | None:
        if torrent.amount_left <= 0:
            return None

        if self._protected_reason(context, torrent) is not None:
            return None

        occupied_bytes = max(torrent.size - torrent.amount_left, 0)
        if occupied_bytes <= 0:
            return None

        return CandidateTorrent(torrent=torrent, occupied_bytes=occupied_bytes)

    def _protected_reason(self, context: ModuleContext, torrent: Torrent) -> str | None:
        torrent_tags = _split_tags(torrent.tags)
        for tag in context.protection.tags:
            if tag in torrent_tags:
                return f"protected_tag:{tag}"

        for category in context.protection.categories:
            if torrent.category == category:
                return f"protected_category:{category}"

        tracker_text = torrent.tracker.lower()
        for tracker_value in context.protection.tracker_contains:
            if tracker_value.lower() in tracker_text:
                return f"protected_tracker:{tracker_value}"

        return None

    def _sort_key(self, candidate: CandidateTorrent) -> tuple[int, int, int, str]:
        torrent = candidate.torrent
        return (
            -candidate.occupied_bytes,
            -torrent.amount_left,
            -torrent.size,
            torrent.hash,
        )
