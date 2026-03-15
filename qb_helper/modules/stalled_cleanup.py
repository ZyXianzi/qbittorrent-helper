from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qb_helper.modules.base import ModuleContext, ModuleResult


def has_tag(existing_tags: str, target_tag: str) -> bool:
    return target_tag in [tag.strip() for tag in existing_tags.split(",") if tag.strip()]


@dataclass(frozen=True)
class StalledCleanupSettings:
    candidate_seconds: int
    delete_seconds: int
    candidate_tag: str

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> "StalledCleanupSettings":
        candidate_seconds = options.get("candidate_seconds")
        delete_seconds = options.get("delete_seconds")
        candidate_tag = options.get("candidate_tag")

        if not isinstance(candidate_seconds, int):
            raise ValueError("modules.stalled_cleanup.options.candidate_seconds must be an integer")
        if not isinstance(delete_seconds, int):
            raise ValueError("modules.stalled_cleanup.options.delete_seconds must be an integer")
        if not isinstance(candidate_tag, str) or not candidate_tag.strip():
            raise ValueError("modules.stalled_cleanup.options.candidate_tag must be a non-empty string")

        return cls(
            candidate_seconds=candidate_seconds,
            delete_seconds=delete_seconds,
            candidate_tag=candidate_tag,
        )


class StalledCleanupModule:
    name = "stalled_cleanup"

    def __init__(self, options: dict[str, Any]) -> None:
        self.settings = StalledCleanupSettings.from_options(options)

    def run(self, context: ModuleContext, previous_state: dict[str, Any]) -> ModuleResult:
        now = context.now
        torrents_by_hash = {torrent.hash: torrent for torrent in context.torrents}
        next_state: dict[str, dict[str, Any]] = {}

        for torrent_hash, old_entry in previous_state.items():
            torrent = torrents_by_hash.get(torrent_hash)
            first_seen_stalled = int(old_entry.get("first_seen_stalled", now))
            last_name = old_entry.get("name", torrent_hash)

            if torrent is None:
                context.logger.info(
                    "Torrent disappeared from qB list; clearing stalled state: %s | previous_stalled=%ss",
                    last_name,
                    now - first_seen_stalled,
                )
                continue

            if torrent.state != "stalledDL":
                context.logger.info(
                    "Recovered from stalledDL: %s | new_state=%s | previous_stalled=%ss",
                    torrent.name,
                    torrent.state,
                    now - first_seen_stalled,
                )
                if has_tag(torrent.tags, self.settings.candidate_tag):
                    self._remove_candidate_tag(context, torrent.hash, torrent.name)
                continue

        for torrent in context.torrents:
            if torrent.state != "stalledDL":
                continue

            old_entry = previous_state.get(torrent.hash)
            if old_entry:
                first_seen_stalled = int(old_entry.get("first_seen_stalled", now))
            else:
                first_seen_stalled = now
                context.logger.info(
                    "First seen stalledDL: %s | progress=%.4f",
                    torrent.name,
                    torrent.progress,
                )

            stalled_duration = now - first_seen_stalled
            context.logger.info(
                "Tracking stalledDL: %s | progress=%.4f | stalled=%ss | state=%s",
                torrent.name,
                torrent.progress,
                stalled_duration,
                torrent.state,
            )

            if (
                stalled_duration >= self.settings.candidate_seconds
                and not has_tag(torrent.tags, self.settings.candidate_tag)
            ):
                self._add_candidate_tag(
                    context,
                    torrent.hash,
                    torrent.name,
                    torrent.progress,
                    stalled_duration,
                )

            if stalled_duration >= self.settings.delete_seconds:
                self._delete_torrent(
                    context,
                    torrent.hash,
                    torrent.name,
                    torrent.progress,
                    stalled_duration,
                )
                continue

            next_state[torrent.hash] = {
                "name": torrent.name,
                "first_seen_stalled": first_seen_stalled,
            }

        context.logger.info("Done. tracked_stalled=%d", len(next_state))
        return ModuleResult(state=next_state)

    def _remove_candidate_tag(self, context: ModuleContext, torrent_hash: str, torrent_name: str) -> None:
        if context.dry_run:
            context.logger.info(
                "[DRY RUN] Would remove tag '%s' from recovered torrent: %s",
                self.settings.candidate_tag,
                torrent_name,
            )
            return

        try:
            context.client.remove_tags(torrent_hash, self.settings.candidate_tag)
            context.logger.info(
                "Removed tag '%s' from recovered torrent: %s",
                self.settings.candidate_tag,
                torrent_name,
            )
        except Exception as exc:
            context.logger.exception("Failed to remove tag from %s: %s", torrent_name, exc)

    def _add_candidate_tag(
        self,
        context: ModuleContext,
        torrent_hash: str,
        torrent_name: str,
        progress: float,
        stalled_duration: int,
    ) -> None:
        if context.dry_run:
            context.logger.info(
                "[DRY RUN] Would add tag '%s': %s | progress=%.4f | stalled=%ss",
                self.settings.candidate_tag,
                torrent_name,
                progress,
                stalled_duration,
            )
            return

        try:
            context.client.add_tags(torrent_hash, self.settings.candidate_tag)
            context.logger.info(
                "Added tag '%s': %s | progress=%.4f | stalled=%ss",
                self.settings.candidate_tag,
                torrent_name,
                progress,
                stalled_duration,
            )
        except Exception as exc:
            context.logger.exception("Failed to add tag for %s: %s", torrent_name, exc)

    def _delete_torrent(
        self,
        context: ModuleContext,
        torrent_hash: str,
        torrent_name: str,
        progress: float,
        stalled_duration: int,
    ) -> None:
        if context.dry_run:
            context.logger.warning(
                "[DRY RUN] Would delete torrent and files: %s | progress=%.4f | stalled=%ss",
                torrent_name,
                progress,
                stalled_duration,
            )
            return

        try:
            context.client.delete_torrent(torrent_hash, delete_files=True)
            context.logger.warning(
                "Deleted torrent and files: %s | progress=%.4f | stalled=%ss",
                torrent_name,
                progress,
                stalled_duration,
            )
        except Exception as exc:
            context.logger.exception("Failed to delete torrent %s: %s", torrent_name, exc)
