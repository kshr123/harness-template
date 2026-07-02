"""プロジェクト管理の中核ロジックのテスト。

作る側（pm）と確かめる側（テスト）を分け、期待する動きをテストで固定する。
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from harness import pm


def _write(path: Path, meta: dict[str, object], body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body)
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _scaffold(root: Path) -> None:
    """work/EP-01（詳しく分解済み・子タスク2件）と EP-02（未分解）を作る。"""
    # done タスクが指す先＝実在するテスト（完了↔検証の結びつけ）。
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    ep1 = root / "work" / "EP-01-foundation"
    _write(ep1 / "item.md", {"id": "EP-01", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    t1: dict[str, object] = {"id": "T-0001", "kind": "task", "status": "done"}
    t1["verified_by"] = ["tests/test_a.py::test_a"]
    _write(ep1 / "T-0001-a.md", t1)
    t2: dict[str, object] = {"id": "T-0002", "kind": "task", "status": "todo", "depends_on": ["T-0001"]}
    _write(ep1 / "T-0002-b.md", t2)
    ep2 = root / "work" / "EP-02-dev"
    _write(ep2 / "item.md", {"id": "EP-02", "kind": "epic", "status": "todo", "plan": "outline"})


def test_outline_epic_without_children_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # EP-02 は未分解（outline・子なし）でも失敗にしない。
    assert not [p for p in pm.lint(tmp_path) if p.level == "error"]


def test_duplicate_id_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 同じ ID をもう 1 つ作る＝重複＝失敗。
    dup: dict[str, object] = {"id": "T-0001", "kind": "task", "status": "todo"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0001-dup.md", dup)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("重複" in p.message for p in errors)


def test_dangling_depends_on_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 存在しない単位に依存＝参照エラー＝失敗。
    x: dict[str, object] = {"id": "T-0009", "kind": "task", "status": "todo", "depends_on": ["T-9999"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0009-x.md", x)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("T-9999" in p.message for p in errors)


def test_done_task_without_verified_by_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # done なのに対応するテスト（verified_by）が無い＝失敗（自己申告完了を防ぐ）。
    d: dict[str, object] = {"id": "T-0003", "kind": "task", "status": "done"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0003-d.md", d)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("verified_by" in p.message for p in errors)


def test_done_task_with_missing_test_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # verified_by が実在しないテストを指す＝失敗。
    d: dict[str, object] = {"id": "T-0004", "kind": "task", "status": "done", "verified_by": ["tests/nope.py::x"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0004-e.md", d)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("nope.py" in p.message for p in errors)


def test_investigation_done_requires_conclusion(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # done の調査に「## 結論」が無い＝失敗（verified_by の代わりの検査）。
    d: dict[str, object] = {"id": "INV-0001", "kind": "investigation", "status": "done"}
    _write(tmp_path / "work" / "EP-01-foundation" / "INV-0001-x.md", d, body="調べた。")
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("結論" in p.message for p in errors)


def test_investigation_with_conclusion_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    d: dict[str, object] = {"id": "INV-0002", "kind": "investigation", "status": "done"}
    _write(tmp_path / "work" / "EP-01-foundation" / "INV-0002-y.md", d, body="## 結論\nこう分かった。")
    # 調査は verified_by 不要。結論があればエラーにしない。
    assert not [p for p in pm.lint(tmp_path) if p.level == "error" and "INV-0002" in p.message]


def test_pending_human_section_lists_blocked_and_questions(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # blocked のタスクと [要確認] を「人の判断待ち」に集約する。
    b: dict[str, object] = {"id": "T-0005", "kind": "task", "status": "blocked"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0005-b.md", b, body="本文に [要確認] を含む")
    status = pm.render_status(tmp_path)
    assert "人の判断待ち" in status
    assert "T-0005" in status
    assert "[要確認]" in status


def test_render_status_counts_leaves(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    status = pm.render_status(tmp_path)
    assert "EP-01" in status
    assert "1/2" in status  # 末端タスク done 1 / 総数 2
    assert "未分解" in status  # EP-02 は outline で子なし


def test_broken_frontmatter_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # status が不正値＝型検証で失敗。
    bad: dict[str, object] = {"id": "T-0010", "kind": "task", "status": "unknown"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0010-bad.md", bad)
    assert [p for p in pm.lint(tmp_path) if p.level == "error"]


def test_spec_lint_requires_headings(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    spec = tmp_path / "work" / "EP-01-foundation" / "E-0001-exp" / "SPEC.md"
    _write(spec.parent / "item.md", {"id": "E-0001", "kind": "experiment", "status": "todo"})
    spec.write_text("# SPEC\n## 目的\nあれ\n", encoding="utf-8")
    assert [p for p in pm.spec_lint(tmp_path) if p.level == "error"]
    spec.write_text(
        "# SPEC\n## 目的\nx\n## 受け入れ基準\nx\n## やらないこと\nx\n## 最後の確認手順\nx\n",
        encoding="utf-8",
    )
    assert not pm.spec_lint(tmp_path)
