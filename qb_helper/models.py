from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Torrent:
    hash: str
    name: str
    state: str
    progress: float
    added_on: int
    tags: str
