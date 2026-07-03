"""検証の仕組み（段階×目印）の部品テスト。

目印ガードの純粋関数を、構成から導ける入力で確かめる（実装をなぞらない）。
フック本体（conftest の pytest_collection_modifyitems）は、この関数が正しければ薄い包みなので、
「全テストが目印を持つ」ことはスイート全体が collect を通ること自体が裏付ける（無印を置けば collect で失敗する）。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from harness import checks
from harness.testing import markers_in_expr, unmarked

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]  # harness-template リポの根


def test_unmarked_detects_only_pyramid_missing() -> None:
    rows = [
        ("tests/a.py::t1", {"unit"}),
        ("tests/b.py::t2", set()),  # 目印なし＝迷子
        ("tests/c.py::t3", {"integration", "slow"}),
        ("tests/d.py::t4", {"slow"}),  # slow だけ＝ピラミッドの目印が無い＝迷子
    ]
    # 期待は入力の構成から直に導ける：ピラミッド(unit/integration/e2e)を持たない t2 と t4 だけ。
    assert unmarked(rows) == ["tests/b.py::t2", "tests/d.py::t4"]


def test_all_marked_returns_empty() -> None:
    rows = [("x::a", {"unit"}), ("x::b", {"e2e"})]
    assert unmarked(rows) == []


def test_load_commands_scopes_pytest_by_level(tmp_path: Path) -> None:
    # 段階（level）ごとに pytest の目印選択が変わり、full は累積で3層すべてを含むこと。
    (tmp_path / "checks.toml").write_text(
        "[fast]\ncommands = [['ruff','check','.'],['pytest','-q','-m','unit and not slow']]\n"
        "[standard]\ncommands = [['mypy'],['pytest','-q','-m','integration and not slow']]\n"
        "[full]\ncommands = [['pytest','-q','-m','e2e and not slow']]\n",
        encoding="utf-8",
    )
    fast = checks._load_commands(tmp_path, "fast")
    full = checks._load_commands(tmp_path, "full")
    assert ["pytest", "-q", "-m", "unit and not slow"] in fast
    assert ["pytest", "-q", "-m", "integration and not slow"] not in fast  # fast は unit だけ
    pytest_cmds = [c for c in full if c[:1] == ["pytest"]]
    assert len(pytest_cmds) == 3  # full は unit/integration/e2e の3つを累積で持つ


def test_markers_in_expr_extracts_names() -> None:
    # 論理演算子を除いたマーカー名だけを取り出す（入力の構成から導ける）。
    assert markers_in_expr("e2e and not slow") == {"e2e", "slow"}
    assert markers_in_expr("unit") == {"unit"}


def test_checks_toml_uses_only_registered_markers() -> None:
    # 実 checks.toml の -m 式が参照するマーカーが、pyproject に登録済みであること。
    # 綴り違い・改名で「全 deselect→テスト0件なのに合格（門番の空回り）」になるのを塞ぐ。
    checks_toml = tomllib.loads((_ROOT / "checks.toml").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    registered = {m.split(":")[0].strip() for m in pyproject["tool"]["pytest"]["ini_options"]["markers"]}
    used: set[str] = set()
    for level in checks_toml.values():
        for cmd in level.get("commands", []):
            if cmd[:1] == ["pytest"] and "-m" in cmd:
                used |= markers_in_expr(cmd[cmd.index("-m") + 1])
    assert used <= registered, f"checks.toml が未登録マーカーを使用: {sorted(used - registered)}"
    # 4 つの目印すべてが段階に接続されている（どれかが設定から抜け落ちていない）。
    assert used == {"unit", "integration", "e2e", "slow"}
