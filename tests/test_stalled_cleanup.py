from __future__ import annotations

from unittest.mock import MagicMock

from qb_helper.modules.stalled_cleanup import StalledCleanupModule


def test_stalled_cleanup_tracks_new_stalled_torrent(make_torrent, make_context) -> None:
    module = StalledCleanupModule(
        {
            "candidate_seconds": 60,
            "delete_seconds": 120,
            "candidate_tag": "stalled-long",
        }
    )
    client = MagicMock()
    torrent = make_torrent(hash="abc", state="stalledDL", progress=0.25)

    result = module.run(
        make_context(client=client, torrents=[torrent], now=1_000),
        previous_state={},
    )

    assert result.state == {
        "abc": {"name": "Example Torrent", "first_seen_stalled": 1_000}
    }
    client.add_tags.assert_not_called()
    client.delete_torrent.assert_not_called()


def test_stalled_cleanup_removes_candidate_tag_when_torrent_recovers(
    make_torrent, make_context
) -> None:
    module = StalledCleanupModule(
        {
            "candidate_seconds": 60,
            "delete_seconds": 120,
            "candidate_tag": "stalled-long",
        }
    )
    client = MagicMock()
    torrent = make_torrent(
        hash="abc",
        name="Recovered Torrent",
        state="downloading",
        tags="keep, stalled-long",
    )

    result = module.run(
        make_context(client=client, torrents=[torrent], now=1_200),
        previous_state={
            "abc": {"name": "Recovered Torrent", "first_seen_stalled": 1_000}
        },
    )

    assert result.state == {}
    client.remove_tags.assert_called_once_with("abc", "stalled-long")


def test_stalled_cleanup_adds_tag_and_deletes_overdue_torrent(
    make_torrent, make_context
) -> None:
    module = StalledCleanupModule(
        {
            "candidate_seconds": 60,
            "delete_seconds": 120,
            "candidate_tag": "stalled-long",
        }
    )
    client = MagicMock()
    torrent = make_torrent(
        hash="abc",
        name="Stuck Torrent",
        state="stalledDL",
        progress=0.75,
    )

    result = module.run(
        make_context(client=client, torrents=[torrent], now=1_200),
        previous_state={"abc": {"name": "Stuck Torrent", "first_seen_stalled": 900}},
    )

    assert result.state == {}
    client.add_tags.assert_called_once_with("abc", "stalled-long")
    client.delete_torrent.assert_called_once_with("abc", delete_files=True)
