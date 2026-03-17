from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Torrent:
    hash: str
    name: str
    state: str
    progress: float
    added_on: int
    completion_on: int
    last_activity: int
    size: int
    amount_left: int
    uploaded: int
    upspeed: int
    ratio: float
    seeding_time: int
    tags: str
    category: str
    tracker: str
