"""画面から作業単位を足す部分のテスト。

足すのは正本（`work/` のファイル）だけで、WBS 側には何も持たない。分解した親から日程が子へ移ること
（子ができた瞬間に親の日程は導出値になるので、宣言を残すと検査に失敗する）を確かめる。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from fastapi.testclient import TestClient

from harness import pm
from harness.deliver import wbs_lint
from harness.deliver.adder import add_child
from harness.deliver.editor import EditRejected
from harness.deliver.server import create_app
from harness.models import Kind, Status

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)
TOKEN = "test-token"


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _items(root: Path) -> dict[str, Any]:
    nodes, _ = pm.load_tree(root)

    def walk(ns: list[pm.Node]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for node in ns:
            out[node.item.id] = node.item
            out.update(walk(node.children))
        return out

    return walk(nodes)


def test_a_child_gets_the_next_free_id(tmp_path: Path) -> None:
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(epic / "T-0007-a.md", {"id": "T-0007", "kind": "task", "status": "todo"})

    new_id = add_child(tmp_path, "EP-90", today=TODAY)
    assert new_id == "T-0008"  # 既存の最大＋1
    item = _items(tmp_path)[new_id]
    assert item.kind is Kind.task
    assert item.status is Status.todo
    assert item.created == TODAY
    assert (epic / f"{new_id}-新しい作業.md").is_file()


def test_the_first_child_inherits_the_parents_dates(tmp_path: Path) -> None:
    """未分解の単位を分解すると、その単位の日程は最初の子へ移る。

    子ができた瞬間、親の日程は子から導く値になる（宣言を残すと検査に失敗する）。分解という操作の意味に
    合わせて移すことで、1 手で分解できて不変条件も保たれる。
    """
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(
        epic / "item.md",
        {
            "id": "EP-90",
            "kind": "epic",
            "status": "todo",
            "start": "2026-08-03",
            "due": "2026-08-07",
            "effort_days": 4.0,
        },
    )
    new_id = add_child(tmp_path, "EP-90", today=TODAY)
    items = _items(tmp_path)
    assert (items[new_id].start, items[new_id].due) == (date(2026, 8, 3), date(2026, 8, 7))
    assert items[new_id].effort_days == pytest.approx(4.0)
    assert items["EP-90"].start is None and items["EP-90"].due is None  # 親からは外れる
    assert not [p for p in wbs_lint.check(tmp_path, today=TODAY) if p.level == "error"]


def test_a_later_child_does_not_take_dates_from_the_parent(tmp_path: Path) -> None:
    """2 人目以降は移すものが無い（親は既に日程を持っていない）。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(
        epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"}
    )
    first = add_child(tmp_path, "EP-90", today=TODAY)
    second = add_child(tmp_path, "EP-90", today=TODAY)
    items = _items(tmp_path)
    assert items[first].start == date(2026, 8, 3)
    assert items[second].start is None
    assert second != first


def test_a_top_level_unit_can_be_added(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir(parents=True)
    new_id = add_child(tmp_path, None, today=TODAY)
    assert (tmp_path / "work" / f"{new_id}-新しい作業.md").is_file()


def test_a_file_unit_cannot_take_children(tmp_path: Path) -> None:
    """ファイル 1 つで表した軽い単位の下には置けない（親はフォルダで表すため）。理由を出して断る。"""
    _write(tmp_path / "work" / "T-0001-a.md", {"id": "T-0001", "kind": "task", "status": "todo"})
    with pytest.raises(EditRejected) as caught:
        add_child(tmp_path, "T-0001", today=TODAY)
    assert "フォルダ" in str(caught.value)


def test_adding_through_the_server_needs_the_token(tmp_path: Path) -> None:
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        epic / "T-0001-a.md",
        {"id": "T-0001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    client = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1")

    refused = client.post("/add", json={"parent": "EP-90"})
    assert refused.status_code == 403
    assert len(_items(tmp_path)) == 2

    added = client.post("/add", json={"parent": "EP-90"}, headers={"X-WBS-Token": TOKEN})
    assert added.status_code == 200, added.text
    assert added.json()["id"] in _items(tmp_path)


def test_the_edit_page_offers_the_add_controls(tmp_path: Path) -> None:
    """フォルダの単位には「＋」が出て、最上位に足す操作も画面にある（足し方が分からない、を無くす）。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        epic / "T-0001-a.md",
        {"id": "T-0001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    page = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1").get("/")
    assert 'class="add" type="button" data-ref="EP-90"' in page.text
    assert 'data-ref="T-0001" title' not in page.text  # ファイルの単位には出さない
    assert 'id="addtop"' in page.text
