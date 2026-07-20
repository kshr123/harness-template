"""doc_source_lint のテスト：複製後も残る資産が一時的な単位（work/ の作業単位・issues/ の課題）を参照していないか。

期待値はすべて一時プロジェクトの構成（どの資産にどんな参照を置くか）から導く。最後の 1 本は現リポに対する
回帰テスト（複製後も残る資産が work/・ISS を根拠に参照しないこと＝以後の混入を止める）。
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
    # 本文説明に直すと消える。
    _write(tmp_path, "docs/ops.md", "理由は本文のとおり（詳細は `docs/method.md`）。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_readme_and_agents_are_scanned(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "構成例：`work/T-0001-foo.md`。\n")
    _write(tmp_path, "AGENTS.md", "根拠は `work/E-0003/SPEC.md`。\n")
    errors = _errors(tmp_path)
    assert any("README.md" in m and "work/T-0001" in m for m in errors)
    assert any("AGENTS.md" in m and "work/E-0003" in m for m in errors)


# --- 検出：ISS（課題）参照も work/ と同じく error ---


@pytest.mark.unit
def test_durable_doc_referencing_issue_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/ops.md", "この検査は `ISS-0007` の対処。\n")
    errors = _errors(tmp_path)
    assert any("ISS-0007" in m and "docs/ops.md:1" in m for m in errors)
    # 課題番号を消して本文で説明すると消える。
    _write(tmp_path, "docs/ops.md", "この検査は実験 config の型無しを塞ぐ。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_iss_placeholder_forms_are_not_flagged(tmp_path: Path) -> None:
    # 角括弧プレースホルダ・型録表記（0000・XXXX）は具体単位を指さないので拾わない。
    _write(tmp_path, "docs/a.md", "例：`ISS-<番号>`・`ISS-0000`・`ISS-XXXX`。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_placeholder_work_path_is_not_flagged(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "- `work/<エピック>/item.md` … エピックの目的\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_contract_paths_are_not_flagged(tmp_path: Path) -> None:
    _write(tmp_path, "docs/serve.md", "予測ログは `artifacts/serve/predictions/<名>/<日付>.jsonl`。\n")
    _write(tmp_path, "docs/method.md", "結果は `results/metrics_<variant>.yaml` に残す。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_template_copy_is_exempt(tmp_path: Path) -> None:
    _write(tmp_path, "docs/template-copy.md", "前案件の `work/EP-06-ds-experiment-loop/` ごと消す（`ISS-0007` も）。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_docs_subdirs_are_not_scanned(tmp_path: Path) -> None:
    _write(tmp_path, "docs/notes/old.md", "実装は `work/EP-23-loops/item.md`（`ISS-0007`）。\n")
    _write(tmp_path, "docs/archive/note.md", "当時の `work/EP-06-ds-experiment-loop/item.md`。\n")
    assert _errors(tmp_path) == []


# --- 走査対象の拡大：src/harness・tests・templates・.claude/skills ---


@pytest.mark.unit
def test_source_dirs_prose_is_scanned(tmp_path: Path) -> None:
    _write(tmp_path, "src/harness/foo.py", '"""役割。ISS-0007 の対処。"""\n')
    _write(tmp_path, "tests/test_foo.py", "# work/EP-06-ds-experiment-loop を参照\n")
    _write(tmp_path, "templates/experiment/train.py", "# 由来は work/E-0001 に残る\n")
    _write(tmp_path, ".claude/skills/x/SKILL.md", "手順は `ISS-0007` を参照。\n")
    errors = _errors(tmp_path)
    assert any("src/harness/foo.py:1" in m and "ISS-0007" in m for m in errors)
    assert any("tests/test_foo.py:1" in m and "work/EP-06-ds-experiment-loop" in m for m in errors)
    assert any("templates/experiment/train.py:1" in m and "work/E-0001" in m for m in errors)
    assert any(".claude/skills/x/SKILL.md:1" in m and "ISS-0007" in m for m in errors)


@pytest.mark.unit
def test_python_data_strings_are_not_flagged(tmp_path: Path) -> None:
    # .py の文字列リテラル（関数引数・アサーション＝テストの合成データ）は設計依存でないので拾わない。
    _write(
        tmp_path,
        "tests/test_bar.py",
        'def test_x() -> None:\n    make("work/EP-01/item.md")\n    assert "ISS-9999" in out\n',
    )
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_python_comment_scans_comment_body_only(tmp_path: Path) -> None:
    # データ文字列とコメントが同居する行：コメント本文だけを見る（データ側の ID は拾わない）。
    _write(tmp_path, "tests/test_baz.py", 'assert "ISS-9999" in out  # 存在しない課題を参照＝error\n')
    assert _errors(tmp_path) == []
    # コメント本文に具体単位を書けば拾う。
    _write(tmp_path, "tests/test_baz.py", "assert x  # work/EP-06-ds-experiment-loop で実装\n")
    assert any("tests/test_baz.py:1" in m and "work/EP-06" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_mutable_areas_are_not_scanned(tmp_path: Path) -> None:
    # issues/ 自身と work/ 自身は走査しない（一時単位どうしの相互参照は正当）。
    _write(tmp_path, "issues/ISS-0100-x.md", "関連: `work/EP-06-ds-experiment-loop` と `ISS-0007`。\n")
    _write(tmp_path, "work/EP-99/item.md", "先行は `work/EP-06-ds-experiment-loop`。参照 `ISS-0007`。\n")
    assert _errors(tmp_path) == []


# --- 検出：気づき ID（L-###）参照も work/・ISS と同じく error ---


@pytest.mark.unit
def test_durable_doc_referencing_learning_id_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/method.md", "この検査は `L-021` の教訓による。\n")
    errors = _errors(tmp_path)
    assert any("L-021" in m and "docs/method.md:1" in m and "気づき ID" in m for m in errors)
    # 教訓を本文の 1 文に書き下すと消える（先例は本文で自足させる）。
    _write(tmp_path, "docs/method.md", "この検査は、対象集合を機械的に導けるかを先に問う趣旨。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_learning_id_in_source_comment_is_error(tmp_path: Path) -> None:
    # src/tests のコメント・docstring の L-### も拾う（複製先で宙に浮く根拠参照）。
    _write(tmp_path, "src/harness/foo.py", '"""役割。fail closed（L-009）。"""\n')
    assert any("src/harness/foo.py:1" in m and "L-009" in m for m in _errors(tmp_path))
    # 文字列リテラルの気づき番号は合成データなので拾わない（learnings 白紙化テストが番号を入力に使う等）。
    _write(tmp_path, "tests/test_x.py", 'def test_x() -> None:\n    write("## L-999 前案件の気づき")\n')
    assert not any("L-999" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_learnings_md_itself_is_not_scanned(tmp_path: Path) -> None:
    # 定義元の learnings.md は案件領域（fork で白紙化）＝走査対象でない。自身の L-### 定義・相互参照を誤検知しない。
    _write(tmp_path, "docs/learnings.md", "## L-021 対象集合は機械導出\n関連 L-017・L-019。ISS-0007 起因。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_charter_md_is_case_area_and_not_scanned(tmp_path: Path) -> None:
    # charter.md は案件領域（init-project で白紙化）＝案件が自分の作業単位・課題・気づきを参照するのは正当。
    _write(tmp_path, "docs/charter.md", "設計は `work/EP-01-foo/item.md`（`ISS-0007`・`L-021`）に基づく。\n")
    assert _errors(tmp_path) == []
    # 一方、恒久資産の docs（method.md 等）は同じ参照で error になる（対比）。
    _write(tmp_path, "docs/method.md", "設計は `work/EP-01-foo/item.md` に基づく。\n")
    assert any("docs/method.md" in m and "work/EP-01-foo" in m for m in _errors(tmp_path))


# --- 免除リストの規約：理由は空でない文字列が必須 ---


@pytest.mark.unit
def test_every_exempt_reason_is_nonempty() -> None:
    for name, reason in doc_source_lint._EXEMPT.items():
        assert isinstance(reason, str) and reason.strip(), f"_EXEMPT[{name!r}] の理由が空"


@pytest.mark.unit
def test_blank_exempt_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(doc_source_lint._EXEMPT, "docs/ops.md", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        doc_source_lint.run_checks(tmp_path)


# --- 配線：INVARIANT_CHECKS に載っている ---


@pytest.mark.unit
def test_doc_source_lint_is_wired_into_invariant_checks() -> None:
    from harness import checks

    assert doc_source_lint.run_checks in checks.INVARIANT_CHECKS


# --- 回帰テスト：現リポの複製後も残る資産が work/・ISS を根拠に参照しない ---


@pytest.mark.integration
def test_real_repo_durable_assets_have_no_mutable_refs() -> None:
    errors = [p for p in doc_source_lint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]
