from __future__ import annotations

from pathlib import Path

import pytest

from qb_helper.state import load_state, save_state


def test_save_state_creates_parent_directories_and_round_trips(tmp_path: Path) -> None:
    state_path = tmp_path / "nested" / "state.json"
    state = {
        "stalled_cleanup": {
            "abc": {"name": "Example Torrent", "first_seen_stalled": 123}
        }
    }

    save_state(state_path, state)

    assert state_path.exists()
    assert not state_path.with_suffix(".json.tmp").exists()
    assert load_state(state_path) == state


def test_load_state_returns_empty_mapping_for_missing_file(tmp_path: Path) -> None:
    assert load_state(tmp_path / "missing.json") == {}


def test_load_state_rejects_non_object_root(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('["not", "an", "object"]', encoding="utf-8")

    with pytest.raises(ValueError, match="state file root must be an object"):
        load_state(state_path)
