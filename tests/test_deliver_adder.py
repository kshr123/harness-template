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
from harness.deliver.adder import add_child, add_sibling
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


def _order(root: Path) -> list[str]:
    """表示順（木をたどった順）の ID の並び。"""
    nodes, _ = pm.load_tree(root)

    def walk(ns: list[pm.Node]) -> list[str]:
        out: list[str] = []
        for node in ns:
            out.append(node.item.id)
            out.extend(walk(node.children))
        return out

    return walk(nodes)


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


def test_a_file_unit_becomes_a_folder_when_it_gets_a_child(tmp_path: Path) -> None:
    """ファイル 1 つで表した単位に子を足す＝分解する。親はフォルダで表す決まりなので、フォルダへ移す。

    どの階層でも子を足せる必要がある（ファイルの単位だから足せない、では使えない）。
    """
    _write(
        tmp_path / "work" / "T-0001-sekkei.md",
        {"id": "T-0001", "kind": "task", "status": "todo", "title": "設計", "start": "2026-08-03", "due": "2026-08-07"},
    )
    child = add_child(tmp_path, "T-0001", today=TODAY)
    assert (tmp_path / "work" / "T-0001-sekkei" / "item.md").is_file()  # フォルダの単位になった
    assert not (tmp_path / "work" / "T-0001-sekkei.md").exists()
    items = _items(tmp_path)
    assert items[child].start == date(2026, 8, 3)  # 日程は最初の子へ移る
    assert items["T-0001"].start is None
    assert _order(tmp_path) == ["T-0001", child]


def test_the_edit_page_lets_any_work_row_take_a_child(tmp_path: Path) -> None:
    """どの作業単位の行にも「中に足す」先が載っている（Lv1 だけ、にならない）。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        epic / "T-0001-a.md",
        {"id": "T-0001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    page = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1").get("/").text
    task_row = next(part for part in page.split("<tr") if "T-0001" in part)
    assert 'data-holder="T-0001"' in task_row


def test_adding_through_the_server_needs_the_token(tmp_path: Path) -> None:
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        epic / "T-0001-a.md",
        {"id": "T-0001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    client = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1")

    refused = client.post("/add", json={"ref": "EP-90", "where": "child"})
    assert refused.status_code == 403
    assert len(_items(tmp_path)) == 2

    added = client.post("/add", json={"ref": "EP-90", "where": "child"}, headers={"X-WBS-Token": TOKEN})
    assert added.status_code == 200, added.text
    assert added.json()["id"] in _items(tmp_path)


def test_the_edit_page_carries_what_the_menu_needs(tmp_path: Path) -> None:
    """足す操作は右クリックに寄せる（ボタンを行に置かない）。行はどの階層かと足せる先を持つ。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        epic / "T-0001-a.md",
        {"id": "T-0001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    page = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1").get("/")
    assert 'class="add"' not in page.text  # 行に「＋」は置かない
    epic_row = next(part for part in page.text.split("<tr") if "EP-90" in part)
    task_row = next(part for part in page.text.split("<tr") if "T-0001" in part)
    assert 'data-level="1"' in epic_row and 'data-holder="EP-90"' in epic_row
    assert 'data-level="2"' in task_row and 'data-holder="T-0001"' in task_row  # どの単位も中に持てる
    assert 'id="menu"' in page.text


def test_a_sibling_can_be_placed_above_or_below(tmp_path: Path) -> None:
    """右クリックの「上に足す／下に足す」が、その位置に入る。

    並びはファイル名の順（実質 ID 順）で ID は最大＋1 でしか採れないため、順序を書かないと「上」は
    表現できない。最初の挿入でその置き場の並びを 10 刻みで書き出し、新しい行にはその間の値を与える。
    """
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(epic / "T-0001-a.md", {"id": "T-0001", "kind": "task", "status": "todo", "title": "設計"})
    _write(epic / "T-0002-b.md", {"id": "T-0002", "kind": "task", "status": "todo", "title": "実装"})

    above = add_sibling(tmp_path, "T-0002", above=True, today=TODAY)
    assert _order(tmp_path) == ["EP-90", "T-0001", above, "T-0002"]

    below = add_sibling(tmp_path, "T-0001", above=False, today=TODAY)
    assert _order(tmp_path) == ["EP-90", "T-0001", below, above, "T-0002"]


def test_the_written_order_is_spaced_so_more_fit_between(tmp_path: Path) -> None:
    """並び順は詰めずに刻んで振る（次の挿入が 1 行の書き足しで済む）。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(epic / "T-0001-a.md", {"id": "T-0001", "kind": "task", "status": "todo"})
    add_sibling(tmp_path, "T-0001", above=False, today=TODAY)
    orders = [item.order for item in _items(tmp_path).values() if item.id.startswith("T-")]
    assert orders == [10, 20]


def test_a_project_without_any_order_keeps_the_filename_order(tmp_path: Path) -> None:
    """順序を書いていない案件の並びは、これまでどおりファイル名の順（既定の見え方を変えない）。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(epic / "T-0002-b.md", {"id": "T-0002", "kind": "task", "status": "todo"})
    _write(epic / "T-0001-a.md", {"id": "T-0001", "kind": "task", "status": "todo"})
    assert _order(tmp_path) == ["EP-90", "T-0001", "T-0002"]


def test_a_milestone_can_be_added(tmp_path: Path) -> None:
    """マイルストーン（◆）を足せる。期間ゼロの印なので start を持たず、期日は基準日にする（あとで直せる）。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        epic / "T-0001-a.md",
        {"id": "T-0001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    new_id = add_child(tmp_path, "EP-90", today=TODAY, milestone=True)
    item = _items(tmp_path)[new_id]
    assert item.milestone is True
    assert item.start is None
    assert item.due == TODAY


def test_the_menu_offers_a_milestone(tmp_path: Path) -> None:
    _write(tmp_path / "work" / "T-0001-a.md", {"id": "T-0001", "kind": "task", "status": "todo"})
    page = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1").get("/").text
    assert "マイルストーンを下に追加" in page
