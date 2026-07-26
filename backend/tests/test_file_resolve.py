# -*- coding: utf-8 -*-
"""Tests for tools.file_tool._resolve_existing — the fallback search that
fixed "open the screenshot/photo I just took" failing with WinError 2
because the planner only had a filename (or a guessed folder name), not
the tool's real save directory."""

from pathlib import Path

import tools.file_tool as file_tool


def test_resolves_directly_when_the_literal_path_exists(tmp_path):
    real_file = tmp_path / "notes.txt"
    real_file.write_text("hi")
    resolved = file_tool._resolve_existing(str(real_file))
    assert resolved == real_file


def test_falls_back_to_search_dirs_for_a_bare_filename(tmp_path, monkeypatch):
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    target = screenshots_dir / "screenshot_20260719_100824.png"
    target.write_bytes(b"fake png")

    # Point the search dirs at our temp layout instead of the real
    # SCREENSHOT_DIR/Pictures/etc, so this test doesn't touch the real filesystem.
    monkeypatch.setattr(file_tool, "_SEARCH_DIRS", [screenshots_dir, tmp_path / "nonexistent"])

    resolved = file_tool._resolve_existing("screenshot_20260719_100824.png")
    assert resolved == target


def test_falls_back_even_when_a_guessed_directory_prefix_was_given(tmp_path, monkeypatch):
    # This is the exact real-world bug: the planner passed the literal
    # multi-segment guess "Pictures\Camera Roll" as a path (a folder name,
    # not a real filename) when it only had a folder mentioned in a
    # previous reply to go on. The fix must not skip the search just
    # because the given path LOOKS like it has a directory component.
    camera_roll = tmp_path / "Pictures" / "Camera Roll"
    camera_roll.mkdir(parents=True)
    photo = camera_roll / "WIN_20260719_photo.jpg"
    photo.write_bytes(b"fake jpg")

    monkeypatch.setattr(file_tool, "_SEARCH_DIRS", [camera_roll])

    # The planner hallucinated a path with a real photo's folder but the
    # wrong/no filename — closest realistic case is a bare name that
    # happens to match something in the search dir.
    resolved = file_tool._resolve_existing("WIN_20260719_photo.jpg")
    assert resolved == photo


def test_returns_naive_path_unresolved_when_nothing_matches_anywhere(tmp_path, monkeypatch):
    monkeypatch.setattr(file_tool, "_SEARCH_DIRS", [tmp_path / "empty"])
    missing = tmp_path / "totally_missing.png"
    resolved = file_tool._resolve_existing(str(missing))
    assert resolved == missing
    assert not resolved.exists()


def test_known_limitation_a_bare_folder_name_guess_still_cannot_resolve(tmp_path, monkeypatch):
    # Honest documentation of a residual limitation: if the planner passes
    # a FOLDER name with no real filename (e.g. the literal historical bug,
    # "Pictures\Camera Roll"), there's no file actually named "Camera Roll"
    # to find — _resolve_existing searches by filename, not by guessing
    # "the newest file in this folder". This case is fixed differently, at
    # the source: agent.session now tracks the real last_photo/last_screenshot
    # path so the planner has an actual filename to pass instead of a
    # guessed folder name. This test exists so that fix doesn't silently
    # regress into "well _resolve_existing will just handle it anyway".
    camera_roll = tmp_path / "Pictures" / "Camera Roll"
    camera_roll.mkdir(parents=True)
    (camera_roll / "an_actual_photo.jpg").write_bytes(b"data")

    monkeypatch.setattr(file_tool, "_SEARCH_DIRS", [camera_roll])
    resolved = file_tool._resolve_existing("Pictures\\Camera Roll")
    assert not resolved.exists()  # correctly still unresolved — this is NOT what fixes that bug


def test_search_order_prefers_earlier_directories(tmp_path, monkeypatch):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "shared.txt").write_text("from a")
    (dir_b / "shared.txt").write_text("from b")

    monkeypatch.setattr(file_tool, "_SEARCH_DIRS", [dir_a, dir_b])
    resolved = file_tool._resolve_existing("shared.txt")
    assert resolved == dir_a / "shared.txt"
