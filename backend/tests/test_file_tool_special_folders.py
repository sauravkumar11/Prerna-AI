"""
Integration tests for v1.2.1 Bug 1: file_tool.py's _safe_path(),
_search_dirs(), and open_shortcut() now resolve special-folder names via
utils.windows_folders instead of guessing relative to the working directory.
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools import file_tool  # noqa: E402


@pytest.fixture
def fake_desktop(tmp_path):
    d = tmp_path / "OneDrive" / "Desktop"
    d.mkdir(parents=True)
    return d


class TestSafePathSpecialFolders:
    def test_desktop_segment_resolves_via_win32_not_cwd(self, fake_desktop):
        with patch.object(file_tool, "get_special_folder", return_value=fake_desktop):
            result = file_tool._safe_path("Desktop/saurav")
        assert result == fake_desktop / "saurav"

    def test_onedrive_redirected_desktop_is_used(self, fake_desktop):
        with patch.object(file_tool, "get_special_folder", return_value=fake_desktop):
            result = file_tool._safe_path("Desktop/saurav")
        assert "OneDrive" in str(result)

    def test_alias_case_insensitive(self, fake_desktop):
        with patch.object(file_tool, "get_special_folder", return_value=fake_desktop), \
             patch.object(file_tool, "is_special_folder_name", return_value=True):
            result = file_tool._safe_path("desktop/saurav")
        assert result == fake_desktop / "saurav"

    def test_plain_relative_path_is_unaffected(self, tmp_path, monkeypatch):
        # A path that does NOT start with a special-folder name must resolve
        # exactly as it did before this fix - no regression to normal paths.
        monkeypatch.chdir(tmp_path)
        result = file_tool._safe_path("some_folder/some_file.txt")
        assert result == (tmp_path / "some_folder" / "some_file.txt").resolve()

    def test_absolute_path_is_unaffected(self, tmp_path):
        abs_path = str(tmp_path / "a" / "b.txt")
        result = file_tool._safe_path(abs_path)
        assert result == Path(abs_path).resolve()

    def test_drive_root_still_rejected(self):
        with pytest.raises(ValueError):
            file_tool._safe_path("C:\\")

    def test_bare_special_folder_with_no_subpath(self, fake_desktop):
        with patch.object(file_tool, "get_special_folder", return_value=fake_desktop):
            result = file_tool._safe_path("Desktop")
        assert result == fake_desktop


class TestOpenShortcut:
    def test_prefers_win32_resolution_over_config_shortcuts(self, fake_desktop):
        with patch.object(file_tool, "get_special_folder", return_value=fake_desktop), \
             patch.object(file_tool, "subprocess") as mock_subproc:
            result = file_tool.open_shortcut("desktop")
        assert result.success
        mock_subproc.Popen.assert_called_once_with(["explorer", str(fake_desktop)])

    def test_falls_back_to_config_shortcuts_dict_when_not_a_special_folder(self):
        with patch.object(file_tool, "get_special_folder", return_value=None), \
             patch.object(file_tool, "_SHORTCUTS", {"projects": Path("/some/projects")}), \
             patch.object(file_tool, "subprocess") as mock_subproc:
            result = file_tool.open_shortcut("projects")
        assert result.success
        mock_subproc.Popen.assert_called_once_with(["explorer", str(Path("/some/projects"))])

    def test_unknown_shortcut_fails_cleanly(self):
        with patch.object(file_tool, "get_special_folder", return_value=None), \
             patch.object(file_tool, "_SHORTCUTS", {}):
            result = file_tool.open_shortcut("nonexistent")
        assert not result.success