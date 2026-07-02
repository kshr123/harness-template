"""共通の検証コマンドの実体。

一つの入口（uv run check / verify）で、言語ツール（ruff/mypy/pytest）と
プロジェクト管理の決まりごと（参照チェック・STATUS 再生成一致）を走らせ、
合否（成功/失敗）を返す。CI もローカルもこの同じ入口を使う＝完了の定義を一致させる。
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from harness import pm

# レベル：fast（フック相当）→ standard（pre-commit 相当）→ full（CI・done）。
LEVELS = ("fast", "standard", "full")


def _load_commands(root: Path, level: str) -> list[list[str]]:
    """checks.toml から、そのレベルまでに走らせる言語ツールのコマンドを集める。"""

    path = root / "checks.toml"
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    commands: list[list[str]] = []
    for lv in LEVELS[: LEVELS.index(level) + 1]:
        for cmd in data.get(lv, {}).get("commands", []):
            commands.append(cmd)
    return commands


def _pm_checks(root: Path) -> bool:
    """プロジェクト管理の決まりごとを検査する。参照エラー・壊れた frontmatter・STATUS 不一致は失敗。"""

    ok = True
    problems = pm.lint(root) + pm.spec_lint(root)
    for p in problems:
        mark = "✗" if p.level == "error" else "・"
        print(f"  {mark} {p.message}")
        if p.level == "error":
            ok = False

    # STATUS.md 再生成一致（手書き・陳腐化を赤にする）。
    status_path = root / "tasks" / "STATUS.md"
    expected = pm.render_status(root)
    actual = status_path.read_text(encoding="utf-8") if status_path.is_file() else ""
    if actual.strip() != expected.strip():
        print("  ✗ tasks/STATUS.md が最新でない（uv run status で作り直すこと）")
        ok = False
    else:
        print("  ○ プロジェクト管理の検査（参照チェック・STATUS 一致）")
    return ok


def run_check(root: Path, level: str = "full") -> int:
    """検証を実行し、終了コードを返す（0=成功・非0=失敗）。"""

    if level not in LEVELS:
        print(f"不明なレベル: {level}（{', '.join(LEVELS)} のいずれか）")
        return 2

    print(f"[check level={level}]")
    ok = _pm_checks(root)

    for cmd in _load_commands(root, level):
        print(f"  → {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=root)
        if result.returncode != 0:
            ok = False

    print("成功（すべて通過）" if ok else "失敗（未通過あり）")
    return 0 if ok else 1
