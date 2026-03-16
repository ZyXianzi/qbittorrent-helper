from __future__ import annotations

from typing import Any

import requests

from qb_helper.models import Torrent


class QBittorrentClient:
    def __init__(
        self, base_url: str, username: str, password: str, timeout: int
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()

    def login(self) -> None:
        response = self.session.post(
            f"{self.base_url}/api/v2/auth/login",
            data={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        response.raise_for_status()
        if response.text.strip() != "Ok.":
            raise RuntimeError(f"qBittorrent login failed: {response.text!r}")

    def get_torrents(self) -> list[Torrent]:
        response = self.session.get(
            f"{self.base_url}/api/v2/torrents/info",
            timeout=self.timeout,
        )
        response.raise_for_status()
        raw_items: list[dict[str, Any]] = response.json()
        return [
            Torrent(
                hash=item["hash"],
                name=item.get("name", ""),
                state=item.get("state", ""),
                progress=float(item.get("progress", 0.0)),
                added_on=int(item.get("added_on", 0)),
                size=int(item.get("size", 0)),
                amount_left=int(item.get("amount_left", 0)),
                tags=item.get("tags", "") or "",
                seeding_time_limit=int(item.get("seeding_time_limit", -2)),
            )
            for item in raw_items
        ]

    def get_free_space_on_disk(self) -> int:
        response = self.session.get(
            f"{self.base_url}/api/v2/sync/maindata",
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        server_state = payload.get("server_state")
        if not isinstance(server_state, dict):
            raise RuntimeError("qBittorrent maindata response missing server_state")
        free_space_on_disk = server_state.get("free_space_on_disk")
        if not isinstance(free_space_on_disk, int):
            raise RuntimeError(
                "qBittorrent maindata response missing free_space_on_disk"
            )
        return free_space_on_disk

    def add_tags(self, torrent_hash: str, tags: str) -> None:
        response = self.session.post(
            f"{self.base_url}/api/v2/torrents/addTags",
            data={"hashes": torrent_hash, "tags": tags},
            timeout=self.timeout,
        )
        response.raise_for_status()

    def remove_tags(self, torrent_hash: str, tags: str) -> None:
        response = self.session.post(
            f"{self.base_url}/api/v2/torrents/removeTags",
            data={"hashes": torrent_hash, "tags": tags},
            timeout=self.timeout,
        )
        response.raise_for_status()

    def delete_torrent(self, torrent_hash: str, delete_files: bool = True) -> None:
        response = self.session.post(
            f"{self.base_url}/api/v2/torrents/delete",
            data={
                "hashes": torrent_hash,
                "deleteFiles": "true" if delete_files else "false",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

    def start_torrents(self, torrent_hashes: list[str]) -> None:
        response = self.session.post(
            f"{self.base_url}/api/v2/torrents/start",
            data={"hashes": "|".join(torrent_hashes)},
            timeout=self.timeout,
        )
        response.raise_for_status()

    def set_seeding_time_limit(self, torrent_hash: str, minutes: int) -> None:
        response = self.session.post(
            f"{self.base_url}/api/v2/torrents/setShareLimits",
            data={
                "hashes": torrent_hash,
                "ratioLimit": -2,
                "seedingTimeLimit": minutes,
                "inactiveSeedingTimeLimit": -2,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
