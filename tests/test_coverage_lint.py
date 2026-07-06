"""coverage_lint のテスト：CLI コマンドの導線（スキル/正本 docs からの到達可能性）検査。

期待値はすべて一時プロジェクトの構成（どのコマンドを置き・どこに導線を書くか）から導く。
最後の 1 本は現リポに対する回帰の番人（全コマンドが導線を持つこと＝以後の導線忘れを止める）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import coverage_lint

REPO_ROOT = Path(__file__).resolve().parents[1]

# ast 解析の対象（import はされない＝typer 実体は不要。装飾子の形だけが本物と同じであればよい）。
ORPHAN_CLI = (
    "import typer\n"
    "\n"
    "data_app = typer.Typer()\n"
    "\n"
    '@data_app.command("_orphan")\n'
    "def _orphan() -> None:\n"
    '    """導線の無いコマンド（テスト用）。"""\n'
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in coverage_lint.run_checks(root) if p.level == "error"]


# --- 検出：導線の無いコマンドは error ---


@pytest.mark.unit
def test_orphan_command_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "src/harness/x/cli.py", ORPHAN_CLI)
    _write(tmp_path, ".claude/skills/foo/SKILL.md", "このスキルは _orphan に触れない。\n")
    errors = _errors(tmp_path)
    assert any("data _orphan" in m and "src/harness/x/cli.py" in m for m in errors)


@pytest.mark.unit
def test_mention_in_skill_makes_command_reachable(tmp_path: Path) -> None:
    _write(tmp_path, "src/harness/x/cli.py", ORPHAN_CLI)
    _write(tmp_path, ".claude/skills/foo/SKILL.md", "一覧は `uv run data _orphan` を見る。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_exempt_token_suppresses_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "src/harness/x/cli.py", ORPHAN_CLI)
    monkeypatch.setitem(coverage_lint._EXEMPT, "data _orphan", "テスト用の内部コマンド（導線不要の例）。")
    assert _errors(tmp_path) == []


# --- コーパスの範囲：正本 docs は直下のみ（非再帰）・AGENTS/README も導線になる ---


@pytest.mark.unit
def test_docs_corpus_is_top_level_only(tmp_path: Path) -> None:
    _write(tmp_path, "src/harness/x/cli.py", ORPHAN_CLI)
    # 下層（docs/notes/…）への言及は導線に数えない → error のまま。
    _write(tmp_path, "docs/notes/deep.md", "`uv run data _orphan` の説明（下層＝正本ではない）。\n")
    assert any("data _orphan" in m for m in _errors(tmp_path))
    # 直下（docs/*.md）への言及は導線 → 消える。
    _write(tmp_path, "docs/top.md", "`uv run data _orphan` の説明（正本）。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_agents_md_and_readme_are_corpus(tmp_path: Path) -> None:
    _write(tmp_path, "src/harness/x/cli.py", ORPHAN_CLI)
    _write(tmp_path, "AGENTS.md", "検査は `uv run data _orphan` で行う。\n")
    assert _errors(tmp_path) == []


# --- 抽出：name == 接頭辞 は素の接頭辞トークン（serve の形） ---


@pytest.mark.unit
def test_name_equal_to_prefix_yields_bare_token(tmp_path: Path) -> None:
    cli = 'import typer\n\nserve_app = typer.Typer()\n\n@serve_app.command("serve")\ndef _serve() -> None:\n    pass\n'
    path = tmp_path / "cli.py"
    path.write_text(cli, encoding="utf-8")
    assert coverage_lint._command_tokens(path) == ["serve"]


@pytest.mark.unit
def test_non_app_variables_and_dynamic_names_are_not_extracted(tmp_path: Path) -> None:
    # `_app` で終わらない変数の .command と、文字列リテラルでない名前は保守的に拾わない。
    cli = (
        "import typer\n"
        "runner = object()\n"
        "x_app = typer.Typer()\n"
        "name = '_dyn'\n"
        '@runner.command("not_a_cli")\n'
        "def _a() -> None: ...\n"
        "@x_app.command(name)\n"
        "def _b() -> None: ...\n"
    )
    path = tmp_path / "cli.py"
    path.write_text(cli, encoding="utf-8")
    assert coverage_lint._command_tokens(path) == []


# --- 免除リストの規約：理由（値）は空でない文字列が必須 ---


@pytest.mark.unit
def test_every_exempt_reason_is_nonempty() -> None:
    for token, reason in coverage_lint._EXEMPT.items():
        assert isinstance(reason, str) and reason.strip(), f"_EXEMPT[{token!r}] の理由が空"


@pytest.mark.unit
def test_blank_exempt_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(coverage_lint._EXEMPT, "data _orphan", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        coverage_lint.run_checks(tmp_path)


# --- 配線：PM_CHECKS（verify の中核検査列）に載っている（外すと導線忘れが検出されなくなる） ---


@pytest.mark.unit
def test_coverage_lint_is_wired_into_pm_checks() -> None:
    from harness import checks

    assert coverage_lint.run_checks in checks.PM_CHECKS


# --- 回帰の番人：現リポの全コマンドが導線を持つ（以後の導線忘れを止める） ---


@pytest.mark.integration
def test_real_repo_all_cli_commands_are_reachable() -> None:
    errors = [p for p in coverage_lint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]
