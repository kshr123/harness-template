"""doc_standards のテスト：文書の発見可能性と整合（孤立・凡例網羅・用語集整合）の検査。

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
    for name, reason in doc_standards._EXEMPT.items():
        assert isinstance(reason, str) and reason.strip(), f"_EXEMPT[{name!r}] の理由が空"


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
