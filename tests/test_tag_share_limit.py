from __future__ import annotations

import logging
from unittest.mock import MagicMock

from qb_helper.modules.tag_share_limit import TagShareLimitModule


def test_tag_share_limit_applies_shortest_matching_rule(
    make_torrent, make_context, caplog
) -> None:
    module = TagShareLimitModule(
        {"tag_seeding_time_limit_minutes": {"keep-1d": 1_440, "keep-7d": 10_080}}
    )
    client = MagicMock()
    torrent = make_torrent(
        hash="abc",
        name="Tagged Torrent",
        tags="keep-7d, keep-1d",
        seeding_time_limit=-2,
    )

    with caplog.at_level(logging.INFO):
        result = module.run(
            make_context(client=client, torrents=[torrent]),
            previous_state={},
        )

    assert result.state == {}
    client.set_seeding_time_limit.assert_called_once_with("abc", 1_440)
    assert "Multiple tag share-limit rules matched" in caplog.text


def test_tag_share_limit_skips_matching_limit(make_torrent, make_context) -> None:
    module = TagShareLimitModule({"tag_seeding_time_limit_minutes": {"keep-1d": 1_440}})
    client = MagicMock()
    torrent = make_torrent(tags="keep-1d", seeding_time_limit=1_440)

    result = module.run(
        make_context(client=client, torrents=[torrent]),
        previous_state={},
    )

    assert result.state == {}
    client.set_seeding_time_limit.assert_not_called()


def test_tag_share_limit_respects_dry_run(make_torrent, make_context) -> None:
    module = TagShareLimitModule({"tag_seeding_time_limit_minutes": {"keep-1d": 1_440}})
    client = MagicMock()
    torrent = make_torrent(hash="abc", tags="keep-1d", seeding_time_limit=-2)

    result = module.run(
        make_context(client=client, torrents=[torrent], dry_run=True),
        previous_state={},
    )

    assert result.state == {}
    client.set_seeding_time_limit.assert_not_called()
