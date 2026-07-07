"""doc_standards のテスト：文書の発見可能性と整合（孤立・凡例網羅・用語集整合・導入 lede・造語 denylist）の検査。

期待値はすべて一時プロジェクトの構成（どの文書を置き・索引に何を書くか）から導く。
最後の 1 本は現リポに対する回帰の番人（索引・凡例・用語集が整合していること＝以後の腐りを止める）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import doc_standards

REPO_ROOT = Path(__file__).resolve().parents[1]

# 凡例（全接頭辞入り）。見出しに「凡例」を含む節が凡例とみなされる。
LEGEND_ALL = (
    "## ID の凡例\n\n- `EP` エピック\n- `T` タスク\n- `E` 実験\n- `INV` 調査\n"
    "- `DEC` 決定\n- `ISS` 課題\n- `REQ` 要件\n"
)

# 用語 2 項目・重複なし・本文ありの妥当な用語集（ID 接頭辞は使わない＝凡例検査に影響しない）。
VALID_GLOSSARY = "# 用語集\n\n## 正本\n唯一の正とする置き場。\n\n## 導線\n使い方へ到達できるリンク。\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _readme(links: tuple[str, ...] = (), legend: str = LEGEND_ALL) -> str:
    """索引 docs/README.md の本文を組み立てる（links のファイル名を地図としてリンクし、legend を凡例節に置く）。"""
    lines = ["# 索引", "", *[f"- [{name}]({name})" for name in links], "", legend]
    return "\n".join(lines)


def _project(root: Path, readme: str, glossary: str = VALID_GLOSSARY) -> None:
    """最小の妥当なプロジェクト（索引＋用語集）。各テストはここから 1 点だけ崩して期待値を導く。"""
    _write(root, "docs/README.md", readme)
    _write(root, "docs/glossary.md", glossary)


def _errors(root: Path) -> list[str]:
    return [p.message for p in doc_standards.run_checks(root) if p.level == "error"]


# --- 孤立検査：索引からリンクされない docs 直下の文書は error ---


@pytest.mark.unit
def test_unlinked_doc_is_error_until_linked(tmp_path: Path) -> None:
    _project(tmp_path, _readme(links=("glossary.md",)))
    _write(tmp_path, "docs/foo.md", "索引に載っていない文書。\n")
    errors = _errors(tmp_path)
    assert any("foo.md" in m and "孤立" in m for m in errors)
    # 索引に foo.md へのリンクを足す → error が消える。
    _write(tmp_path, "docs/README.md", _readme(links=("glossary.md", "foo.md")))
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_readme_itself_is_not_an_orphan(tmp_path: Path) -> None:
    # 索引そのもの（docs/README.md）は孤立検査の対象外＝自分へのリンクは要らない。
    _project(tmp_path, _readme(links=("glossary.md",)))
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_exempt_doc_suppresses_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, _readme(links=("glossary.md",)))
    _write(tmp_path, "docs/foo.md", "索引に載せない文書（免除の例）。\n")
    monkeypatch.setitem(doc_standards._EXEMPT, "foo.md", "テスト用の内部メモ（索引不要の例）。")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_blank_exempt_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, _readme(links=("glossary.md",)))
    monkeypatch.setitem(doc_standards._EXEMPT, "foo.md", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        doc_standards.run_checks(tmp_path)


@pytest.mark.unit
def test_every_exempt_reason_is_nonempty() -> None:
    exempts = (
        ("_EXEMPT", doc_standards._EXEMPT),
        ("_LEDE_EXEMPT", doc_standards._LEDE_EXEMPT),
        ("_TERM_EXEMPT", doc_standards._TERM_EXEMPT),
    )
    for label, exempt in exempts:
        for name, reason in exempt.items():
            assert isinstance(reason, str) and reason.strip(), f"{label}[{name!r}] の理由が空"


# --- 凡例網羅：使われている ID 接頭辞が凡例に無ければ error ---


@pytest.mark.unit
def test_used_prefix_missing_from_legend_until_added(tmp_path: Path) -> None:
    legend_without_dec = "## ID の凡例\n\n- `EP` エピック\n"
    _project(tmp_path, _readme(links=("glossary.md", "bar.md"), legend=legend_without_dec))
    _write(tmp_path, "docs/bar.md", "この判断は DEC-0007 を参照。\n")
    errors = _errors(tmp_path)
    assert any("'DEC'" in m and "凡例" in m for m in errors)
    # 凡例に DEC の 1 行を足す → error が消える。
    legend_with_dec = legend_without_dec + "- `DEC` 決定\n"
    _write(tmp_path, "docs/README.md", _readme(links=("glossary.md", "bar.md"), legend=legend_with_dec))
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_missing_legend_section_is_error_when_prefixes_are_used(tmp_path: Path) -> None:
    # 凡例の節（見出しに「凡例」）がそもそも無い索引＋接頭辞の使用 → error（節を置けと名指しする）。
    _project(tmp_path, _readme(links=("glossary.md", "bar.md"), legend="## 補足\n\n説明。\n"))
    _write(tmp_path, "docs/bar.md", "この判断は DEC-0007 を参照。\n")
    errors = _errors(tmp_path)
    assert any("凡例の節" in m for m in errors)


@pytest.mark.unit
def test_archive_is_excluded_from_orphan_and_legend(tmp_path: Path) -> None:
    # docs/archive/** は孤立検査（直下のみ）にも凡例網羅（archive 除外）にも数えない。
    _project(tmp_path, _readme(links=("glossary.md",)))
    _write(tmp_path, "docs/archive/old-note.md", "古いメモ。ISS-0001 に触れる（凡例に ISS は無いが対象外）。\n")
    assert _errors(tmp_path) == []


# --- 用語集整合：存在・見出しの重複なし・空見出しなし ---


@pytest.mark.unit
def test_missing_glossary_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/README.md", _readme())
    errors = _errors(tmp_path)
    assert any("glossary.md" in m and "無い" in m for m in errors)


@pytest.mark.unit
def test_duplicate_glossary_heading_is_error(tmp_path: Path) -> None:
    glossary = "# 用語集\n\n## 正本\n唯一の正とする置き場。\n\n## 正本\n二重に定義してしまった項目。\n"
    _project(tmp_path, _readme(links=("glossary.md",)), glossary=glossary)
    errors = _errors(tmp_path)
    assert any("'正本'" in m and "重複" in m for m in errors)


@pytest.mark.unit
def test_empty_glossary_heading_is_error(tmp_path: Path) -> None:
    glossary = "# 用語集\n\n## 導線\n\n## 正本\n唯一の正とする置き場。\n"
    _project(tmp_path, _readme(links=("glossary.md",)), glossary=glossary)
    errors = _errors(tmp_path)
    assert any("'導線'" in m and "定義本文" in m for m in errors)


# --- 導入（lede）検査：対象文書の H1 直後の最初の内容は平文の段落（＝可視の導入）であること ---


def _lede_project(root: Path, body: str) -> None:
    """lede 検査用の最小プロジェクト：対象文書 foo.md（索引にリンク済み＝孤立 error を混ぜない）を body で置く。"""
    _project(root, _readme(links=("glossary.md", "foo.md")))
    _write(root, "docs/foo.md", body)


@pytest.fixture
def lede_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """lede 検査の対象を foo.md だけに差し替える（現物の対象リストに依存しない）。"""
    monkeypatch.setattr(doc_standards, "_LEDE_DOCS", ("foo.md",))


@pytest.mark.unit
def test_lede_bullet_list_first_is_error_until_prose_added(tmp_path: Path, lede_target: None) -> None:
    _lede_project(tmp_path, "# 題名\n\n- いきなり箇条書き（機構の羅列）\n")
    errors = _errors(tmp_path)
    assert any("foo.md" in m and "導入" in m for m in errors)
    # H1 直後に平文の導入を置く → error が消える（導入の後の箇条書きはよい）。
    _write(tmp_path, "docs/foo.md", "# 題名\n\nこの文書が何か・なぜ在るかを述べる平易な導入。\n\n- 詳細は導入の後\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_lede_html_comment_first_is_error(tmp_path: Path, lede_target: None) -> None:
    # HTML コメントに隠した導入は「可視」でない＝error。
    _lede_project(tmp_path, "# 題名\n\n<!-- コメントに隠れた導入 -->\n\n本文。\n")
    errors = _errors(tmp_path)
    assert any("foo.md" in m and "平文の段落でない" in m for m in errors)


@pytest.mark.unit
def test_lede_heading_or_fence_first_is_error(tmp_path: Path, lede_target: None) -> None:
    _lede_project(tmp_path, "# 題名\n\n## いきなり小見出し\n\n本文。\n")
    assert any("foo.md" in m for m in _errors(tmp_path))
    _write(tmp_path, "docs/foo.md", "# 題名\n\n```\nuv run verify\n```\n")
    assert any("foo.md" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_lede_missing_h1_or_empty_body_is_error(tmp_path: Path, lede_target: None) -> None:
    _lede_project(tmp_path, "本文だけで題名（H1）が無い。\n")
    assert any("foo.md" in m and "H1" in m for m in _errors(tmp_path))
    _write(tmp_path, "docs/foo.md", "# 題名\n")
    assert any("foo.md" in m and "H1" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_lede_absent_target_doc_is_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 対象文書ごと持たないプロジェクト（コピー先で領域を外した等）には lede を課さない。
    monkeypatch.setattr(doc_standards, "_LEDE_DOCS", ("missing.md",))
    _project(tmp_path, _readme(links=("glossary.md",)))
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_lede_exempt_suppresses_error(tmp_path: Path, lede_target: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(doc_standards._LEDE_EXEMPT, "foo.md", "テスト用：導入を課さない例。")
    _lede_project(tmp_path, "# 題名\n\n- 箇条書きで始まる\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_blank_lede_exempt_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, _readme(links=("glossary.md",)))
    monkeypatch.setitem(doc_standards._LEDE_EXEMPT, "foo.md", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        doc_standards.run_checks(tmp_path)


# --- 造語 denylist：最悪造語は用語集の該当アンカーへのリンク無しに使えない ---

# denylist に実在する語とその構成（提案・アンカー）から期待値を導く（語を増減してもテストは追従する）。
DENY_TERM = "金メッキ"
DENY_SUGGESTION, DENY_ANCHOR = doc_standards._DENYLIST[DENY_TERM]


@pytest.mark.unit
def test_denylisted_term_without_glossary_link_is_error_until_linked(tmp_path: Path) -> None:
    _project(tmp_path, _readme(links=("glossary.md", "foo.md")))
    _write(tmp_path, "docs/foo.md", f"# 題名\n\nテストに{DENY_TERM}を書かない。\n")
    errors = _errors(tmp_path)
    assert any(f"'{DENY_TERM}'" in m and DENY_SUGGESTION in m for m in errors)
    # 使用箇所を用語集の該当アンカーへリンクする → error が消える。
    _write(tmp_path, "docs/foo.md", f"# 題名\n\nテストに[{DENY_TERM}](glossary.md#{DENY_ANCHOR})を書かない。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_denylisted_term_absent_is_clean(tmp_path: Path) -> None:
    _project(tmp_path, _readme(links=("glossary.md", "foo.md")))
    _write(tmp_path, "docs/foo.md", "# 題名\n\n対象語を使わない普通の文書。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_glossary_itself_is_excluded_from_denylist(tmp_path: Path) -> None:
    # 用語集は対象語を定義する場所そのものなので、リンク無しで語が現れても指摘しない。
    glossary = f"{VALID_GLOSSARY}\n## {DENY_TERM}\n導出できない期待値を書いたテストのこと。\n"
    _project(tmp_path, _readme(links=("glossary.md",)), glossary=glossary)
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_denylist_scans_subdirectories_but_not_archive(tmp_path: Path) -> None:
    # 検査は docs/**（再帰・decisions/ 等も対象）。archive/ は正本でないので対象外。
    _project(tmp_path, _readme(links=("glossary.md",)))
    _write(tmp_path, "docs/archive/old.md", f"# 古いメモ\n\n{DENY_TERM}という言い方をしていた。\n")
    assert _errors(tmp_path) == []
    _write(tmp_path, "docs/decisions/DEC-0001-x.md", f"# 決定\n\n{DENY_TERM}を禁じる。\n")
    errors = _errors(tmp_path)
    assert any("decisions/DEC-0001-x.md" in m and f"'{DENY_TERM}'" in m for m in errors)


@pytest.mark.unit
def test_term_exempt_suppresses_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, _readme(links=("glossary.md", "foo.md")))
    _write(tmp_path, "docs/foo.md", f"# 題名\n\n{DENY_TERM}に触れる文書（免除の例）。\n")
    monkeypatch.setitem(doc_standards._TERM_EXEMPT, "foo.md", "テスト用：対象語を言及として引用する例。")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_blank_term_exempt_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, _readme(links=("glossary.md",)))
    monkeypatch.setitem(doc_standards._TERM_EXEMPT, "foo.md", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        doc_standards.run_checks(tmp_path)


@pytest.mark.unit
def test_every_denylist_term_has_a_real_glossary_anchor_heading() -> None:
    # denylist の各語は、現リポの用語集に定義（見出し）がある語だけを載せる（提案先が実在する）。
    glossary_text = (REPO_ROOT / "docs" / "glossary.md").read_text(encoding="utf-8")
    for term, (suggestion, _anchor) in doc_standards._DENYLIST.items():
        assert f"## {term}" in glossary_text, f"denylist の '{term}' が docs/glossary.md に定義されていない"
        assert suggestion.strip(), f"denylist の '{term}' の言い換え提案が空"


# --- 縮退：docs を正本置き場として使っていないプロジェクトでは誤検知しない ---


@pytest.mark.unit
def test_project_without_docs_dir_is_silent(tmp_path: Path) -> None:
    assert doc_standards.run_checks(tmp_path) == []


@pytest.mark.unit
def test_docs_dir_without_markdown_is_silent(tmp_path: Path) -> None:
    # docs/ にテーブル定義（YAML）だけ置くコピー先の初期状態＝索引がまだ無くても指摘しない。
    _write(tmp_path, "docs/data/train.yaml", "id: train\n")
    assert doc_standards.run_checks(tmp_path) == []


@pytest.mark.unit
def test_missing_readme_is_error_when_docs_are_present(tmp_path: Path) -> None:
    _write(tmp_path, "docs/foo.md", "索引の無いプロジェクトの文書。\n")
    errors = _errors(tmp_path)
    assert any("docs/README.md" in m and "索引" in m for m in errors)


# --- 配線：PM_CHECKS（verify の中核検査列）に載っている（外すと文書の腐りが検出されなくなる） ---


@pytest.mark.unit
def test_doc_standards_is_wired_into_pm_checks() -> None:
    from harness import checks

    assert doc_standards.run_checks in checks.PM_CHECKS


# --- 回帰の番人：現リポの索引・凡例・用語集が整合している（以後の腐りを止める） ---


@pytest.mark.integration
def test_real_repo_doc_standards_is_green() -> None:
    errors = [p for p in doc_standards.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]
