"""doclint のテスト：正本ドキュメントの参照（DEC/ISS/パス/コマンド）実在検査。

期待値はすべて一時プロジェクトの構成（何を置き・何を置かないか）から導く。
最後の 1 本は現リポの実 docs に対する回帰の番人（正本の参照が全部実在すること）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import doclint

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]


def _doc(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in doclint.run_checks(root) if p.level == "error"]


def _infos(root: Path) -> list[str]:
    # 未知コマンドは info（pm.Problem の "error"|"info" 規約。合否には効かせない＝環境由来の偽陽性回避）。
    return [p.message for p in doclint.run_checks(root) if p.level == "info"]


# --- DEC 参照 ---


def test_existing_dec_reference_is_ok(tmp_path: Path) -> None:
    _doc(tmp_path, "docs/decisions/DEC-0001-x.md", "決定の本文。")
    _doc(tmp_path, "AGENTS.md", "DEC-0001 を参照。")
    assert _errors(tmp_path) == []


def test_missing_dec_reference_is_error(tmp_path: Path) -> None:
    _doc(tmp_path, "AGENTS.md", "DEC-9999 を参照。")
    errors = _errors(tmp_path)
    assert any("AGENTS.md" in m and "DEC-9999" in m for m in errors)


def test_dec_number_must_match_exactly_not_by_prefix(tmp_path: Path) -> None:
    # DEC-00012 が在っても DEC-0001 の実体にはならない（番号の前方一致では通さない）。
    _doc(tmp_path, "docs/decisions/DEC-00012-y.md", "別の決定。")
    _doc(tmp_path, "AGENTS.md", "DEC-0001 を参照。")
    assert any("DEC-0001" in m for m in _errors(tmp_path))


# --- ISS 参照 ---


def test_missing_iss_reference_is_error(tmp_path: Path) -> None:
    # 既定 backend は file:issues。issues/ に ISS-9999 が無い＝error。
    _doc(tmp_path, "AGENTS.md", "課題 ISS-9999 を参照。")
    assert any("ISS-9999" in m for m in _errors(tmp_path))


def test_existing_iss_reference_is_ok(tmp_path: Path) -> None:
    _doc(tmp_path, "issues/ISS-0001-x.md", "課題の本文。")
    _doc(tmp_path, "AGENTS.md", "課題 ISS-0001 を参照。")
    assert _errors(tmp_path) == []


def test_iss_check_skipped_on_github_backend(tmp_path: Path) -> None:
    # github: backend では課題の実体がローカルに無いので ISS 検査を行わない（仕様の分岐・skip でない）。
    _doc(tmp_path, ".harness/config.toml", '[issues]\nbackend = "github:owner/repo"\n')
    _doc(tmp_path, "AGENTS.md", "課題 ISS-9999 を参照。")
    assert _errors(tmp_path) == []


# --- パス参照 ---


def test_missing_path_is_error(tmp_path: Path) -> None:
    _doc(tmp_path, "AGENTS.md", "`src/nope.py` を見る。")
    assert any("src/nope.py" in m for m in _errors(tmp_path))


def test_existing_path_and_directory_are_ok(tmp_path: Path) -> None:
    _doc(tmp_path, "src/ok.py", "x = 1\n")
    (tmp_path / "docs" / "sub").mkdir(parents=True)
    _doc(tmp_path, "AGENTS.md", "`src/ok.py` と docs/sub/ を見る。")
    assert _errors(tmp_path) == []


def test_globs_placeholders_and_bare_words_are_not_flagged(tmp_path: Path) -> None:
    # glob（*）・変数（{}）・プレースホルダ（<>・XXXX）・拡張子なしの語は保守的に拾わない。
    text = (
        "`src/*.py` を集める。`docs/{name}.md` を作る。`work/<ID>-x.md` に置く。\n"
        "`tests/test_*.py` が対象。docs/decisions/DEC-XXXX-思想.md の形式。docs のどこか。\n"
    )
    _doc(tmp_path, "AGENTS.md", text)
    assert doclint.run_checks(tmp_path) == []


def test_trailing_punctuation_is_stripped(tmp_path: Path) -> None:
    _doc(tmp_path, "docs/method.md", "手順の本文。\n")
    _doc(tmp_path, "AGENTS.md", "詳細は docs/method.md。")
    assert _errors(tmp_path) == []


# --- コマンド参照 ---


def test_known_command_is_ok_and_unknown_is_info(tmp_path: Path) -> None:
    # pyproject の無い一時プロジェクトでは固定の最小集合（verify/status/task-lint/data）が既知。未知は info。
    _doc(tmp_path, "AGENTS.md", "`uv run verify` を回す。`uv run data blocks` で一覧。`uv run nope` は打ち間違い。")
    assert _errors(tmp_path) == []
    infos = _infos(tmp_path)
    assert any("uv run nope" in m for m in infos)
    assert not any("verify" in m or "data" in m for m in infos)


def test_known_commands_derived_from_pyproject_scripts(tmp_path: Path) -> None:
    _doc(tmp_path, "pyproject.toml", '[project]\nname = "x"\nversion = "0"\n[project.scripts]\nfoo = "x:main"\n')
    _doc(tmp_path, "AGENTS.md", "`uv run foo` と `uv run verify` を使う。")
    assert doclint.run_checks(tmp_path) == []


# --- 対象ファイルの範囲 ---


def test_skills_and_decisions_are_scanned_but_templates_are_not(tmp_path: Path) -> None:
    _doc(tmp_path, ".claude/skills/foo/SKILL.md", "DEC-9999 を参照。")
    _doc(tmp_path, "docs/decisions/_template.md", "DEC-0000 の形式で書く。")
    errors = _errors(tmp_path)
    assert any(".claude/skills/foo/SKILL.md" in m and "DEC-9999" in m for m in errors)
    assert not any("DEC-0000" in m for m in errors)


# --- 回帰の番人：現リポの正本 ---


def test_real_repo_docs_have_no_dead_links() -> None:
    errors = [p for p in doclint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]
