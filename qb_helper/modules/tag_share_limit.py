from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qb_helper.modules.base import ModuleContext, ModuleResult


def _split_tags(raw_tags: str) -> set[str]:
    return {tag.strip() for tag in raw_tags.split(",") if tag.strip()}


@dataclass(frozen=True)
class TagShareLimitSettings:
    tag_seeding_time_limit_minutes: dict[str, int]

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> TagShareLimitSettings:
        raw_mapping = options.get("tag_seeding_time_limit_minutes")
        if not isinstance(raw_mapping, dict) or not raw_mapping:
            raise ValueError(
                "modules.tag_share_limit.options.tag_seeding_time_limit_minutes must be a non-empty mapping"
            )

        mapping: dict[str, int] = {}
        for raw_tag, raw_minutes in raw_mapping.items():
            if not isinstance(raw_tag, str) or not raw_tag.strip():
                raise ValueError(
                    "modules.tag_share_limit.options.tag_seeding_time_limit_minutes keys must be non-empty strings"
                )
            if not isinstance(raw_minutes, int) or raw_minutes < -2:
                raise ValueError(
                    "modules.tag_share_limit.options.tag_seeding_time_limit_minutes values must be integers >= -2"
                )
            mapping[raw_tag.strip()] = raw_minutes

        return cls(tag_seeding_time_limit_minutes=mapping)


class TagShareLimitModule:
    name = "tag_share_limit"

    def __init__(self, options: dict[str, Any]) -> None:
        self.settings = TagShareLimitSettings.from_options(options)

    def run(
        self, context: ModuleContext, previous_state: dict[str, Any]
    ) -> ModuleResult:
        del previous_state

        updated_count = 0
        dry_run_count = 0
        for torrent in context.torrents:
            matched_tags = self._matching_tags(torrent.tags)
            if not matched_tags:
                continue

            matched_tag, desired_minutes = min(
                (
                    (tag, self.settings.tag_seeding_time_limit_minutes[tag])
                    for tag in matched_tags
                ),
                key=lambda item: item[1],
            )
            if len(matched_tags) > 1:
                context.logger.info(
                    "Multiple tag share-limit rules matched; using shortest limit: %s | matched_tags=%s | chosen_tag=%s | chosen_limit=%d",
                    torrent.name,
                    ",".join(matched_tags),
                    matched_tag,
                    desired_minutes,
                )
            if torrent.seeding_time_limit == desired_minutes:
                context.logger.info(
                    "Share limit already matches tag rule: %s | tag=%s | seeding_time_limit=%d",
                    torrent.name,
                    matched_tag,
                    desired_minutes,
                )
                continue

            outcome = self._apply_seeding_time_limit(
                context=context,
                torrent_hash=torrent.hash,
                torrent_name=torrent.name,
                matched_tag=matched_tag,
                current_minutes=torrent.seeding_time_limit,
                desired_minutes=desired_minutes,
            )
            if outcome == "updated":
                updated_count += 1
            elif outcome == "dry_run":
                dry_run_count += 1

        context.logger.info(
            "Done. updated_share_limits=%d | dry_run_share_limits=%d",
            updated_count,
            dry_run_count,
        )
        return ModuleResult(state={})

    def _matching_tags(self, raw_tags: str) -> list[str]:
        torrent_tags = _split_tags(raw_tags)
        return [
            tag
            for tag in self.settings.tag_seeding_time_limit_minutes
            if tag in torrent_tags
        ]

    def _apply_seeding_time_limit(
        self,
        context: ModuleContext,
        torrent_hash: str,
        torrent_name: str,
        matched_tag: str,
        current_minutes: int,
        desired_minutes: int,
    ) -> str:
        if context.dry_run:
            context.logger.info(
                "[DRY RUN] Would set seeding time limit: %s | tag=%s | current=%d | desired=%d",
                torrent_name,
                matched_tag,
                current_minutes,
                desired_minutes,
            )
            return "dry_run"

        try:
            context.client.set_seeding_time_limit(torrent_hash, desired_minutes)
            context.logger.info(
                "Set seeding time limit: %s | tag=%s | previous=%d | new=%d",
                torrent_name,
                matched_tag,
                current_minutes,
                desired_minutes,
            )
            return "updated"
        except Exception as exc:
            context.logger.exception(
                "Failed to set seeding time limit for %s: %s", torrent_name, exc
            )
            return "failed"
