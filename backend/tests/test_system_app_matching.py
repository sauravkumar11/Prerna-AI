# -*- coding: utf-8 -*-
"""Tests for tools.system_tool.open_app's fuzzy matching — fixed the real
bug where "Microsoft Store" didn't match the registered "store" mapping
because only exact key lookup was used."""

import tools.system_tool as system_tool


def test_exact_match_still_works(monkeypatch):
    calls = []
    monkeypatch.setattr(system_tool.subprocess, "Popen", lambda cmd, shell=True: calls.append(cmd))
    result = system_tool.open_app("notepad")
    assert result.success
    assert calls  # a command was actually launched


def test_fuzzy_match_microsoft_store_to_store_mapping(monkeypatch):
    calls = []
    monkeypatch.setattr(system_tool.subprocess, "Popen", lambda cmd, shell=True: calls.append(cmd))
    result = system_tool.open_app("microsoft store")
    assert result.success
    assert calls == [system_tool.WINDOWS_APPS["store"]]


def test_fuzzy_match_windows_store_variant(monkeypatch):
    calls = []
    monkeypatch.setattr(system_tool.subprocess, "Popen", lambda cmd, shell=True: calls.append(cmd))
    result = system_tool.open_app("windows store")
    assert result.success
    assert calls == [system_tool.WINDOWS_APPS["store"]]


def test_unmapped_app_fails_honestly_without_launching_anything(monkeypatch):
    calls = []
    monkeypatch.setattr(system_tool.subprocess, "Popen", lambda cmd, shell=True: calls.append(cmd))
    result = system_tool.open_app("some random app that does not exist")
    assert not result.success
    assert "don't have" in result.message.lower()
    assert not calls  # must NOT launch anything for an unmapped app
