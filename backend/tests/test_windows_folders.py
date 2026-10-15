"""
Tests for utils/windows_folders.py (v1.2.1 Bug 1 fix).

The real SHGetKnownFolderPath call only works on Windows, so these tests
mock it out to verify the *logic* (alias resolution, fallback behavior,
caching) on any platform. The one thing these tests cannot verify is that
the real Win32 call actually returns correct, OneDrive-aware paths on a
live Windows machine — that must be confirmed by hand once, per the
handoff doc's own caveat.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))
import windows_folders as wf  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    wf.clear_cache()
    yield
    wf.clear_cache()


class TestIsSpecialFolderName:
    def test_recognizes_desktop(self):
        assert wf.is_special_folder_name("desktop")

    def test_recognizes_case_insensitive(self):
        assert wf.is_special_folder_name("DeskTop")

    def test_recognizes_alias(self):
        assert wf.is_special_folder_name("download")  # singular alias

    def test_rejects_unrelated_name(self):
        assert not wf.is_special_folder_name("saurav")

    def test_rejects_empty_string(self):
        assert not wf.is_special_folder_name("")


class TestGetSpecialFolderWithMockedWin32:
    def test_desktop_uses_win32_result_when_available(self, tmp_path):
        fake_desktop = tmp_path / "OneDrive" / "Desktop"
        fake_desktop.mkdir(parents=True)
        with patch.object(wf, "_sh_get_known_folder_path", return_value=fake_desktop):
            result = wf.get_special_folder("desktop")
        assert result == fake_desktop

    def test_onedrive_redirected_desktop_is_respected(self, tmp_path):
        # This is the exact real-world case a naive %USERPROFILE%\Desktop
        # guess gets wrong: OneDrive moves Desktop under the OneDrive folder.
        redirected = tmp_path / "OneDrive" / "Desktop"
        redirected.mkdir(parents=True)
        with patch.object(wf, "_sh_get_known_folder_path", return_value=redirected):
            result = wf.get_special_folder("desktop")
        assert "OneDrive" in str(result)

    def test_falls_back_when_win32_call_fails(self, monkeypatch, tmp_path):
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        with patch.object(wf, "_sh_get_known_folder_path", return_value=None):
            result = wf.get_special_folder("desktop")
        assert result == tmp_path / "Desktop"

    def test_unrecognized_name_returns_none(self):
        with patch.object(wf, "_sh_get_known_folder_path", return_value=None):
            assert wf.get_special_folder("not_a_real_folder") is None

    def test_alias_resolves_to_same_result_as_canonical_name(self, tmp_path):
        fake = tmp_path / "Downloads"
        fake.mkdir()
        with patch.object(wf, "_sh_get_known_folder_path", return_value=fake):
            a = wf.get_special_folder("downloads")
            wf.clear_cache()
            b = wf.get_special_folder("download")
        assert a == b

    def test_result_is_cached_across_calls(self, tmp_path):
        fake = tmp_path / "Desktop"
        fake.mkdir()
        with patch.object(wf, "_sh_get_known_folder_path", return_value=fake) as mocked:
            wf.get_special_folder("desktop")
            wf.get_special_folder("desktop")
        assert mocked.call_count == 1  # second call hit the cache

    def test_clear_cache_forces_re_resolution(self, tmp_path):
        fake = tmp_path / "Desktop"
        fake.mkdir()
        with patch.object(wf, "_sh_get_known_folder_path", return_value=fake) as mocked:
            wf.get_special_folder("desktop")
            wf.clear_cache()
            wf.get_special_folder("desktop")
        assert mocked.call_count == 2

    @pytest.mark.parametrize(
        "key", ["documents", "pictures", "videos", "music", "appdata_roaming", "appdata_local"]
    )
    def test_all_known_folders_resolve_without_error(self, key, tmp_path):
        fake = tmp_path / key
        fake.mkdir()
        with patch.object(wf, "_sh_get_known_folder_path", return_value=fake):
            assert wf.get_special_folder(key) == fake


class TestFallbackPath:
    def test_fallback_uses_appdata_env_var_when_set(self, monkeypatch, tmp_path):
        fake_appdata = tmp_path / "Roaming"
        monkeypatch.setenv("APPDATA", str(fake_appdata))
        assert wf._fallback_path("appdata_roaming") == fake_appdata

    def test_fallback_constructs_appdata_when_env_var_missing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        assert wf._fallback_path("appdata_roaming") == tmp_path / "AppData" / "Roaming"

    def test_fallback_uses_userprofile_for_desktop(self, monkeypatch, tmp_path):
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        assert wf._fallback_path("desktop") == tmp_path / "Desktop"