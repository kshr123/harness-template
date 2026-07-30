"""doclint のテスト：正本ドキュメントの参照（ISS/パス/コマンド）実在検査。

期待値はすべて一時プロジェクトの構成（何を置き・何を置かないか）から導く。
最後の 1 本は現リポの実 docs に対する回帰テスト（正本の参照が全部実在すること）。
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


# --- ID 参照の実在検査（接頭辞ごとの置き場登録簿。T-0165） ---


def test_req_reference_with_existing_home_and_missing_file_is_error(tmp_path: Path) -> None:
    # docs/requirements/ は在るが REQ-9999 の実体が無い＝error。
    (tmp_path / "docs" / "requirements").mkdir(parents=True)
    _doc(tmp_path, "AGENTS.md", "要件 REQ-9999 を満たす。")
    assert any("REQ-9999" in m for m in _errors(tmp_path))


def test_req_reference_with_existing_file_is_ok(tmp_path: Path) -> None:
    _doc(tmp_path, "docs/requirements/REQ-001.md", "要件の本文。")
    _doc(tmp_path, "AGENTS.md", "要件 REQ-001 を満たす。")
    assert _errors(tmp_path) == []


def test_extensionless_reference_whose_parent_dir_exists_is_ok(tmp_path: Path) -> None:
    # 拡張子の無い 2 セグメントの参照（例 tests/conftest）は、親ディレクトリ tests/ が在れば指摘しない。
    # 「参照先を含むディレクトリが存在するか」を見るのが検査の意図で、参照そのものがディレクトリである
    # ことは要求しない（doclint は過検出より取りこぼしを許容する方針）。
    _doc(tmp_path, "tests/conftest.py", "# 収集フック")
    _doc(tmp_path, "AGENTS.md", "収集フックは tests/conftest を参照。")
    assert _errors(tmp_path) == []


def test_case_area_path_reference_is_not_flagged_when_absent(tmp_path: Path) -> None:
    # docs/wbs.yaml は init-project が白紙化する案件領域ファイル＝fresh clone に無くて当然。durable な docs が
    # それを指しても壊れリンクではない（doclint は CASE_AREA_ROOTS 配下のパスの不在を咎めない）。
    assert not (tmp_path / "docs" / "wbs.yaml").exists()
    _doc(tmp_path, "AGENTS.md", "案件固有の上書きは docs/wbs.yaml に置く。")
    assert _errors(tmp_path) == []


def test_non_case_area_missing_path_is_still_an_error(tmp_path: Path) -> None:
    # 免除が広すぎないことの確認：案件領域外の不在パスは従来どおり error（案件領域だけを除外する）。
    _doc(tmp_path, "AGENTS.md", "詳細は docs/nonexistent-guide.md を参照。")
    assert any("docs/nonexistent-guide.md" in m for m in _errors(tmp_path))


def test_case_area_subtree_is_exempt_but_boundary_sibling_is_not(tmp_path: Path) -> None:
    # 案件領域ディレクトリ（work）の配下は免除・境界の別物は免除しない（セグメント境界一致）。
    _doc(tmp_path, "AGENTS.md", "配下は work/deep/nested/file.md、境界の別物は docs/requirements-old.md。")
    errors = _errors(tmp_path)
    assert not any("work/deep/nested/file.md" in m for m in errors)  # work/ 配下＝免除
    assert any("docs/requirements-old.md" in m for m in errors)  # docs/requirements の配下ではない→error


def test_case_area_glob_matches_per_segment_not_across_slash(tmp_path: Path) -> None:
    # glob 免除（docs/structure-review-*.md）は 1 セグメントのファイル名パターン＝`*` が `/` を跨がない。
    _doc(tmp_path, "AGENTS.md", "レビューは docs/structure-review-notes.md、入れ子は docs/structure-review-x/y.md。")
    errors = _errors(tmp_path)
    assert not any("structure-review-notes.md" in m for m in errors)  # 1 セグメント＝免除
    assert any("structure-review-x/y.md" in m for m in errors)  # `/` を跨ぐ＝免除しない→error


def test_extensionless_reference_whose_parent_dir_is_absent_is_error(tmp_path: Path) -> None:
    # 親ディレクトリごと撤去された仕組みへの参照（例 docs/decisions/DEC-0006）は error のまま。
    _doc(tmp_path, "AGENTS.md", "根拠は docs/decisions/DEC-0006 を参照。")
    errors = _errors(tmp_path)
    assert any("docs/decisions" in message for message in errors)


def test_reference_to_prefix_whose_home_dir_is_absent_is_error(tmp_path: Path) -> None:
    # docs/decisions/ を撤去済みのプロジェクトで DEC-0001 を参照＝置き場自体が無いのですべて error
    # （T-0165：仕組みを撤去したのに参照が残っている状態を検出する。docs/decisions/ を持たないのは
    # このハーネス自体の現状＝EP-26 で廃止済み）。
    assert not (tmp_path / "docs" / "decisions").exists()
    _doc(tmp_path, "AGENTS.md", "設計判断は DEC-0001 を参照。")
    errors = _errors(tmp_path)
    assert any("DEC-0001" in m and "docs/decisions" in m for m in errors)


# --- ISS 参照 ---


def test_missing_iss_reference_is_error(tmp_path: Path) -> None:
    # 既定 backend は file:issues。存在しない課題 ID を参照＝error。
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
        "`tests/test_*.py` が対象。`docs/notes/XXXX-思想.md` の形式。docs のどこか。\n"
    )
    _doc(tmp_path, "AGENTS.md", text)
    assert doclint.run_checks(tmp_path) == []


def test_trailing_punctuation_is_stripped(tmp_path: Path) -> None:
    _doc(tmp_path, "docs/method.md", "手順の本文。\n")
    _doc(tmp_path, "AGENTS.md", "詳細は docs/method.md。")
    assert _errors(tmp_path) == []


# --- 拡張子もスラッシュ終端も無いパス（T-0165：先頭 2 セグメントの実在で判定） ---


def test_bare_path_with_missing_home_dir_is_error(tmp_path: Path) -> None:
    # 拡張子なし・スラッシュ終端なしの参照は、これまで「判定に迷う」として素通りしていた
    # （docs/decisions/DEC-0006 のような、仕組みを撤去した後の参照を見逃す穴）。
    _doc(tmp_path, "AGENTS.md", "詳細は `templates/removed-experiment-kind` を見る。")
    assert any("templates/removed-experiment-kind" in m for m in _errors(tmp_path))


def test_bare_path_with_existing_home_dir_is_ok(tmp_path: Path) -> None:
    (tmp_path / "templates" / "existing-kind").mkdir(parents=True)
    _doc(tmp_path, "AGENTS.md", "詳細は `templates/existing-kind` を見る。")
    assert _errors(tmp_path) == []


def test_bare_path_candidate_with_non_ascii_segment_is_prose_not_flagged(tmp_path: Path) -> None:
    # `docs/日本語の語` のような日本語の散文は _PATH_RE の \w（Unicode）に拾われるが、拡張子・末尾スラッシュを
    # 持たない候補は全 ASCII のときだけ検査するので、パスでなく散文として扱われ error を出さない。
    _doc(tmp_path, "AGENTS.md", "詳細は docs/日本語の語 を参照。")
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


def test_known_commands_derived_from_venv_scripts_on_windows(tmp_path: Path) -> None:
    # Windows の venv は .venv/bin でなく .venv/Scripts（実行ファイルは拡張子付き＝pytest.exe 等）。
    # p.stem（拡張子を除いた名前）で登録することを固定する（このバグで `uv run marimo` 等が
    # 常に「既知のコマンドに無い」と info 報告されていた）。
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "marimo.exe").write_text("", encoding="utf-8")
    _doc(tmp_path, "AGENTS.md", "`uv run marimo` でノートブックを開く。")
    assert doclint.run_checks(tmp_path) == []


def test_known_commands_still_derived_from_venv_bin_on_posix(tmp_path: Path) -> None:
    # posix の venv は .venv/bin（拡張子なし）。既存の経路を壊さないことも合わせて固定する。
    bin_dir = tmp_path / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "marimo").write_text("", encoding="utf-8")
    _doc(tmp_path, "AGENTS.md", "`uv run marimo` でノートブックを開く。")
    assert doclint.run_checks(tmp_path) == []


# --- src/**/*.py の文字列リテラル（T-0165：ID 参照だけを見る。コメントは対象外） ---


def test_python_string_literal_with_dead_id_reference_is_error(tmp_path: Path) -> None:
    _doc(
        tmp_path,
        "src/harness/example.py",
        'def f() -> str:\n    return "設計の根拠は REQ-9999 を見る"\n',
    )
    errors = _errors(tmp_path)
    assert any("src/harness/example.py" in m and "REQ-9999" in m for m in errors)


def test_python_comment_with_dead_id_reference_is_not_checked(tmp_path: Path) -> None:
    # コメントは ast に現れないので対象外（コメントには大量の暫定引用が残っており過検出の的になるため）。
    _doc(tmp_path, "src/harness/example.py", "# 設計の根拠は REQ-9999 を見る\nx = 1\n")
    assert _errors(tmp_path) == []


def test_python_string_literal_with_existing_id_reference_is_ok(tmp_path: Path) -> None:
    _doc(tmp_path, "docs/requirements/REQ-001.md", "要件の本文。")
    _doc(tmp_path, "src/harness/example.py", 'x = "要件 REQ-001 に対応"\n')
    assert _errors(tmp_path) == []


# --- 対象ファイルの範囲 ---


def test_skills_are_scanned(tmp_path: Path) -> None:
    # スキルも走査対象＝存在しない課題参照は死にリンクとして拾う。
    _doc(tmp_path, ".claude/skills/foo/SKILL.md", "課題 ISS-9999 を参照。")
    assert any(".claude/skills/foo/SKILL.md" in m and "ISS-9999" in m for m in _errors(tmp_path))


# --- 回帰テスト：現リポの正本 ---


def test_real_repo_docs_have_no_dead_links() -> None:
    errors = [p for p in doclint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]


def test_template_copy_paths_resolve() -> None:
    # docs/template-copy.md（複製手順）が指すパス参照（templates/・tests/・work/ 等）がすべて実在すること
    # （T-0140：正本雛形の移設で複製手順が腐っていないかを doclint の走査対象に載せた回帰テスト）。
    errors = [p for p in doclint.run_checks(REPO_ROOT) if p.level == "error" and "docs/template-copy.md" in p.message]
    assert errors == [], [p.message for p in errors]
