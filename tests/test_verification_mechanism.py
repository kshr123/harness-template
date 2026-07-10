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
from harness.testing import PYRAMID, markers_in_expr, unmarked

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


# ---- checks.toml の不変条件（起動時 precondition。T-0198 / EP-32） --------------------------------
#
# 番人が門の内側に住まないことの担保：ここで確かめる `_verify_checks_config` は pytest のテストではなく
# `run_check` の冒頭で無条件に呼ばれる関数（マーカーで deselect され得ない）。下の各テストは、その関数を
# 直接呼ぶ（マーカー選択に依存しない層）＋ `run_check` が pytest サブプロセスに到達する前に落ちること
# （＝マーカー選択の上流で効くこと）を確かめる。tmp_path 上に checks.toml／pyproject.toml を組み立てるので、
# 実リポジトリの値はハードコードしない（期待値は組み立てた入力から導ける）。


def _write_repo(tmp_path: Path, *, fast: str, standard: str, full: str) -> Path:
    """tmp_path に checks.toml と、テストの層＋slow を登録した pyproject.toml を置く。

    登録マーカーは testing.PYRAMID（unit/integration/e2e）＋slow から機械的に作る（実 pyproject を仮定しない）。
    """
    (tmp_path / "checks.toml").write_text(
        f"[fast]\ncommands = [{fast}]\n[standard]\ncommands = [{standard}]\n[full]\ncommands = [{full}]\n",
        encoding="utf-8",
    )
    markers = ", ".join(f'"{name}: 層 {name}"' for name in (*PYRAMID, "slow"))
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.pytest.ini_options]\nmarkers = [{markers}]\n",
        encoding="utf-8",
    )
    return tmp_path


# 実リポジトリと同じ形の、正しい段階割り当て（各層が -m 式に一度ずつ現れ、ruff/mypy も揃う）。
_GOOD_FAST = "['ruff','format','--check','.'],['ruff','check','.'],['pytest','-q','-m','unit and not slow']"
_GOOD_STANDARD = "['mypy'],['pytest','-q','-m','integration and not slow']"
_GOOD_FULL = "['pytest','-q','-m','e2e and not slow']"


def test_checks_config_accepts_valid_config(tmp_path: Path) -> None:
    # 実物と同じ形（ruff/mypy 揃い・3 層すべて被覆）は素通りする＝正しい設定を拒まない。
    root = _write_repo(tmp_path, fast=_GOOD_FAST, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    checks._verify_checks_config(root)  # 例外を投げなければ合格


def test_checks_config_rejects_marker_typo(tmp_path: Path) -> None:
    # unit → unitt の綴り違い。unitt は pyproject の登録に無い（全 deselect で 0 件のまま緑になる経路）。
    typo_fast = _GOOD_FAST.replace("unit and not slow", "unitt and not slow")
    root = _write_repo(tmp_path, fast=typo_fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="unitt"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_missing_pytest_layer(tmp_path: Path) -> None:
    # pytest の行を丸ごと消す（ruff/mypy は残す）→ どの層も -m 式に現れず、層の被覆に失敗する。
    root = _write_repo(
        tmp_path,
        fast="['ruff','format','--check','.'],['ruff','check','.']",
        standard="['mypy']",
        full="",
    )
    with pytest.raises(ValueError):
        checks._verify_checks_config(root)


def test_checks_config_rejects_missing_ruff(tmp_path: Path) -> None:
    # ruff を消す（mypy・pytest は残す）→ 必須の言語検査を欠くので拒否。
    root = _write_repo(
        tmp_path,
        fast="['pytest','-q','-m','unit and not slow']",
        standard=_GOOD_STANDARD,
        full=_GOOD_FULL,
    )
    with pytest.raises(ValueError, match="ruff"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_missing_mypy(tmp_path: Path) -> None:
    # mypy を消す（ruff・pytest は残す）→ 必須の言語検査を欠くので拒否。
    root = _write_repo(
        tmp_path,
        fast=_GOOD_FAST,
        standard="['pytest','-q','-m','integration and not slow']",
        full=_GOOD_FULL,
    )
    with pytest.raises(ValueError, match="mypy"):
        checks._verify_checks_config(root)


def test_run_check_rejects_broken_config_before_pytest(tmp_path: Path) -> None:
    # 番人が門の内側に住まない証拠：壊れた checks.toml を与えた run_check は、pytest サブプロセスに
    # 到達する前（＝マーカー選択の上流・無条件の層）で ValueError を投げる。pytest が 1 件も走らなくても
    # 起動が拒否されることを、run_check を直接呼んで確かめる。
    typo_fast = _GOOD_FAST.replace("unit and not slow", "unitt and not slow")
    root = _write_repo(tmp_path, fast=typo_fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError):
        checks.run_check(root, "full")
