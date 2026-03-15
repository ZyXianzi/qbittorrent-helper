from __future__ import annotations

from typing import Any

import requests

from qb_helper.models import Torrent


class QBittorrentClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: int) -> None:
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
                tags=item.get("tags", "") or "",
            )
            for item in raw_items
        ]

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
            data={"hashes": torrent_hash, "deleteFiles": "true" if delete_files else "false"},
            timeout=self.timeout,
        )
        response.raise_for_status()
