"""Tests for memory.memory_manager function-based API."""

from __future__ import annotations

import json
from pathlib import Path

import memory.memory_manager as mm


def _configure_paths(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mm, "MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(mm, "LOG_FILE", tmp_path / "activity_log.json")
    monkeypatch.setattr(mm, "CONVERSATION_FILE", tmp_path / "conversation_log.json")
    (tmp_path / "memory.json").write_text('{"profile": {}, "contacts": {}, "preferences": {}, "habits": []}', encoding="utf-8")
    (tmp_path / "activity_log.json").write_text("[]", encoding="utf-8")
    (tmp_path / "conversation_log.json").write_text("[]", encoding="utf-8")
    mm._invalidate_cache()


def test_save_memory_round_trip(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    payload = {"profile": {"name": "Saurav"}, "contacts": {}, "preferences": {}, "habits": []}

    mm.save_memory(payload)
    loaded = mm.load_memory()

    assert loaded["profile"]["name"] == "Saurav"


def test_log_activity_persists_entry(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)

    mm.log_activity("system.lock", success=True, details="ok")
    entries = mm.get_recent_actions(5)

    assert len(entries) == 1
    assert entries[0]["action"] == "system.lock"
    assert entries[0]["success"] is True


def test_add_conversation_turn_persists_and_limits(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(mm, "MAX_CONVERSATION_TURNS", 2)

    mm.add_conversation_turn("user", "one")
    mm.add_conversation_turn("assistant", "two")
    mm.add_conversation_turn("user", "three")

    turns = mm.get_conversation_history(10)
    assert len(turns) == 2
    assert turns[0]["content"] == "two"
    assert turns[1]["content"] == "three"


def test_load_memory_uses_cache_until_invalidated(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)

    first = mm.load_memory()
    assert first["profile"] == {}

    mm.MEMORY_FILE.write_text('{"profile": {"name": "changed"}}', encoding="utf-8")
    cached = mm.load_memory()
    assert cached.get("profile", {}).get("name") != "changed"

    mm._invalidate_cache()
    refreshed = mm.load_memory()
    assert refreshed["profile"]["name"] == "changed"
