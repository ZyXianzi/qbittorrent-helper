#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

import requests


# =========================
# Environment variables
# =========================
QB_URL = os.getenv("QB_URL", "http://127.0.0.1:8080")
QB_USERNAME = os.getenv("QB_USERNAME", "admin")
QB_PASSWORD = os.getenv("QB_PASSWORD", "adminadmin")

STATE_FILE = Path(os.getenv("STATE_FILE", "./qb_stalled_state.json"))
LOG_FILE = Path(os.getenv("LOG_FILE", "./cleaner.log"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

CANDIDATE_SECONDS = int(os.getenv("CANDIDATE_SECONDS", "7200"))   # 2h
DELETE_SECONDS = int(os.getenv("DELETE_SECONDS", "10800"))        # 3h
CANDIDATE_TAG = os.getenv("CANDIDATE_TAG", "stalled-long")

DRY_RUN = os.getenv("DRY_RUN", "false").lower() in {"1", "true", "yes", "on"}
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))


# =========================
# Logging
# =========================
def setup_logging() -> logging.Logger:
    logger = logging.getLogger("qb_stalled_cleaner")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File: rotate hourly, keep last 24 files ~= last 24 hours
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=str(LOG_FILE),
        when="H",
        interval=1,
        backupCount=24,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()


# =========================
# Data classes
# =========================
@dataclass
class Torrent:
    hash: str
    name: str
    state: str
    progress: float
    added_on: int
    tags: str


# =========================
# qBittorrent client
# =========================
class QBittorrentClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = 15) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()

    def login(self) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/v2/auth/login",
            data={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        if resp.text.strip() != "Ok.":
            raise RuntimeError(f"qBittorrent login failed: {resp.text!r}")

    def get_torrents(self) -> list[Torrent]:
        resp = self.session.get(
            f"{self.base_url}/api/v2/torrents/info",
            timeout=self.timeout,
        )
        resp.raise_for_status()
        raw_items: list[dict[str, Any]] = resp.json()
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
        resp = self.session.post(
            f"{self.base_url}/api/v2/torrents/addTags",
            data={"hashes": torrent_hash, "tags": tags},
            timeout=self.timeout,
        )
        resp.raise_for_status()

    def remove_tags(self, torrent_hash: str, tags: str) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/v2/torrents/removeTags",
            data={"hashes": torrent_hash, "tags": tags},
            timeout=self.timeout,
        )
        resp.raise_for_status()

    def delete_torrent(self, torrent_hash: str, delete_files: bool = True) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/v2/torrents/delete",
            data={"hashes": torrent_hash, "deleteFiles": "true" if delete_files else "false"},
            timeout=self.timeout,
        )
        resp.raise_for_status()


# =========================
# Helpers
# =========================
def load_state(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load state file %s: %s. Resetting state.", path, exc)
        return {}


def save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp_path.replace(path)


def has_tag(existing_tags: str, target_tag: str) -> bool:
    return target_tag in [t.strip() for t in existing_tags.split(",") if t.strip()]


# =========================
# Main
# =========================
def main() -> int:
    now = int(time.time())
    old_state = load_state(STATE_FILE)

    client = QBittorrentClient(QB_URL, QB_USERNAME, QB_PASSWORD, REQUEST_TIMEOUT)

    try:
        client.login()
        torrents = client.get_torrents()
    except Exception as exc:
        logger.exception("Failed to communicate with qBittorrent: %s", exc)
        return 1

    torrents_by_hash = {torrent.hash: torrent for torrent in torrents}
    new_state: dict[str, dict[str, Any]] = {}

    # Pass 1: handle recovered / disappeared torrents that existed in old_state
    for torrent_hash, old_entry in old_state.items():
        torrent = torrents_by_hash.get(torrent_hash)
        first_seen_stalled = int(old_entry.get("first_seen_stalled", now))
        last_name = old_entry.get("name", torrent_hash)

        # Torrent disappeared from qB list entirely
        if torrent is None:
            logger.info(
                "Torrent disappeared from qB list; clearing stalled state: %s | previous_stalled=%ss",
                last_name,
                now - first_seen_stalled,
            )
            continue

        # Torrent still exists, but is no longer stalledDL => recovered
        if torrent.state != "stalledDL":
            logger.info(
                "Recovered from stalledDL: %s | new_state=%s | previous_stalled=%ss",
                torrent.name,
                torrent.state,
                now - first_seen_stalled,
            )
            if has_tag(torrent.tags, CANDIDATE_TAG):
                if DRY_RUN:
                    logger.info(
                        "[DRY RUN] Would remove tag '%s' from recovered torrent: %s",
                        CANDIDATE_TAG,
                        torrent.name,
                    )
                else:
                    try:
                        client.remove_tags(torrent.hash, CANDIDATE_TAG)
                        logger.info(
                            "Removed tag '%s' from recovered torrent: %s",
                            CANDIDATE_TAG,
                            torrent.name,
                        )
                    except Exception as exc:
                        logger.exception("Failed to remove tag from %s: %s", torrent.name, exc)
            continue

    # Pass 2: handle currently stalledDL torrents
    for torrent in torrents:
        if torrent.state != "stalledDL":
            continue

        old_entry = old_state.get(torrent.hash)
        if old_entry:
            first_seen_stalled = int(old_entry.get("first_seen_stalled", now))
        else:
            first_seen_stalled = now
            logger.info(
                "First seen stalledDL: %s | progress=%.4f",
                torrent.name,
                torrent.progress,
            )

        stalled_duration = now - first_seen_stalled

        logger.info(
            "Tracking stalledDL: %s | progress=%.4f | stalled=%ss | state=%s",
            torrent.name,
            torrent.progress,
            stalled_duration,
            torrent.state,
        )

        # >= 2h => add tag
        if stalled_duration >= CANDIDATE_SECONDS and not has_tag(torrent.tags, CANDIDATE_TAG):
            if DRY_RUN:
                logger.info(
                    "[DRY RUN] Would add tag '%s': %s | progress=%.4f | stalled=%ss",
                    CANDIDATE_TAG,
                    torrent.name,
                    torrent.progress,
                    stalled_duration,
                )
            else:
                try:
                    client.add_tags(torrent.hash, CANDIDATE_TAG)
                    logger.info(
                        "Added tag '%s': %s | progress=%.4f | stalled=%ss",
                        CANDIDATE_TAG,
                        torrent.name,
                        torrent.progress,
                        stalled_duration,
                    )
                except Exception as exc:
                    logger.exception("Failed to add tag for %s: %s", torrent.name, exc)

        # >= 3h => delete torrent and files
        if stalled_duration >= DELETE_SECONDS:
            if DRY_RUN:
                logger.warning(
                    "[DRY RUN] Would delete torrent and files: %s | progress=%.4f | stalled=%ss",
                    torrent.name,
                    torrent.progress,
                    stalled_duration,
                )
            else:
                try:
                    client.delete_torrent(torrent.hash, delete_files=True)
                    logger.warning(
                        "Deleted torrent and files: %s | progress=%.4f | stalled=%ss",
                        torrent.name,
                        torrent.progress,
                        stalled_duration,
                    )
                except Exception as exc:
                    logger.exception("Failed to delete torrent %s: %s", torrent.name, exc)
            continue

        # still stalled and not deleted => keep tracking
        new_state[torrent.hash] = {
            "name": torrent.name,
            "first_seen_stalled": first_seen_stalled,
        }

    try:
        save_state(STATE_FILE, new_state)
    except Exception as exc:
        logger.exception("Failed to save state: %s", exc)
        return 1

    logger.info("Done. tracked_stalled=%d", len(new_state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
