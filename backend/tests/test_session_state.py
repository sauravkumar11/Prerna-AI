# -*- coding: utf-8 -*-
"""Tests for agent.session's last_photo/last_screenshot tracking — the
explicit "what did I just save" state that lets "open that picture"
resolve to a real path instead of the LLM guessing a folder name from
prior chat text."""

import pytest

from agent import session
from agent.registry import ToolResult


@pytest.fixture(autouse=True)
def _clear_session():
    session.clear_session()
    yield
    session.clear_session()


def test_screenshot_updater_captures_real_path():
    session.update_from_action(
        "screenshot", "default", {},
        ToolResult(True, "Screenshot saved as x.png.", data={"path": "C:/screenshots/x.png"}),
    )
    assert session.get_session_state()["last_screenshot"] == "C:/screenshots/x.png"


def test_camera_updater_captures_confirmed_photo_path():
    session.update_from_action(
        "camera", "take_picture", {},
        ToolResult(True, "Photo taken!", data={"path": "C:/Pictures/Camera Roll/photo1.jpg"}),
    )
    state = session.get_session_state()
    assert state["last_photo"] == "C:/Pictures/Camera Roll/photo1.jpg"
    assert state["current_app"] == "Camera"


def test_camera_updater_does_not_store_an_unconfirmed_guess():
    # This is the exact case that caused the original bug: take_picture()
    # couldn't confirm a real file, so it only had a vague "saved_to"
    # folder hint. That must NOT be stored as if it were a real photo path
    # — doing so would just move the guessing from the LLM into session
    # state instead of actually fixing it.
    session.update_from_action(
        "camera", "take_picture", {},
        ToolResult(True, "Photo taken, unsure where.", data={"saved_to": "C:/Pictures/Camera Roll"}),
    )
    assert session.get_session_state()["last_photo"] is None


def test_failed_action_never_updates_session_state():
    session.update_from_action(
        "screenshot", "default", {},
        ToolResult(False, "Something went wrong.", data={"path": "C:/should/not/be/stored.png"}),
    )
    assert session.get_session_state()["last_screenshot"] is None


def test_unrelated_tool_leaves_photo_and_screenshot_state_untouched():
    session.update_from_action(
        "camera", "take_picture", {},
        ToolResult(True, "Photo taken!", data={"path": "C:/photo.jpg"}),
    )
    session.update_from_action("volume", "up", {}, ToolResult(True, "Volume up."))
    state = session.get_session_state()
    assert state["last_photo"] == "C:/photo.jpg"  # untouched by the unrelated volume action
