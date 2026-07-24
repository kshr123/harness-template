"""画面から行を消す部分と、右クリックの操作のテスト。

消すのは正本だけ。手動行は上書きファイルの塊と、それを指している節の項目を**両方**取る（片方だけだと
参照切れになる）。配下を持つ単位はまとめて消さない（何が消えるか画面から見えないため）。
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
from harness.deliver.editor import EditRejected
from harness.deliver.overlay import load_overlay
from harness.deliver.remover import remove
from harness.deliver.server import create_app

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)
TOKEN = "test-token"


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _ids(root: Path) -> set[str]:
    nodes, _ = pm.load_tree(root)

    def walk(ns: list[pm.Node]) -> set[str]:
        out: set[str] = set()
        for node in ns:
            out.add(node.item.id)
            out |= walk(node.children)
        return out

    return walk(nodes)


def _scaffold(root: Path) -> Path:
    epic = root / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        epic / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    _write(
        epic / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    return epic


def test_a_leaf_unit_is_removed(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    remove(tmp_path, "T-9002", today=TODAY)
    assert _ids(tmp_path) == {"EP-90", "T-9001"}


def test_a_unit_with_children_is_refused(tmp_path: Path) -> None:
    """配下を持つ単位はまとめて消さない（何が消えるか画面から見えないため）。"""
    _scaffold(tmp_path)
    with pytest.raises(EditRejected) as caught:
        remove(tmp_path, "EP-90", today=TODAY)
    assert "配下" in str(caught.value)
    assert _ids(tmp_path) == {"EP-90", "T-9001", "T-9002"}


def test_an_emptied_folder_unit_can_then_be_removed(tmp_path: Path) -> None:
    """配下を先に消せば、フォルダの単位も消せる（フォルダごと片づく）。"""
    epic = _scaffold(tmp_path)
    remove(tmp_path, "T-9001", today=TODAY)
    remove(tmp_path, "T-9002", today=TODAY)
    remove(tmp_path, "EP-90", today=TODAY)
    assert _ids(tmp_path) == set()
    assert not epic.exists()


def test_removing_something_others_depend_on_is_refused(tmp_path: Path) -> None:
    """他の単位が先行として指している単位を消すと参照切れになるので、書き戻して断る。"""
    epic = _scaffold(tmp_path)
    _write(
        epic / "T-9002-b.md",
        {
            "id": "T-9002",
            "kind": "task",
            "status": "todo",
            "start": "2026-08-10",
            "due": "2026-08-12",
            "depends_on": ["T-9001"],
        },
    )
    with pytest.raises(EditRejected):
        remove(tmp_path, "T-9001", today=TODAY)
    assert "T-9001" in _ids(tmp_path)  # 書き戻っている
    assert not [p for p in wbs_lint.check(tmp_path, today=TODAY) if p.level == "error"]


def test_a_manual_row_and_the_section_pointing_at_it_go_together(tmp_path: Path) -> None:
    """手動行を消すと、それを指している節の項目も一緒に消える（片方だけ残すと参照切れ）。"""
    _scaffold(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "wbs.yaml").write_text(
        "# 見本\n"
        "sections:\n"
        "  - name: フェーズ1\n"
        "    entries:\n"
        "      - work: EP-90\n"
        "      - row: W-001\n"
        "rows:\n"
        "  - id: W-001\n"
        "    name: 承認\n"
        "    status: todo\n",
        encoding="utf-8",
    )
    remove(tmp_path, "W-001", today=TODAY)
    text = (tmp_path / "docs" / "wbs.yaml").read_text(encoding="utf-8")
    assert "W-001" not in text
    assert "# 見本" in text  # 他は動かさない
    assert load_overlay(tmp_path).rows == []
    assert not [p for p in wbs_lint.check(tmp_path, today=TODAY) if p.level == "error"]


def test_removing_through_the_server_needs_the_token(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    client = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1")
    refused = client.post("/remove", json={"ref": "T-9002"})
    assert refused.status_code == 403
    assert "T-9002" in _ids(tmp_path)

    done = client.post("/remove", json={"ref": "T-9002"}, headers={"X-WBS-Token": TOKEN})
    assert done.status_code == 200, done.text
    assert "T-9002" not in _ids(tmp_path)


def test_removing_a_unit_with_children_reports_why(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    client = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1")
    reply = client.post("/remove", json={"ref": "EP-90"}, headers={"X-WBS-Token": TOKEN})
    assert reply.status_code == 409
    assert "配下" in reply.json()["detail"]


def test_rows_carry_what_the_menu_needs(tmp_path: Path) -> None:
    """右クリックの操作に要る情報（自分・この下の足し先・同じ階層の足し先）が行に載っている。"""
    _scaffold(tmp_path)
    page = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1").get("/").text
    epic_row = next(part for part in page.split("<tr") if "EP-90" in part)
    task_row = next(part for part in page.split("<tr") if "T-9001" in part)
    assert 'data-ref="EP-90"' in epic_row and 'data-holder="EP-90"' in epic_row
    assert 'data-ref="T-9001"' in task_row
    assert 'data-parent="EP-90"' in task_row  # 同じ階層＝EP-90 の下
    assert 'data-holder="T-9001"' in task_row  # どの作業単位にも中に足せる（足すときに分解される）
    assert 'id="menu"' in page


def test_each_cell_carries_its_column_so_the_menu_can_branch(tmp_path: Path) -> None:
    """右クリックのメニューを列ごとに出し分けるため、各セルが表示列の名前（data-col）を持っている。"""
    _scaffold(tmp_path)
    page = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1").get("/").text
    task_row = next(part for part in page.split("<tr") if "T-9001" in part)
    # 末端行なので、編集できる列（状態・日付）も導出だけの列（進捗・ガント）も同じ行に揃う。
    for col in ("no", "name", "status", "start", "due", "days", "act_start", "progress", "gantt"):
        assert f'data-col="{col}"' in task_row, col
