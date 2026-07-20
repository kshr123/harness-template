"""coverage_lint のテスト：CLI コマンドの導線（スキル/正本 docs からの到達可能性）検査。

期待値はすべて一時プロジェクトの構成（どのコマンドを置き・どこに導線を書くか）から導く。
最後の 1 本は現リポに対する回帰テスト（全コマンドが導線を持つこと＝以後の導線忘れを止める）。
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


# --- 語境界：1 語コマンドの単なる出現・部分文字列は到達とみなさない（T-0201） ---


# `serve_app.command("serve")` → 素の "serve" トークン（1 語コマンドの代表例）。
BARE_SERVE_CLI = (
    'import typer\n\nserve_app = typer.Typer()\n\n@serve_app.command("serve")\ndef _s() -> None:\n    pass\n'
)


@pytest.mark.unit
def test_bare_mention_without_uv_run_is_not_reachable(tmp_path: Path) -> None:
    # "serve" という語が本文にただ出現するだけ（`uv run` の後ろではない）→ 導線としては数えない。
    _write(tmp_path, "src/harness/x/cli.py", BARE_SERVE_CLI)
    _write(tmp_path, "docs/top.md", "モデルを配信（serve）する仕組みについて説明する。\n")
    assert any("'serve'" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_negated_sentence_mention_is_not_reachable(tmp_path: Path) -> None:
    # 否定文中の出現（「触れない」）も、`uv run` の後ろに置かれていなければ導線として数えない。
    _write(tmp_path, "src/harness/x/cli.py", ORPHAN_CLI)
    _write(tmp_path, "docs/top.md", "data _orphan を直接叩かない。\n")
    assert any("data _orphan" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_substring_of_longer_word_does_not_falsely_match(tmp_path: Path) -> None:
    # "deserve" や "servex" のように "serve" を部分文字列として含む語には誤ってヒットしない。
    _write(tmp_path, "src/harness/x/cli.py", BARE_SERVE_CLI)
    _write(tmp_path, "docs/top.md", "この設計は `uv run servex` という架空のコマンドと deserve という英単語を含む。\n")
    assert any("'serve'" in m for m in _errors(tmp_path))
    # 本物の `uv run serve` が現れれば到達する（境界チェックが厳しすぎて正しい案内まで弾かないことの確認）。
    _write(tmp_path, "docs/bottom.md", "配信は `uv run serve --help` から始める。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_uv_run_prefixed_bare_token_is_reachable(tmp_path: Path) -> None:
    _write(tmp_path, "src/harness/x/cli.py", BARE_SERVE_CLI)
    _write(tmp_path, "docs/top.md", "配信は `uv run serve --help` を見る。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_hyphenated_command_word_boundary(tmp_path: Path) -> None:
    # ハイフンを含むコマンド名（[project.scripts] の task-lint 相当）でも語境界が正しく効くこと。
    pyproject_with_foo_lint = '[project]\nname = "x"\nversion = "0"\n\n[project.scripts]\nfoo-lint = "x:main"\n'
    _write(tmp_path, "pyproject.toml", pyproject_with_foo_lint)
    # 別語の一部（foo-linter）に誤ってヒットしない。
    _write(tmp_path, "docs/top.md", "`uv run foo-linter` という別コマンドの説明。\n")
    assert any("foo-lint" in m for m in _errors(tmp_path))
    # 本物の `uv run foo-lint` は到達する。
    _write(tmp_path, "docs/bottom.md", "検査は `uv run foo-lint` で行う。\n")
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


# --- [project.scripts] 走査：plain main のコマンドも導線検査の対象になる ---

# tomllib で読む最小の pyproject.toml。`frob` は導線を書かない限り未到達（構成から期待値を導く）。
PYPROJECT_WITH_FROB = '[project]\nname = "x"\nversion = "0"\n\n[project.scripts]\nfrob = "x:main"\n'


@pytest.mark.unit
def test_orphan_project_script_is_error_until_linked(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", PYPROJECT_WITH_FROB)
    _write(tmp_path, ".claude/skills/foo/SKILL.md", "このスキルは対象コマンドに触れない。\n")
    # 導線ゼロ → error（メッセージで frob を名指しし、pyproject.toml 由来と分かる）。
    errors = _errors(tmp_path)
    assert any("frob" in m and "pyproject.toml" in m for m in errors)
    # スキルに導線を 1 行足す → error が消える。
    _write(tmp_path, ".claude/skills/foo/SKILL.md", "検査は `uv run frob` で行う。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_orphan_project_script_reachable_via_agents_md(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", PYPROJECT_WITH_FROB)
    _write(tmp_path, "AGENTS.md", "検査は `uv run frob` で行う。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_exempt_project_script_suppresses_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "pyproject.toml", PYPROJECT_WITH_FROB)
    monkeypatch.setitem(coverage_lint._EXEMPT, "frob", "テスト用の内部コマンド（導線不要の例）。")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_blank_exempt_reason_for_script_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "pyproject.toml", PYPROJECT_WITH_FROB)
    monkeypatch.setitem(coverage_lint._EXEMPT, "frob", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        coverage_lint.run_checks(tmp_path)


@pytest.mark.unit
def test_missing_pyproject_is_silently_skipped(tmp_path: Path) -> None:
    # pyproject.toml が無いプロジェクト（既存テスト群と同じ形）でも scripts 走査は静かに読み飛ばす。
    _write(tmp_path, "src/harness/x/cli.py", ORPHAN_CLI)
    _write(tmp_path, ".claude/skills/foo/SKILL.md", "一覧は `uv run data _orphan` を見る。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_same_token_from_typer_and_scripts_is_reported_once(tmp_path: Path) -> None:
    # typer の `data_app.command("data")`（name == 接頭辞 → 素の "data"）と scripts の `data` が同一トークン。
    cli = 'import typer\n\ndata_app = typer.Typer()\n\n@data_app.command("data")\ndef _d() -> None:\n    pass\n'
    _write(tmp_path, "src/harness/x/cli.py", cli)
    _write(tmp_path, "pyproject.toml", '[project]\nname = "x"\nversion = "0"\n\n[project.scripts]\ndata = "x:main"\n')
    errors = _errors(tmp_path)
    assert len(errors) == 1  # 両経路が拾っても同じ token の error は 1 回だけ
    assert "data" in errors[0]


@pytest.mark.unit
def test_changelog_is_exempt_with_reason() -> None:
    # changelog は Phase 0 の未実装骨格（cli.py は「未実装」を echo するだけ）。理由つき免除で扱う。
    reason = coverage_lint._EXEMPT["changelog"]
    assert "未実装" in reason and "免除を外す" in reason


# --- 配線：INVARIANT_CHECKS（verify の中核検査列）に載っている（外すと導線忘れが検出されなくなる） ---


@pytest.mark.unit
def test_coverage_lint_is_wired_into_invariant_checks() -> None:
    from harness import checks

    assert coverage_lint.run_checks in checks.INVARIANT_CHECKS


# --- 回帰テスト：現リポの全コマンドが導線を持つ（以後の導線忘れを止める） ---


@pytest.mark.integration
def test_real_repo_all_cli_commands_are_reachable() -> None:
    errors = [p for p in coverage_lint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]
