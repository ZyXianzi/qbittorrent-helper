from __future__ import annotations

from unittest.mock import MagicMock, call

from qb_helper.modules.value_retention_cleanup import ValueRetentionCleanupModule


def make_options() -> dict[str, object]:
    return {
        "min_free_space_gb": 80,
        "target_free_space_gb": 150,
        "max_deletions_per_run": 4,
        "history_hours": 48,
        "recent_window_hours": 6,
        "long_window_hours": 24,
        "delete_low_value_after_base_seed": True,
        "resume_error_downloads_after_cleanup": True,
        "protected_tags": ["manual-keep"],
        "protected_categories": ["do-not-delete"],
        "protected_tracker_contains": ["viptracker"],
        "score_weights": {
            "recent_upload_per_gib": 4.0,
            "long_upload_per_gib": 2.0,
            "current_upspeed_mib": 0.3,
            "idle_hours": 0.5,
            "size_root": 0.4,
        },
        "default_policy": {
            "name": "default",
            "priority": 0.0,
            "base_seed_hours": 12,
            "max_seed_hours": 24,
            "min_score_to_keep": 1.0,
        },
        "policies": [
            {
                "name": "adult-large",
                "match_categories": ["adult"],
                "min_size_gb": 50,
                "priority": 6.0,
                "base_seed_hours": 24,
                "max_seed_hours": 72,
                "min_score_to_keep": 1.5,
            },
            {
                "name": "large-free",
                "match_categories": ["general"],
                "min_size_gb": 50,
                "priority": 2.0,
                "base_seed_hours": 12,
                "max_seed_hours": 36,
                "min_score_to_keep": 1.5,
            },
        ],
    }


def test_value_retention_cleanup_deletes_low_value_seed_after_base_hours(
    make_torrent, make_context
) -> None:
    now = 200 * 3600
    module = ValueRetentionCleanupModule(make_options())
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 200 * 1024**3
    client.get_torrents.return_value = []
    torrent = make_torrent(
        hash="low-value",
        name="Low Value Seed",
        state="uploading",
        progress=1.0,
        amount_left=0,
        size=5 * 1024**3,
        added_on=now - (14 * 3600),
        completion_on=now - (13 * 3600),
        last_activity=now - (13 * 3600),
    )

    result = module.run(
        make_context(client=client, torrents=[torrent], now=now),
        previous_state={},
    )

    client.delete_torrent.assert_called_once_with("low-value", delete_files=True)
    client.start_torrents.assert_not_called()
    assert result.state == {"torrents": {}}


def test_value_retention_cleanup_keeps_high_value_adult_seed(
    make_torrent, make_context
) -> None:
    now = 300 * 3600
    gib = 1024**3
    module = ValueRetentionCleanupModule(make_options())
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 300 * gib
    torrent = make_torrent(
        hash="adult-hot",
        name="Adult Hot Pack",
        state="uploading",
        progress=1.0,
        amount_left=0,
        category="adult",
        size=60 * gib,
        uploaded=240 * gib,
        upspeed=40 * 1024**2,
        added_on=now - (28 * 3600),
        completion_on=now - (26 * 3600),
        last_activity=now - 600,
    )
    previous_state = {
        "torrents": {
            "adult-hot": {
                "name": "Adult Hot Pack",
                "samples": [
                    {"ts": now - (24 * 3600), "uploaded": 100 * gib},
                    {"ts": now - (6 * 3600), "uploaded": 200 * gib},
                ],
            }
        }
    }

    result = module.run(
        make_context(client=client, torrents=[torrent], now=now),
        previous_state=previous_state,
    )

    client.delete_torrent.assert_not_called()
    assert "adult-hot" in result.state["torrents"]
    assert result.state["torrents"]["adult-hot"]["samples"]


def test_value_retention_cleanup_uses_lowest_score_for_space_pressure(
    make_torrent, make_context
) -> None:
    now = 400 * 3600
    gib = 1024**3
    module = ValueRetentionCleanupModule(make_options())
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 50 * gib
    client.get_torrents.return_value = []
    low_value = make_torrent(
        hash="low-space",
        name="Low Space Seed",
        state="stalledUP",
        progress=1.0,
        amount_left=0,
        size=100 * gib,
        added_on=now - (18 * 3600),
        completion_on=now - (16 * 3600),
        last_activity=now - (12 * 3600),
    )
    high_value = make_torrent(
        hash="high-space",
        name="High Space Seed",
        state="uploading",
        progress=1.0,
        amount_left=0,
        category="adult",
        size=60 * gib,
        uploaded=220 * gib,
        upspeed=30 * 1024**2,
        added_on=now - (30 * 3600),
        completion_on=now - (26 * 3600),
        last_activity=now - 300,
    )
    previous_state = {
        "torrents": {
            "high-space": {
                "name": "High Space Seed",
                "samples": [
                    {"ts": now - (24 * 3600), "uploaded": 120 * gib},
                    {"ts": now - (6 * 3600), "uploaded": 180 * gib},
                ],
            }
        }
    }

    module.run(
        make_context(client=client, torrents=[low_value, high_value], now=now),
        previous_state=previous_state,
    )

    client.delete_torrent.assert_has_calls(
        [call("low-space", delete_files=True)],
        any_order=False,
    )
    client.delete_torrent.assert_called_once()


def test_value_retention_cleanup_respects_protected_tags_under_pressure(
    make_torrent, make_context
) -> None:
    now = 500 * 3600
    gib = 1024**3
    module = ValueRetentionCleanupModule(make_options())
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 20 * gib
    client.get_torrents.return_value = []
    protected = make_torrent(
        hash="protected",
        name="Protected Seed",
        state="stalledUP",
        progress=1.0,
        amount_left=0,
        size=90 * gib,
        tags="manual-keep",
        added_on=now - (18 * 3600),
        completion_on=now - (16 * 3600),
        last_activity=now - (16 * 3600),
    )
    disposable = make_torrent(
        hash="disposable",
        name="Disposable Seed",
        state="stalledUP",
        progress=1.0,
        amount_left=0,
        size=140 * gib,
        added_on=now - (18 * 3600),
        completion_on=now - (16 * 3600),
        last_activity=now - (16 * 3600),
    )

    module.run(
        make_context(client=client, torrents=[protected, disposable], now=now),
        previous_state={},
    )

    client.delete_torrent.assert_called_once_with("disposable", delete_files=True)
