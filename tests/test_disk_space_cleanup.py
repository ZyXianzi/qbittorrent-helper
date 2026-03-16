from __future__ import annotations

from unittest.mock import MagicMock

from qb_helper.modules.disk_space_cleanup import DiskSpaceCleanupModule


def test_disk_space_cleanup_noops_when_free_space_is_sufficient(
    make_torrent, make_context
) -> None:
    module = DiskSpaceCleanupModule({"min_free_space_gb": 20})
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 25 * 1024**3
    torrent = make_torrent(progress=1.0, amount_left=0, size=5 * 1024**3)

    result = module.run(
        make_context(client=client, torrents=[torrent]),
        previous_state={},
    )

    assert result.state == {}
    client.delete_torrent.assert_not_called()
    client.start_torrents.assert_not_called()


def test_disk_space_cleanup_deletes_largest_seed_and_resumes_errors(
    make_torrent, make_context
) -> None:
    module = DiskSpaceCleanupModule({"min_free_space_gb": 20})
    client = MagicMock()
    client.get_free_space_on_disk.return_value = 5 * 1024**3
    client.get_torrents.return_value = [
        make_torrent(
            hash="err-1", name="Errored Download", state="error", amount_left=1
        )
    ]
    torrents = [
        make_torrent(
            hash="seed-small",
            name="Small Seed",
            progress=1.0,
            amount_left=0,
            size=5 * 1024**3,
            added_on=1,
        ),
        make_torrent(
            hash="seed-large",
            name="Large Seed",
            progress=1.0,
            amount_left=0,
            size=10 * 1024**3,
            added_on=2,
        ),
        make_torrent(hash="downloading", progress=0.4, amount_left=50),
    ]

    result = module.run(
        make_context(client=client, torrents=torrents),
        previous_state={},
    )

    assert result.state == {}
    client.delete_torrent.assert_called_once_with("seed-large", delete_files=True)
    client.start_torrents.assert_called_once_with(["err-1"])
