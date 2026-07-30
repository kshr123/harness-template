"""Chrome ロケータ（tests/_headless）の構成テスト。

実ブラウザの起動は test_deliver_browser が担う。ここは「どの OS でも Chrome を見つけられる構成か」を、
Chrome の有無に依らず（当マシンで）確かめる＝macOS/Windows の既定パスを消す退行を止める。
"""

from __future__ import annotations

import _headless  # tests/ は sys.path に載る（prepend import）＝素の名前で取り込める
import pytest

pytestmark = pytest.mark.unit


def test_chrome_locator_covers_mac_and_windows() -> None:
    """既定パスに macOS（.app）と Windows（chrome.exe）の両方があり、Linux は PATH 名で拾う。"""
    paths = _headless._APP_PATHS
    assert any(p.endswith(".app/Contents/MacOS/Google Chrome") for p in paths), "macOS の Chrome パスが無い"
    assert any(p.lower().endswith("chrome.exe") for p in paths), "Windows の Chrome パスが無い"
    assert "google-chrome" in _headless._PATH_NAMES, "Linux の PATH 名が無い"
