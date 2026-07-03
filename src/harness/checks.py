"""共通の検証コマンドの実体。

一つの入口（uv run check / verify）で、言語ツール（ruff/mypy/pytest）と
プロジェクト管理の決まりごと（参照チェック・完了↔検証の結びつけ）を走らせ、
合否（成功/失敗）を返す。CI もローカルもこの同じ入口を使う＝完了の定義を一致させる。
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from harness import issues, pm
from harness.ds import schema as ds_schema

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
    """プロジェクト管理の決まりごとを検査する。参照エラー・壊れた frontmatter・完了↔検証の欠落は失敗。

    STATUS.md は生成物（その都度 `uv run status` で作り直す・コミットしない）なので、
    ここで「生成物とソースの一致」は突き合わせない（古い生成物を理由に検証を落とさない）。
    """

    ok = True
    problems = pm.lint(root) + pm.spec_lint(root) + issues.run_checks(root) + ds_schema.data_lint(root)
    for p in problems:
        mark = "✗" if p.level == "error" else "・"
        print(f"  {mark} {p.message}")
        if p.level == "error":
            ok = False
    if ok:
        print("  ○ プロジェクト管理の検査（参照チェック・完了↔検証・課題の整合・テーブル定義）")
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
            # pytest は「選んだ目印に該当するテストが 1 件も無い」を終了コード 5 で表す。
            # 段階×目印の設計上、その層のテストがまだ無いのは失敗ではない（付け忘れは conftest の
            # 目印ガードが別途止める）。5 だけは成功として扱い、それ以外の非 0 は失敗にする。
            if result.returncode == 5 and cmd[:1] == ["pytest"]:
                print("    （この目印に該当するテストは無し＝合格）")
                continue
            ok = False

    print("成功（すべて通過）" if ok else "失敗（未通過あり）")
    return 0 if ok else 1
