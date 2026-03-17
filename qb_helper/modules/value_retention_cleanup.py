from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from qb_helper.models import Torrent
from qb_helper.modules.base import ModuleContext, ModuleResult


def _bytes_to_gib(value: int) -> float:
    return value / (1024**3)


def _bytes_to_mib(value: int) -> float:
    return value / (1024**2)


def _is_seed_candidate(torrent: Torrent) -> bool:
    return torrent.progress >= 1.0 and torrent.amount_left == 0


def _split_tags(raw_tags: str) -> set[str]:
    return {tag.strip() for tag in raw_tags.split(",") if tag.strip()}


def _expect_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _expect_int(value: Any, label: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _expect_positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _expect_non_negative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be an integer >= 0")
    return value


def _expect_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a number")
    return float(value)


def _expect_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _expect_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _expect_string_list(value: Any, label: str) -> tuple[str, ...]:
    items = _expect_list(value, label)
    cleaned: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label}[{index}] must be a non-empty string")
        cleaned.append(item.strip())
    return tuple(cleaned)


def _optional_positive_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _expect_positive_int(value, label)


def _optional_non_negative_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    parsed = _expect_number(value, label)
    if parsed < 0:
        raise ValueError(f"{label} must be >= 0")
    return parsed


def _serialize_samples(samples: list[UploadSample]) -> list[dict[str, int]]:
    return [{"ts": sample.ts, "uploaded": sample.uploaded} for sample in samples]


@dataclass(frozen=True)
class UploadSample:
    ts: int
    uploaded: int


@dataclass(frozen=True)
class ScoreWeights:
    recent_upload_per_gib: float
    long_upload_per_gib: float
    current_upspeed_mib: float
    idle_hours: float
    size_root: float

    @classmethod
    def from_options(cls, raw: dict[str, Any]) -> ScoreWeights:
        return cls(
            recent_upload_per_gib=_expect_number(
                raw.get("recent_upload_per_gib"),
                "modules.value_retention_cleanup.options.score_weights.recent_upload_per_gib",
            ),
            long_upload_per_gib=_expect_number(
                raw.get("long_upload_per_gib"),
                "modules.value_retention_cleanup.options.score_weights.long_upload_per_gib",
            ),
            current_upspeed_mib=_expect_number(
                raw.get("current_upspeed_mib"),
                "modules.value_retention_cleanup.options.score_weights.current_upspeed_mib",
            ),
            idle_hours=_expect_number(
                raw.get("idle_hours"),
                "modules.value_retention_cleanup.options.score_weights.idle_hours",
            ),
            size_root=_expect_number(
                raw.get("size_root"),
                "modules.value_retention_cleanup.options.score_weights.size_root",
            ),
        )


@dataclass(frozen=True)
class RetentionPolicy:
    name: str
    priority: float
    base_seed_hours: int
    max_seed_hours: int | None
    min_score_to_keep: float
    match_categories: tuple[str, ...]
    match_tags: tuple[str, ...]
    tracker_contains: tuple[str, ...]
    min_size_gb: float | None
    max_size_gb: float | None

    @classmethod
    def from_options(
        cls, raw: dict[str, Any], label: str, *, require_matchers: bool
    ) -> RetentionPolicy:
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label}.name must be a non-empty string")

        base_seed_hours = _expect_positive_int(
            raw.get("base_seed_hours"), f"{label}.base_seed_hours"
        )
        max_seed_hours = _optional_positive_int(
            raw.get("max_seed_hours"), f"{label}.max_seed_hours"
        )
        if max_seed_hours is not None and max_seed_hours < base_seed_hours:
            raise ValueError(
                f"{label}.max_seed_hours must be >= {label}.base_seed_hours"
            )

        match_categories = _expect_string_list(
            raw.get("match_categories", []), f"{label}.match_categories"
        )
        match_tags = _expect_string_list(
            raw.get("match_tags", []), f"{label}.match_tags"
        )
        tracker_contains = _expect_string_list(
            raw.get("tracker_contains", []), f"{label}.tracker_contains"
        )
        if require_matchers and not (
            match_categories
            or match_tags
            or tracker_contains
            or raw.get("min_size_gb") is not None
            or raw.get("max_size_gb") is not None
        ):
            raise ValueError(f"{label} must define at least one matcher")

        min_size_gb = _optional_non_negative_number(
            raw.get("min_size_gb"), f"{label}.min_size_gb"
        )
        max_size_gb = _optional_non_negative_number(
            raw.get("max_size_gb"), f"{label}.max_size_gb"
        )
        if (
            min_size_gb is not None
            and max_size_gb is not None
            and min_size_gb > max_size_gb
        ):
            raise ValueError(f"{label}.min_size_gb must be <= {label}.max_size_gb")

        return cls(
            name=name.strip(),
            priority=_expect_number(raw.get("priority"), f"{label}.priority"),
            base_seed_hours=base_seed_hours,
            max_seed_hours=max_seed_hours,
            min_score_to_keep=_expect_number(
                raw.get("min_score_to_keep"), f"{label}.min_score_to_keep"
            ),
            match_categories=match_categories,
            match_tags=match_tags,
            tracker_contains=tracker_contains,
            min_size_gb=min_size_gb,
            max_size_gb=max_size_gb,
        )

    def matches(self, torrent: Torrent) -> bool:
        size_gib = _bytes_to_gib(torrent.size)
        if self.match_categories and torrent.category not in self.match_categories:
            return False

        torrent_tags = _split_tags(torrent.tags)
        if self.match_tags and not any(tag in torrent_tags for tag in self.match_tags):
            return False

        tracker_text = torrent.tracker.lower()
        if self.tracker_contains and not any(
            needle.lower() in tracker_text for needle in self.tracker_contains
        ):
            return False

        if self.min_size_gb is not None and size_gib < self.min_size_gb:
            return False

        if self.max_size_gb is not None and size_gib > self.max_size_gb:
            return False

        return True


@dataclass(frozen=True)
class ValueRetentionSettings:
    min_free_space_gb: int
    target_free_space_gb: int
    max_deletions_per_run: int
    history_hours: int
    recent_window_hours: int
    long_window_hours: int
    delete_low_value_after_base_seed: bool
    resume_error_downloads_after_cleanup: bool
    protected_tags: tuple[str, ...]
    protected_categories: tuple[str, ...]
    protected_tracker_contains: tuple[str, ...]
    score_weights: ScoreWeights
    default_policy: RetentionPolicy
    policies: tuple[RetentionPolicy, ...]

    @property
    def min_free_space_bytes(self) -> int:
        return self.min_free_space_gb * 1024**3

    @property
    def target_free_space_bytes(self) -> int:
        return self.target_free_space_gb * 1024**3

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> ValueRetentionSettings:
        min_free_space_gb = _expect_positive_int(
            options.get("min_free_space_gb"),
            "modules.value_retention_cleanup.options.min_free_space_gb",
        )
        target_free_space_gb = _expect_positive_int(
            options.get("target_free_space_gb"),
            "modules.value_retention_cleanup.options.target_free_space_gb",
        )
        if target_free_space_gb < min_free_space_gb:
            raise ValueError(
                "modules.value_retention_cleanup.options.target_free_space_gb must be >= modules.value_retention_cleanup.options.min_free_space_gb"
            )

        history_hours = _expect_positive_int(
            options.get("history_hours"),
            "modules.value_retention_cleanup.options.history_hours",
        )
        recent_window_hours = _expect_positive_int(
            options.get("recent_window_hours"),
            "modules.value_retention_cleanup.options.recent_window_hours",
        )
        long_window_hours = _expect_positive_int(
            options.get("long_window_hours"),
            "modules.value_retention_cleanup.options.long_window_hours",
        )
        if recent_window_hours > long_window_hours:
            raise ValueError(
                "modules.value_retention_cleanup.options.recent_window_hours must be <= modules.value_retention_cleanup.options.long_window_hours"
            )
        if long_window_hours > history_hours:
            raise ValueError(
                "modules.value_retention_cleanup.options.long_window_hours must be <= modules.value_retention_cleanup.options.history_hours"
            )

        default_policy = RetentionPolicy.from_options(
            _expect_dict(
                options.get("default_policy"),
                "modules.value_retention_cleanup.options.default_policy",
            ),
            "modules.value_retention_cleanup.options.default_policy",
            require_matchers=False,
        )

        raw_policies = _expect_list(
            options.get("policies", []),
            "modules.value_retention_cleanup.options.policies",
        )
        policies = tuple(
            RetentionPolicy.from_options(
                _expect_dict(
                    policy, f"modules.value_retention_cleanup.options.policies[{index}]"
                ),
                f"modules.value_retention_cleanup.options.policies[{index}]",
                require_matchers=True,
            )
            for index, policy in enumerate(raw_policies)
        )

        return cls(
            min_free_space_gb=min_free_space_gb,
            target_free_space_gb=target_free_space_gb,
            max_deletions_per_run=_expect_positive_int(
                options.get("max_deletions_per_run"),
                "modules.value_retention_cleanup.options.max_deletions_per_run",
            ),
            history_hours=history_hours,
            recent_window_hours=recent_window_hours,
            long_window_hours=long_window_hours,
            delete_low_value_after_base_seed=_expect_bool(
                options.get("delete_low_value_after_base_seed"),
                "modules.value_retention_cleanup.options.delete_low_value_after_base_seed",
            ),
            resume_error_downloads_after_cleanup=_expect_bool(
                options.get("resume_error_downloads_after_cleanup"),
                "modules.value_retention_cleanup.options.resume_error_downloads_after_cleanup",
            ),
            protected_tags=_expect_string_list(
                options.get("protected_tags", []),
                "modules.value_retention_cleanup.options.protected_tags",
            ),
            protected_categories=_expect_string_list(
                options.get("protected_categories", []),
                "modules.value_retention_cleanup.options.protected_categories",
            ),
            protected_tracker_contains=_expect_string_list(
                options.get("protected_tracker_contains", []),
                "modules.value_retention_cleanup.options.protected_tracker_contains",
            ),
            score_weights=ScoreWeights.from_options(
                _expect_dict(
                    options.get("score_weights"),
                    "modules.value_retention_cleanup.options.score_weights",
                )
            ),
            default_policy=default_policy,
            policies=policies,
        )


@dataclass(frozen=True)
class TorrentEvaluation:
    torrent: Torrent
    policy: RetentionPolicy
    score: float
    seed_hours: float
    size_gib: float
    recent_uploaded_gib: float
    long_uploaded_gib: float
    recent_uploaded_per_gib: float
    long_uploaded_per_gib: float
    upspeed_mib: float
    idle_hours: float
    protected_reason: str | None

    @property
    def is_protected(self) -> bool:
        return self.protected_reason is not None

    @property
    def over_base_seed(self) -> bool:
        return self.seed_hours >= self.policy.base_seed_hours

    @property
    def over_max_seed(self) -> bool:
        return (
            self.policy.max_seed_hours is not None
            and self.seed_hours >= self.policy.max_seed_hours
        )

    @property
    def below_keep_threshold(self) -> bool:
        return self.score < self.policy.min_score_to_keep


@dataclass(frozen=True)
class PlannedDeletion:
    evaluation: TorrentEvaluation
    reason: str


class ValueRetentionCleanupModule:
    name = "value_retention_cleanup"

    def __init__(self, options: dict[str, Any]) -> None:
        self.settings = ValueRetentionSettings.from_options(options)

    def run(
        self, context: ModuleContext, previous_state: dict[str, Any]
    ) -> ModuleResult:
        tracked_state = self._load_tracked_state(previous_state)

        evaluations: list[TorrentEvaluation] = []
        next_tracked_state: dict[str, dict[str, Any]] = {}
        for torrent in context.torrents:
            if not _is_seed_candidate(torrent):
                continue

            policy = self._select_policy(torrent)
            samples = self._update_samples(
                previous_samples=tracked_state.get(torrent.hash, []),
                now=context.now,
                uploaded=torrent.uploaded,
            )
            next_tracked_state[torrent.hash] = {
                "name": torrent.name,
                "samples": _serialize_samples(samples),
            }
            evaluations.append(
                self._evaluate_torrent(
                    torrent=torrent,
                    policy=policy,
                    samples=samples,
                    now=context.now,
                )
            )

        free_space = context.client.get_free_space_on_disk()
        context.logger.info(
            "Value retention check: free=%.2f GiB | threshold=%d GiB | target=%.2f GiB | tracked_complete=%d",
            _bytes_to_gib(free_space),
            self.settings.min_free_space_gb,
            _bytes_to_gib(self.settings.target_free_space_bytes),
            len(evaluations),
        )

        deletions = self._plan_deletions(
            evaluations=evaluations,
            free_space=free_space,
        )
        if not deletions:
            context.logger.info(
                "Done. deleted=0 | dry_run_deleted=0 | protected=%d",
                sum(1 for evaluation in evaluations if evaluation.is_protected),
            )
            return ModuleResult(state={"torrents": next_tracked_state})

        deleted_hashes: set[str] = set()
        deleted_count = 0
        dry_run_count = 0
        estimated_free_space = free_space
        for deletion in deletions:
            evaluation = deletion.evaluation
            torrent = evaluation.torrent
            message = (
                "%s: %s | policy=%s | score=%.3f | threshold=%.3f | seed_hours=%.2f | "
                "size=%.2f GiB | uploaded_%dh=%.2f GiB | uploaded_%dh=%.2f GiB | upspeed=%.2f MiB/s | idle_hours=%.2f"
            )
            args = (
                deletion.reason,
                torrent.name,
                evaluation.policy.name,
                evaluation.score,
                evaluation.policy.min_score_to_keep,
                evaluation.seed_hours,
                evaluation.size_gib,
                self.settings.recent_window_hours,
                evaluation.recent_uploaded_gib,
                self.settings.long_window_hours,
                evaluation.long_uploaded_gib,
                evaluation.upspeed_mib,
                evaluation.idle_hours,
            )

            if context.dry_run:
                context.logger.warning(
                    "[DRY RUN] Would delete low-value seed. " + message, *args
                )
                dry_run_count += 1
                estimated_free_space += torrent.size
                continue

            try:
                context.client.delete_torrent(torrent.hash, delete_files=True)
                deleted_hashes.add(torrent.hash)
                deleted_count += 1
                estimated_free_space += torrent.size
                context.logger.warning("Deleted low-value seed. " + message, *args)
            except Exception as exc:
                context.logger.exception(
                    "Failed to delete torrent %s during value retention cleanup: %s",
                    torrent.name,
                    exc,
                )

        if deleted_count > 0 and self.settings.resume_error_downloads_after_cleanup:
            self._resume_error_downloads(context)

        if deleted_hashes:
            next_tracked_state = {
                torrent_hash: state
                for torrent_hash, state in next_tracked_state.items()
                if torrent_hash not in deleted_hashes
            }

        context.logger.info(
            "Done. deleted=%d | dry_run_deleted=%d | protected=%d | free_before=%.2f GiB | free_after_est=%.2f GiB",
            deleted_count,
            dry_run_count,
            sum(1 for evaluation in evaluations if evaluation.is_protected),
            _bytes_to_gib(free_space),
            _bytes_to_gib(estimated_free_space),
        )
        return ModuleResult(state={"torrents": next_tracked_state})

    def _load_tracked_state(
        self, previous_state: dict[str, Any]
    ) -> dict[str, list[UploadSample]]:
        raw_tracked = previous_state.get("torrents", {})
        if not isinstance(raw_tracked, dict):
            return {}

        tracked: dict[str, list[UploadSample]] = {}
        for torrent_hash, raw_entry in raw_tracked.items():
            if not isinstance(torrent_hash, str) or not isinstance(raw_entry, dict):
                continue
            raw_samples = raw_entry.get("samples", [])
            if not isinstance(raw_samples, list):
                continue

            samples: list[UploadSample] = []
            for raw_sample in raw_samples:
                if not isinstance(raw_sample, dict):
                    continue
                ts = raw_sample.get("ts")
                uploaded = raw_sample.get("uploaded")
                if (
                    isinstance(ts, int)
                    and isinstance(uploaded, int)
                    and ts > 0
                    and uploaded >= 0
                ):
                    samples.append(UploadSample(ts=ts, uploaded=uploaded))
            if samples:
                tracked[torrent_hash] = sorted(samples, key=lambda sample: sample.ts)
        return tracked

    def _update_samples(
        self, *, previous_samples: list[UploadSample], now: int, uploaded: int
    ) -> list[UploadSample]:
        bucket_ts = now - (now % 3600)
        threshold = bucket_ts - (self.settings.history_hours * 3600)
        samples = [sample for sample in previous_samples if sample.ts >= threshold]

        if samples and uploaded < samples[-1].uploaded:
            samples = []

        if samples and samples[-1].ts == bucket_ts:
            last_sample = samples[-1]
            samples[-1] = UploadSample(
                ts=last_sample.ts,
                uploaded=max(last_sample.uploaded, uploaded),
            )
        else:
            samples.append(UploadSample(ts=bucket_ts, uploaded=uploaded))

        return samples

    def _select_policy(self, torrent: Torrent) -> RetentionPolicy:
        for policy in self.settings.policies:
            if policy.matches(torrent):
                return policy
        return self.settings.default_policy

    def _evaluate_torrent(
        self,
        *,
        torrent: Torrent,
        policy: RetentionPolicy,
        samples: list[UploadSample],
        now: int,
    ) -> TorrentEvaluation:
        size_gib = max(_bytes_to_gib(torrent.size), 0.01)
        recent_uploaded = self._uploaded_in_window(
            samples=samples,
            current_uploaded=torrent.uploaded,
            now=now,
            window_hours=self.settings.recent_window_hours,
        )
        long_uploaded = self._uploaded_in_window(
            samples=samples,
            current_uploaded=torrent.uploaded,
            now=now,
            window_hours=self.settings.long_window_hours,
        )
        recent_uploaded_gib = _bytes_to_gib(recent_uploaded)
        long_uploaded_gib = _bytes_to_gib(long_uploaded)
        recent_uploaded_per_gib = recent_uploaded_gib / size_gib
        long_uploaded_per_gib = long_uploaded_gib / size_gib
        upspeed_mib = _bytes_to_mib(max(torrent.upspeed, 0))

        seed_start = (
            torrent.completion_on if torrent.completion_on > 0 else torrent.added_on
        )
        seed_hours = max((now - seed_start) / 3600, 0.0)

        last_activity = torrent.last_activity
        if last_activity <= 0:
            last_activity = seed_start
        idle_hours = max((now - last_activity) / 3600, 0.0)

        score = (
            policy.priority
            + (
                self.settings.score_weights.recent_upload_per_gib
                * recent_uploaded_per_gib
            )
            + (self.settings.score_weights.long_upload_per_gib * long_uploaded_per_gib)
            + (self.settings.score_weights.current_upspeed_mib * upspeed_mib)
            - (self.settings.score_weights.idle_hours * idle_hours)
            - (self.settings.score_weights.size_root * math.sqrt(size_gib))
        )

        return TorrentEvaluation(
            torrent=torrent,
            policy=policy,
            score=score,
            seed_hours=seed_hours,
            size_gib=size_gib,
            recent_uploaded_gib=recent_uploaded_gib,
            long_uploaded_gib=long_uploaded_gib,
            recent_uploaded_per_gib=recent_uploaded_per_gib,
            long_uploaded_per_gib=long_uploaded_per_gib,
            upspeed_mib=upspeed_mib,
            idle_hours=idle_hours,
            protected_reason=self._protected_reason(torrent),
        )

    def _uploaded_in_window(
        self,
        *,
        samples: list[UploadSample],
        current_uploaded: int,
        now: int,
        window_hours: int,
    ) -> int:
        if not samples:
            return 0

        cutoff = now - (window_hours * 3600)
        baseline = samples[0].uploaded
        for sample in reversed(samples):
            if sample.ts <= cutoff:
                baseline = sample.uploaded
                break

        return max(current_uploaded - baseline, 0)

    def _protected_reason(self, torrent: Torrent) -> str | None:
        torrent_tags = _split_tags(torrent.tags)
        for tag in self.settings.protected_tags:
            if tag in torrent_tags:
                return f"protected_tag:{tag}"

        for category in self.settings.protected_categories:
            if torrent.category == category:
                return f"protected_category:{category}"

        tracker_text = torrent.tracker.lower()
        for tracker_value in self.settings.protected_tracker_contains:
            if tracker_value.lower() in tracker_text:
                return f"protected_tracker:{tracker_value}"

        return None

    def _plan_deletions(
        self, *, evaluations: list[TorrentEvaluation], free_space: int
    ) -> list[PlannedDeletion]:
        planned: list[PlannedDeletion] = []
        planned_hashes: set[str] = set()
        estimated_free_space = free_space

        if self.settings.delete_low_value_after_base_seed:
            proactive_candidates = sorted(
                (
                    evaluation
                    for evaluation in evaluations
                    if not evaluation.is_protected
                    and evaluation.over_base_seed
                    and (evaluation.over_max_seed or evaluation.below_keep_threshold)
                ),
                key=self._delete_sort_key,
            )
            for evaluation in proactive_candidates:
                if len(planned) >= self.settings.max_deletions_per_run:
                    break
                planned.append(
                    PlannedDeletion(
                        evaluation=evaluation,
                        reason=(
                            "expired_max_seed"
                            if evaluation.over_max_seed
                            else "expired_low_value"
                        ),
                    )
                )
                planned_hashes.add(evaluation.torrent.hash)
                estimated_free_space += evaluation.torrent.size

        if free_space >= self.settings.min_free_space_bytes:
            return planned

        pressure_candidates = sorted(
            (
                evaluation
                for evaluation in evaluations
                if not evaluation.is_protected
                and evaluation.torrent.hash not in planned_hashes
            ),
            key=self._delete_sort_key,
        )
        for evaluation in pressure_candidates:
            if len(planned) >= self.settings.max_deletions_per_run:
                break
            if estimated_free_space >= self.settings.target_free_space_bytes:
                break
            planned.append(
                PlannedDeletion(
                    evaluation=evaluation,
                    reason=(
                        "space_pressure_expired"
                        if evaluation.over_base_seed
                        else "space_pressure_low_margin"
                    ),
                )
            )
            estimated_free_space += evaluation.torrent.size

        return planned

    def _delete_sort_key(
        self, evaluation: TorrentEvaluation
    ) -> tuple[int, float, float, float]:
        tier = 2
        if evaluation.over_max_seed:
            tier = 0
        elif evaluation.over_base_seed and evaluation.below_keep_threshold:
            tier = 1
        return (tier, evaluation.score, -evaluation.size_gib, -evaluation.seed_hours)

    def _resume_error_downloads(self, context: ModuleContext) -> None:
        try:
            refreshed_torrents = context.client.get_torrents()
        except Exception as exc:
            context.logger.exception(
                "Failed to refresh torrents after value retention cleanup: %s", exc
            )
            return

        error_downloads = [
            torrent
            for torrent in refreshed_torrents
            if torrent.state == "error" and torrent.amount_left > 0
        ]
        if not error_downloads:
            context.logger.info(
                "No errored downloads found after value retention cleanup"
            )
            return

        hashes = [torrent.hash for torrent in error_downloads]
        names = ", ".join(torrent.name for torrent in error_downloads)
        try:
            context.client.start_torrents(hashes)
            context.logger.info(
                "Resumed errored downloads after value retention cleanup: count=%d | torrents=%s",
                len(error_downloads),
                names,
            )
        except Exception as exc:
            context.logger.exception(
                "Failed to resume errored downloads after value retention cleanup: %s",
                exc,
            )
