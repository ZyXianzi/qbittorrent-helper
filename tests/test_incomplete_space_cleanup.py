from __future__ import annotations

from unittest.mock import MagicMock, call

from qb_helper.config import ProtectionConfig
from qb_helper.modules.incomplete_space_cleanup import IncompleteSpaceCleanupModule


def test_incomplete_space_cleanup_deletes_largest_occupied_torrents_until_target(
    make_torrent, make_context
) -> None:
    gib = 1024**3
    module = IncompleteSpaceCleanupModule()
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 20 * gib
    large = make_torrent(
        hash="large",
        name="Large Incomplete",
        size=260 * gib,
        amount_left=180 * gib,
    )
    medium = make_torrent(
        hash="medium",
        name="Medium Incomplete",
        size=230 * gib,
        amount_left=160 * gib,
    )
    small = make_torrent(
        hash="small",
        name="Small Incomplete",
        size=120 * gib,
        amount_left=80 * gib,
    )

    module.run(
        make_context(
            client=client,
            torrents=[small, medium, large],
            module_runtime={
                "value_retention_cleanup": {
                    "space_pressure_triggered": True,
                    "target_free_space_bytes": 150 * gib,
                }
            },
            module_name="incomplete_space_cleanup",
        ),
        previous_state={},
    )

    client.delete_torrent.assert_has_calls(
        [
            call("large", delete_files=True),
            call("medium", delete_files=True),
        ],
        any_order=False,
    )


def test_incomplete_space_cleanup_skips_when_value_retention_was_not_triggered(
    make_torrent, make_context
) -> None:
    gib = 1024**3
    module = IncompleteSpaceCleanupModule()
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 30 * gib
    torrent = make_torrent(
        hash="candidate",
        name="Candidate",
        size=300 * gib,
        amount_left=120 * gib,
    )

    module.run(
        make_context(
            client=client,
            torrents=[torrent],
            module_runtime={
                "value_retention_cleanup": {"target_free_space_bytes": 150 * gib}
            },
            module_name="incomplete_space_cleanup",
        ),
        previous_state={},
    )

    client.delete_torrent.assert_not_called()


def test_incomplete_space_cleanup_respects_protection_rules(
    make_torrent, make_context
) -> None:
    gib = 1024**3
    module = IncompleteSpaceCleanupModule()
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 40 * gib
    protected = make_torrent(
        hash="protected",
        name="Protected",
        size=500 * gib,
        amount_left=100 * gib,
        tags="manual-keep",
    )
    disposable = make_torrent(
        hash="disposable",
        name="Disposable",
        size=320 * gib,
        amount_left=120 * gib,
    )

    module.run(
        make_context(
            client=client,
            torrents=[protected, disposable],
            protection=ProtectionConfig(
                tags=("manual-keep",),
                categories=("do-not-delete",),
                tracker_contains=("viptracker",),
            ),
            module_runtime={
                "value_retention_cleanup": {
                    "space_pressure_triggered": True,
                    "target_free_space_bytes": 150 * gib,
                }
            },
            module_name="incomplete_space_cleanup",
        ),
        previous_state={},
    )

    client.delete_torrent.assert_called_once_with("disposable", delete_files=True)
