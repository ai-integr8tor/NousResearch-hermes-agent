"""Regression tests for Linux cua-driver window metadata quirks (#58026)."""

from __future__ import annotations

from unittest.mock import patch

ISSUE_58026_WINDOWS = [
    {
        "app_name": "ding",
        "pid": 4294,
        "window_id": 33554439,
        "title": "Desktop Icons 1",
        "is_on_screen": True,
        "z_index": 0,
    },
    {
        "app_name": "",
        "pid": 1816017,
        "window_id": 60817412,
        "title": "zcode",
        "is_on_screen": True,
        "z_index": 0,
    },
    {
        "app_name": "",
        "pid": 1877178,
        "window_id": 84043449,
        "title": "xr@10:~/hermes",
        "is_on_screen": True,
        "z_index": 0,
    },
    {
        "app_name": "",
        "pid": 1877178,
        "window_id": 84065715,
        "title": "HERMES-CU",
        "is_on_screen": True,
        "z_index": 0,
    },
]


def _normalized_windows(raw=ISSUE_58026_WINDOWS):
    from tools.computer_use.cua_backend import _window_from_list_windows_entry

    return [_window_from_list_windows_entry(w) for w in raw]


def test_linux_null_is_on_screen_is_treated_as_unknown_not_offscreen():
    raw = [
        {
            "app_name": "",
            "pid": 1,
            "window_id": 10,
            "title": "Chrome",
            "is_on_screen": None,
            "z_index": 0,
        },
        {
            "app_name": "",
            "pid": 2,
            "window_id": 20,
            "title": "Hidden",
            "is_on_screen": False,
            "z_index": 0,
        },
    ]
    windows = _normalized_windows(raw)

    assert windows[0]["off_screen"] is False
    assert windows[1]["off_screen"] is True


def test_linux_empty_app_name_falls_back_to_window_title_for_app_filter():
    from tools.computer_use.cua_backend import _window_matches_app_filter

    chrome = _normalized_windows([
        {
            "app_name": "",
            "pid": 1,
            "window_id": 10,
            "title": "Guides — OMC Docs - Google Chrome",
            "is_on_screen": True,
            "z_index": 0,
        }
    ])[0]

    assert _window_matches_app_filter(chrome, "chrome") is True
    assert _window_matches_app_filter(chrome, "firefox") is False


def test_default_capture_skips_desktop_icons_window():
    from tools.computer_use.cua_backend import _select_capture_target

    with patch("tools.computer_use.cua_backend.sys.platform", "linux"), \
         patch("tools.computer_use.cua_backend._linux_x11_active_window_id", return_value=None):
        target = _select_capture_target(_normalized_windows(), app_requested=False)

    assert target["title"] == "zcode"
    assert target["window_id"] == 60817412


def test_default_capture_prefers_x11_active_window_when_z_index_tied():
    from tools.computer_use.cua_backend import _select_capture_target

    with patch("tools.computer_use.cua_backend.sys.platform", "linux"), \
         patch(
             "tools.computer_use.cua_backend._linux_x11_active_window_id",
             return_value=84043449,
         ):
        target = _select_capture_target(_normalized_windows(), app_requested=False)

    assert target["title"] == "xr@10:~/hermes"
    assert target["window_id"] == 84043449


def test_explicit_app_capture_preserves_filtered_target():
    from tools.computer_use.cua_backend import _select_capture_target

    terminal = _normalized_windows()[2]

    with patch("tools.computer_use.cua_backend.sys.platform", "linux"):
        target = _select_capture_target([terminal], app_requested=True)

    assert target == terminal


def test_is_linux_shell_helper_window_matches_gnome_ding():
    from tools.computer_use.cua_backend import _is_linux_shell_helper_window

    with patch("tools.computer_use.cua_backend.sys.platform", "linux"):
        assert _is_linux_shell_helper_window(_normalized_windows()[0]) is True
        assert _is_linux_shell_helper_window(_normalized_windows()[1]) is False


def test_focus_app_matches_linux_window_title_when_app_name_empty():
    from unittest.mock import MagicMock

    from tools.computer_use.cua_backend import CuaDriverBackend

    backend = CuaDriverBackend()
    backend._session = MagicMock()
    backend._session.call_tool.return_value = {
        "data": "",
        "images": [],
        "structuredContent": {
            "windows": [
                {
                    "app_name": "",
                    "pid": 11715,
                    "window_id": 81790890,
                    "title": "Guides — OMC Docs - Google Chrome",
                    "is_on_screen": None,
                    "z_index": 0,
                }
            ]
        },
        "isError": False,
    }

    res = backend.focus_app("Chrome")

    assert res.ok is True
    assert backend._active_pid == 11715
    assert backend._active_window_id == 81790890
