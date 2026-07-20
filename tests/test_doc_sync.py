"""doc_sync のテスト：中核の正本ドキュメント（docs/core.md）の自動生成節と、その鮮度検査。

期待値はすべて入力の構成から導く：
- 検査の表は `checks.INVARIANT_CHECKS`（関数の一覧）から導出する＝行数・名前・要約は INVARIANT_CHECKS 側の事実。
- コマンドの表は一時プロジェクトに置いた `checks.toml` の中身から導出する。
最後の 1 本は現リポの `docs/core.md` に対する回帰テスト（コミット済みの生成物が古くないこと）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import checks, doc_sync, pm

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]


def _errors(root: Path) -> list[str]:
    return [p.message for p in doc_sync.run_checks(root) if p.level == "error"]


def _write_core_doc(root: Path, body: str) -> Path:
    """マーカーで囲んだ本文を持つ docs/core.md を作る（前後に散文も置く＝生成節だけを差し替える確認用）。"""
    path = root / doc_sync.DOC_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# 中核\n\n前書き。\n\n{doc_sync.MARKER_BEGIN}\n{body}{doc_sync.MARKER_END}\n\n後書き。\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _checks_toml(root: Path) -> None:
    """段階と数を検査側で決め打ちしない形の checks.toml（期待値はこの構成から導く）。"""
    (root / "checks.toml").write_text(
        '[fast]\ncommands = [["ruff", "check", "."]]\n[full]\ncommands = [["pytest", "-q"]]\n',
        encoding="utf-8",
    )


def _table_rows(section: str) -> list[str]:
    """Markdown 表の本文行（見出し行と区切り行を除く `|` 始まりの行）。"""
    rows = [line for line in section.splitlines() if line.startswith("|")]
    return rows[2:]  # 0=見出し 1=区切り


def _section(text: str, heading: str) -> str:
    """指定の見出しから次の見出し（または末尾）までを切り出す。"""
    start = text.index(heading)
    rest = text.index("\n### ", start + 1) if "\n### " in text[start + 1 :] else len(text)
    return text[start:rest]


# --- 生成の内容（INVARIANT_CHECKS と checks.toml から導く） ---


def test_check_table_has_exactly_one_row_per_invariant_check(tmp_path: Path) -> None:
    # 表の行数は INVARIANT_CHECKS の件数と一致する（載せ忘れ・二重掲載が起きない）。
    text = doc_sync.render(tmp_path)
    rows = _table_rows(_section(text, doc_sync.HEADING_CHECKS))
    assert len(rows) == len(checks.INVARIANT_CHECKS)


def test_check_table_names_each_invariant_check_as_module_dot_function(tmp_path: Path) -> None:
    # 名前は一律 `<モジュール>.<関数>`。特例（run_checks の短縮）は作らない。
    text = doc_sync.render(tmp_path)
    for fn in checks.INVARIANT_CHECKS:
        expected = f"{fn.__module__.removeprefix('harness.')}.{fn.__name__}"
        assert f"`{expected}`" in text


def test_check_table_uses_docstring_first_line_as_summary(tmp_path: Path) -> None:
    # 要約の出所は docstring 1 行目だけ（文言を二重に持たない＝食い違いが起きない）。
    text = doc_sync.render(tmp_path)
    for fn in checks.INVARIANT_CHECKS:
        first_line = (fn.__doc__ or "").strip().splitlines()[0]
        assert doc_sync._escape_cell(first_line) in text


def test_command_table_rows_come_from_checks_toml(tmp_path: Path) -> None:
    _checks_toml(tmp_path)
    section = _section(doc_sync.render(tmp_path), doc_sync.HEADING_COMMANDS)
    rows = _table_rows(section)
    assert len(rows) == 2  # 上の checks.toml に置いたコマンドは fast/full に 1 本ずつ
    assert any("fast" in r and "ruff check ." in r for r in rows)
    assert any("full" in r and "pytest -q" in r for r in rows)


def test_command_argument_with_spaces_is_quoted(tmp_path: Path) -> None:
    # 表からそのままコピーして貼れること。`-m unit and not slow` は引用しないと別の意味になる。
    (tmp_path / "checks.toml").write_text(
        '[fast]\ncommands = [["pytest", "-m", "unit and not slow"]]\n', encoding="utf-8"
    )
    section = _section(doc_sync.render(tmp_path), doc_sync.HEADING_COMMANDS)
    assert "pytest -m 'unit and not slow'" in section


def test_levels_really_are_cumulative_as_the_generated_prose_claims(tmp_path: Path) -> None:
    # 生成節の散文「段階は累積する（full は fast・standard のコマンドも走らせる）」は checks._load_commands の
    # 振る舞いの言い換えで、表からは導出されない。文が嘘にならないよう、その振る舞いをここで固定する。
    _checks_toml(tmp_path)  # fast に 1 本・full に 1 本
    fast = checks._load_commands(tmp_path, "fast")
    full = checks._load_commands(tmp_path, "full")
    assert fast == [["ruff", "check", "."]]
    assert full[: len(fast)] == fast  # full は fast の全コマンドを先に含む
    assert ["pytest", "-q"] in full


def test_command_table_is_empty_without_checks_toml(tmp_path: Path) -> None:
    # checks.toml が無い複製先でも生成できる（表は空・見出しは残る）。
    section = _section(doc_sync.render(tmp_path), doc_sync.HEADING_COMMANDS)
    assert _table_rows(section) == []


def test_render_ignores_config_so_every_copy_generates_the_same_table(tmp_path: Path) -> None:
    # プロファイルの検査は実行時に config から加わる＝生成表には載らない（複製先で生成結果が変わらない）。
    with_config = tmp_path / "with-config"
    without_config = tmp_path / "without-config"
    (with_config / ".harness").mkdir(parents=True)
    without_config.mkdir()
    (with_config / ".harness" / "config.toml").write_text('profiles = ["harness.ds"]\n', encoding="utf-8")
    assert doc_sync.render(with_config) == doc_sync.render(without_config)
    assert "harness.ds" not in doc_sync.render(with_config)


def test_pipe_in_summary_is_escaped_so_the_table_keeps_its_shape() -> None:
    def fake(_root: Path) -> list[pm.Problem]:
        """左 | 右 の要約。"""
        return []

    assert doc_sync._escape_cell(doc_sync._summary(fake)) == r"左 \| 右 の要約。"


# --- fail closed（黙って空欄を生成しない） ---


def test_check_without_docstring_raises() -> None:
    def undocumented(_root: Path) -> list[pm.Problem]:
        return []

    with pytest.raises(ValueError, match="undocumented"):
        doc_sync._summary(undocumented)


def test_check_with_blank_docstring_raises() -> None:
    def blank(_root: Path) -> list[pm.Problem]:
        """ """
        return []

    with pytest.raises(ValueError, match="blank"):
        doc_sync._summary(blank)


# --- 鮮度検査 ---


def test_fresh_block_is_ok(tmp_path: Path) -> None:
    _checks_toml(tmp_path)
    _write_core_doc(tmp_path, "古い本文\n")
    doc_sync.sync(tmp_path)
    assert doc_sync.run_checks(tmp_path) == []


def test_stale_block_is_error(tmp_path: Path) -> None:
    _checks_toml(tmp_path)
    _write_core_doc(tmp_path, "手で書いた古い表\n")
    assert any(doc_sync.DOC_REL in m and "doc-sync" in m for m in _errors(tmp_path))


def test_missing_marker_is_error(tmp_path: Path) -> None:
    path = tmp_path / doc_sync.DOC_REL
    path.parent.mkdir(parents=True)
    path.write_text("# 中核\n\nマーカーが無い。\n", encoding="utf-8")
    assert any("マーカー" in m for m in _errors(tmp_path))


def test_duplicate_marker_is_error(tmp_path: Path) -> None:
    path = tmp_path / doc_sync.DOC_REL
    path.parent.mkdir(parents=True)
    body = f"{doc_sync.MARKER_BEGIN}\na\n{doc_sync.MARKER_END}\n{doc_sync.MARKER_BEGIN}\nb\n{doc_sync.MARKER_END}\n"
    path.write_text(body, encoding="utf-8")
    assert any("マーカー" in m for m in _errors(tmp_path))


def test_absent_core_doc_is_not_a_problem(tmp_path: Path) -> None:
    # 削除の検出は doclint（AGENTS.md からのリンクが死にリンクになる）に委ねる＝ここでは指摘しない。
    assert not (tmp_path / doc_sync.DOC_REL).exists()
    assert doc_sync.run_checks(tmp_path) == []


def test_sync_is_idempotent(tmp_path: Path) -> None:
    _checks_toml(tmp_path)
    path = _write_core_doc(tmp_path, "初期\n")
    assert doc_sync.sync(tmp_path) is True  # 1 回目は書き換わる
    after_first = path.read_bytes()
    assert doc_sync.sync(tmp_path) is False  # 2 回目は変化なし
    assert path.read_bytes() == after_first


def test_sync_preserves_prose_outside_the_markers(tmp_path: Path) -> None:
    _checks_toml(tmp_path)
    path = _write_core_doc(tmp_path, "置き換えられる\n")
    doc_sync.sync(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "前書き。" in text and "後書き。" in text
    assert "置き換えられる" not in text


def test_crlf_document_is_not_reported_as_stale(tmp_path: Path) -> None:
    # Windows の作業ツリーで CRLF になっていても鮮度検査は偽陽性を出さない（比較は改行を正規化する）。
    _checks_toml(tmp_path)
    path = _write_core_doc(tmp_path, "初期\n")
    doc_sync.sync(tmp_path)
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert doc_sync.run_checks(tmp_path) == []


def test_sync_writes_lf_newlines(tmp_path: Path) -> None:
    _checks_toml(tmp_path)
    path = _write_core_doc(tmp_path, "初期\n")
    doc_sync.sync(tmp_path)
    assert b"\r\n" not in path.read_bytes()


def test_sync_raises_when_markers_are_absent(tmp_path: Path) -> None:
    path = tmp_path / doc_sync.DOC_REL
    path.parent.mkdir(parents=True)
    path.write_text("# 中核\n", encoding="utf-8")
    with pytest.raises(ValueError, match="マーカー"):
        doc_sync.sync(tmp_path)


# --- 回帰テスト：現リポのコミット済み生成物 ---


def test_real_repo_core_doc_is_fresh() -> None:
    problems = doc_sync.run_checks(REPO_ROOT)
    assert problems == [], [p.message for p in problems]


def test_doc_sync_is_registered_in_invariant_checks() -> None:
    # 自己言及：doc_sync 自身も verify が回す検査の 1 つとして表に載る（表の完全性の定義）。
    assert doc_sync.run_checks in checks.INVARIANT_CHECKS
