"""画面からの操作を 1 手戻す（Ctrl+Z）のテスト。

戻す先は**編集の場（作業用の写し）**。画面からの操作は正本を直接書かないので、Ctrl+Z も写しの中の操作になる
（正本を戻すのは取り込み以後＝git の領分）。編集は前の値へ、追加は消す（分解でできたフォルダも片づける）、
削除は復元する。別の手で写しが動いていたら、推測で部分適用せず打ち切る（fail-closed）。redo は持たない。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from fastapi.testclient import TestClient

from harness import pm
from harness.deliver.server import create_app

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)
TOKEN = "test-token"
AUTH = {"X-WBS-Token": TOKEN}


def _live(root: Path) -> Path:
    """画面からの書き込み先（編集の場＝作業用の写し）。正本へは「取り込む」ときだけ書かれる。"""
    return root / ".harness" / "wbs-edit" / "tree"


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _ids(root: Path) -> set[str]:
    nodes, _ = pm.load_tree(_live(root))

    def walk(ns: list[pm.Node]) -> set[str]:
        out: set[str] = set()
        for node in ns:
            out.add(node.item.id)
            out |= walk(node.children)
        return out

    return walk(nodes)


def _status_of(root: Path, item_id: str) -> str:
    nodes, _ = pm.load_tree(_live(root))

    def find(ns: list[pm.Node]) -> str | None:
        for node in ns:
            if node.item.id == item_id:
                return node.item.status.value
            got = find(node.children)
            if got is not None:
                return got
        return None

    got = find(nodes)
    assert got is not None
    return got


def _scaffold(root: Path) -> None:
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


def _client(root: Path) -> TestClient:
    return TestClient(create_app(root, today=TODAY, token=TOKEN), base_url="http://127.0.0.1")


def test_undo_puts_an_edited_value_back(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    client = _client(tmp_path)
    assert (
        client.post(
            "/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH
        ).status_code
        == 200
    )
    assert _status_of(tmp_path, "T-9001") == "in-progress"

    reply = client.post("/undo", headers=AUTH)
    assert reply.status_code == 200, reply.text
    assert _status_of(tmp_path, "T-9001") == "todo"  # 前の値に戻った


def test_undo_removes_an_added_unit(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    client = _client(tmp_path)
    added = client.post("/add", json={"ref": "T-9001", "where": "below"}, headers=AUTH)
    new_id = added.json()["id"]
    assert new_id in _ids(tmp_path)

    assert client.post("/undo", headers=AUTH).status_code == 200
    assert new_id not in _ids(tmp_path)  # 足した単位が消えた
    assert _ids(tmp_path) == {"EP-90", "T-9001", "T-9002"}


def test_undo_restores_a_removed_unit(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    client = _client(tmp_path)
    assert client.post("/remove", json={"ref": "T-9002"}, headers=AUTH).status_code == 200
    assert "T-9002" not in _ids(tmp_path)

    assert client.post("/undo", headers=AUTH).status_code == 200
    assert "T-9002" in _ids(tmp_path)  # 消した単位が戻った


def test_undo_of_an_add_that_decomposed_a_parent_also_undoes_the_folder(tmp_path: Path) -> None:
    """ファイル 1 つの単位に子を足すと分解（ファイル→フォルダ）が起きる。取り消しでフォルダごと元に戻す。"""
    (tmp_path / "work").mkdir(parents=True)
    _write(
        tmp_path / "work" / "T-0001-sekkei.md",
        {"id": "T-0001", "kind": "task", "status": "todo", "title": "設計", "start": "2026-08-03", "due": "2026-08-07"},
    )
    client = _client(tmp_path)
    added = client.post("/add", json={"ref": "T-0001", "where": "child"}, headers=AUTH)
    new_id = added.json()["id"]
    assert (_live(tmp_path) / "work" / "T-0001-sekkei" / "item.md").is_file()  # 分解された

    assert client.post("/undo", headers=AUTH).status_code == 200
    assert new_id not in _ids(tmp_path)
    assert (_live(tmp_path) / "work" / "T-0001-sekkei.md").is_file()  # ファイルに戻った
    assert not (_live(tmp_path) / "work" / "T-0001-sekkei").exists()  # 空フォルダも片づいた
    # 日程も親へ戻っている（分解のときに子へ移したぶん）。
    item = frontmatter.loads((_live(tmp_path) / "work" / "T-0001-sekkei.md").read_text(encoding="utf-8"))
    assert item["start"] == "2026-08-03"


def test_undo_with_nothing_to_undo_is_refused(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    reply = _client(tmp_path).post("/undo", headers=AUTH)
    assert reply.status_code == 409
    assert "戻す操作が無い" in reply.json()["detail"]


def test_undo_stops_when_the_source_moved_by_another_hand(tmp_path: Path) -> None:
    """操作の後に別の手で**写し**が動いていたら、指紋が合わず打ち切る（推測で部分適用しない）。"""
    _scaffold(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)
    # 別の手（エディタ等）が編集の場のファイルを触ったことにする。
    path = _live(tmp_path) / "work" / "EP-90-alpha" / "T-9001-a.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n# 別の手による追記\n", encoding="utf-8")

    reply = client.post("/undo", headers=AUTH)
    assert reply.status_code == 409
    assert "別の手" in reply.json()["detail"]
    # 打ち切ったので、次の取り消しも「戻す操作が無い」（スタックは消えている）。
    assert client.post("/undo", headers=AUTH).json()["detail"] == "戻す操作が無い"


def test_undo_needs_the_token(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)
    assert client.post("/undo").status_code == 403
    assert _status_of(tmp_path, "T-9001") == "in-progress"  # 合言葉なしでは戻らない


def test_changing_an_upper_level_changes_all_its_descendants(tmp_path: Path) -> None:
    """上位の行の状態は子から導く値なので、まとめて変える＝**末端の正本を書く**（親に値を持たせない）。"""
    _scaffold(tmp_path)
    client = _client(tmp_path)
    reply = client.post("/cascade", json={"ref": "EP-90", "field": "status", "value": "in-progress"}, headers=AUTH)
    assert reply.status_code == 200, reply.text
    assert reply.json()["changed"] == 2  # 配下の末端 2 件
    assert _status_of(tmp_path, "T-9001") == "in-progress"
    assert _status_of(tmp_path, "T-9002") == "in-progress"


def test_a_cascade_can_be_undone_in_one_step(tmp_path: Path) -> None:
    """まとめての変更も 1 手で戻る（1 操作＝1 手として積む）。"""
    _scaffold(tmp_path)
    client = _client(tmp_path)
    client.post("/cascade", json={"ref": "EP-90", "field": "status", "value": "in-progress"}, headers=AUTH)
    assert client.post("/undo", headers=AUTH).status_code == 200
    assert _status_of(tmp_path, "T-9001") == "todo"
    assert _status_of(tmp_path, "T-9002") == "todo"


def test_a_cascade_that_would_break_a_check_writes_nothing(tmp_path: Path) -> None:
    """まとめて書いた結果、検査に落ちるなら全部書き戻して断る（部分適用しない）。

    done には対応するテスト（verified_by）が要る、という既存の検査に当てて確かめる。
    """
    _scaffold(tmp_path)
    client = _client(tmp_path)
    reply = client.post("/cascade", json={"ref": "EP-90", "field": "status", "value": "done"}, headers=AUTH)
    assert reply.status_code == 409
    assert _status_of(tmp_path, "T-9001") == "todo"  # 1 件も書き換わっていない
    assert _status_of(tmp_path, "T-9002") == "todo"
