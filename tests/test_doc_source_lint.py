"""doc_source_lint のテスト：恒久ドキュメントが一時的な作業単位（work/）を参照していないか。

期待値はすべて一時プロジェクトの構成（どの文書にどんな参照を置くか）から導く。最後の 1 本は現リポに対する
回帰の番人（恒久ドキュメントが work/ の作業単位を参照しないこと＝以後の混入を止める）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import doc_source_lint

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in doc_source_lint.run_checks(root) if p.level == "error"]


# --- 検出：恒久ドキュメントの work/ 参照は error ---


@pytest.mark.unit
def test_durable_doc_referencing_work_item_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/ops.md", "理由は `work/EP-21-ops-profile/item.md` を参照。\n")
    errors = _errors(tmp_path)
    assert any("work/EP-21-ops-profile" in m and "docs/ops.md:1" in m for m in errors)
    # DEC 参照・本文説明に直すと消える。
    _write(tmp_path, "docs/ops.md", "理由は本文のとおり（詳細は `docs/method.md`）。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_readme_and_agents_are_scanned(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "構成例：`work/T-0001-foo.md`。\n")
    _write(tmp_path, "AGENTS.md", "根拠は `work/E-0003/SPEC.md`。\n")
    errors = _errors(tmp_path)
    assert any("README.md" in m and "work/T-0001" in m for m in errors)
    assert any("AGENTS.md" in m and "work/E-0003" in m for m in errors)


@pytest.mark.unit
def test_placeholder_work_path_is_not_flagged(tmp_path: Path) -> None:
    # プレースホルダ（ID を持たない構成例）は正当＝拾わない。
    _write(tmp_path, "README.md", "- `work/<エピック>/item.md` … エピックの目的\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_contract_paths_are_not_flagged(tmp_path: Path) -> None:
    # artifacts/・results/ は契約のパス型なので禁じない。
    _write(tmp_path, "docs/serve.md", "予測ログは `artifacts/serve/predictions/<名>/<日付>.jsonl`。\n")
    _write(tmp_path, "docs/method.md", "結果は `results/metrics_<variant>.yaml` に残す。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_template_copy_is_exempt(tmp_path: Path) -> None:
    # 複製手順書は work/ を「消す対象」として名指しするので免除。
    _write(tmp_path, "docs/template-copy.md", "前案件の `work/EP-06-ds-experiment-loop/` ごと消す。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_docs_subdirs_are_not_scanned(tmp_path: Path) -> None:
    # docs 直下のみが対象。下層（保管庫・メモ等）は履歴なので対象外。
    _write(tmp_path, "docs/notes/old.md", "実装は `work/EP-23-loops/item.md`。\n")
    _write(tmp_path, "docs/archive/note.md", "当時の `work/EP-06-ds-experiment-loop/item.md`。\n")
    assert _errors(tmp_path) == []


# --- 免除リストの規約：理由は空でない文字列が必須 ---


@pytest.mark.unit
def test_every_exempt_reason_is_nonempty() -> None:
    for name, reason in doc_source_lint._EXEMPT.items():
        assert isinstance(reason, str) and reason.strip(), f"_EXEMPT[{name!r}] の理由が空"


@pytest.mark.unit
def test_blank_exempt_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(doc_source_lint._EXEMPT, "ops.md", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        doc_source_lint.run_checks(tmp_path)


# --- 配線：PM_CHECKS に載っている ---


@pytest.mark.unit
def test_doc_source_lint_is_wired_into_pm_checks() -> None:
    from harness import checks

    assert doc_source_lint.run_checks in checks.PM_CHECKS


# --- 回帰の番人：現リポの恒久ドキュメントが work/ の作業単位を参照しない ---


@pytest.mark.integration
def test_real_repo_durable_docs_have_no_work_refs() -> None:
    errors = [p for p in doc_source_lint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]
