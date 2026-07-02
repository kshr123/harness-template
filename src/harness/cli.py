"""ハーネスの CLI 入口（typer）。`uv run <コマンド>` で呼ぶ。

make は使わない（Windows 含むクロスプラットフォームのため実体は uv run）。
各コマンドは pyproject.toml の [project.scripts] で公開する。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from harness import checks, pm

# Windows コンソール（cp932）でも日本語・記号（✓✗✅）を出せるよう UTF-8 に固定。
# クロスプラットフォームの前提（make 非依存と同じ理由）。
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def _root() -> Path:
    return Path.cwd()


def status_main() -> None:
    """作業単位の木から STATUS.md を作り直す（自動算出・手書き禁止）。"""

    def _run(
        check: Annotated[bool, typer.Option(help="生成せず、最新かどうかだけ判定する")] = False,
    ) -> None:
        root = _root()
        content = pm.render_status(root)
        out = root / "STATUS.md"
        if check:
            actual = out.read_text(encoding="utf-8") if out.is_file() else ""
            if actual.strip() != content.strip():
                typer.echo("STATUS.md が最新でない（uv run status で作り直す）")
                raise typer.Exit(1)
            typer.echo("STATUS.md は最新")
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content + "\n", encoding="utf-8")
        typer.echo(f"生成: {out}")

    typer.run(_run)


def task_lint_main() -> None:
    """作業単位の検査。ID の重複・depends_on の指す先が無い、を失敗にする（終了コード 1）。"""

    root = _root()
    problems = pm.lint(root)
    errors = 0
    for p in problems:
        mark = "✗" if p.level == "error" else "・"
        typer.echo(f"{mark} {p.message}")
        if p.level == "error":
            errors += 1
    if errors:
        typer.echo(f"問題 {errors} 件（失敗）")
        # console_script 入口（typer.run を通さない）なので sys.exit で綺麗に終える。
        # typer.Exit を raise すると未捕捉で Traceback が出る（L-006）。
        sys.exit(1)
    typer.echo("問題なし（未分解・未割り当ては許容）")


def check_main() -> None:
    """共通の検証（fast/standard/full）。合否（成功/失敗）を返す。"""

    def _run(
        level: Annotated[str, typer.Option(help="fast | standard | full")] = "full",
    ) -> None:
        raise typer.Exit(checks.run_check(_root(), level))

    typer.run(_run)


def verify_main() -> None:
    """完了判定＝check full と同じ。すべて成功したら done にできる。"""

    sys.exit(checks.run_check(_root(), "full"))


def changelog_main() -> None:
    """CHANGELOG 生成（Phase 0 ではひな形。Conventional Commits から生成予定）。"""

    typer.echo("changelog: 未実装（Phase 0 骨格）。実装は開発ワークフローの段階で。")
