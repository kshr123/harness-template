"""編集の場（作業用の写し）と取り込みのテスト。

いちばん大事な性質は 1 つ：**取り込むまで正本は 1 バイトも変わらない**。画面からいくら直しても、別の手
（コミットするエージェント・エディタ・git）とぶつからない、という保証の実体がこれ。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from fastapi.testclient import TestClient

from harness import pm
from harness.deliver import session as session_mod
from harness.deliver.server import create_app

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)
TOKEN = "test-token"
AUTH = {"X-WBS-Token": TOKEN}


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


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


def _fingerprints(root: Path) -> dict[str, str]:
    """正本の入力ファイルの指紋（1 バイトでも変われば変わる）。"""
    return session_mod.digests_of(root, session_mod.inputs_of(root))


def _client(root: Path) -> TestClient:
    return TestClient(create_app(root, today=TODAY, token=TOKEN, fresh=True), base_url="http://127.0.0.1")


def _status_of(root: Path, item_id: str) -> str:
    nodes, _ = pm.load_tree(root)

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


def test_editing_never_touches_the_source_until_it_is_applied(tmp_path: Path) -> None:
    """直す・足す・消す・まとめて変える・戻す、をひと通りやっても正本は 1 バイトも変わらない。"""
    _scaffold(tmp_path)
    before = _fingerprints(tmp_path)
    client = _client(tmp_path)

    assert (
        client.post(
            "/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH
        ).status_code
        == 200
    )
    added = client.post("/add", json={"ref": "T-9001", "where": "below"}, headers=AUTH)
    assert added.status_code == 200
    assert client.post("/remove", json={"ref": "T-9002"}, headers=AUTH).status_code == 200
    assert (
        client.post("/cascade", json={"ref": "EP-90", "field": "status", "value": "todo"}, headers=AUTH).status_code
        == 200
    )
    assert client.post("/undo", headers=AUTH).status_code == 200

    assert _fingerprints(tmp_path) == before  # 正本は無傷


def test_the_screen_shows_what_would_change_before_applying(tmp_path: Path) -> None:
    """取り込む前に「行がどう変わるか」と「ファイルの生差分」の両方を見せる。"""
    _scaffold(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)

    seen = client.get("/changes").json()
    assert seen["files"], "変えたファイルが出ていない"
    assert any("status" in line and "in-progress" in line for line in seen["rows"])  # 行の変化
    assert any("+status: in-progress" in entry["diff"] for entry in seen["diffs"])  # 生差分
    assert seen["confirm"]


def test_applying_writes_exactly_what_changed(tmp_path: Path) -> None:
    """取り込むと、写しで変えたファイルだけが正本に書かれる（余計な 1 ファイルも書かない）。"""
    _scaffold(tmp_path)
    before = _fingerprints(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)
    changed = client.get("/changes").json()

    applied = client.post("/apply", json={"confirm": changed["confirm"]}, headers=AUTH)
    assert applied.status_code == 200, applied.text
    assert applied.json()["written"] == changed["files"]
    after = _fingerprints(tmp_path)
    assert {rel for rel in after if after[rel] != before.get(rel)} == set(changed["files"])
    assert _status_of(tmp_path, "T-9001") == "in-progress"


def test_apply_is_refused_when_the_source_moved_and_writes_nothing(tmp_path: Path) -> None:
    """写しを取った後に正本が別の手で動いていたら、取り込みを打ち切る（部分適用しない）。"""
    _scaffold(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)
    # 別の手（エディタ・git 等）が同じファイルを触った。
    path = tmp_path / "work" / "EP-90-alpha" / "T-9001-a.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n# 別の手による追記\n", encoding="utf-8")
    before = _fingerprints(tmp_path)

    reply = client.post("/apply", json={}, headers=AUTH)
    assert reply.status_code == 409
    assert "別の手" in reply.json()["detail"]
    assert _fingerprints(tmp_path) == before  # 1 バイトも書いていない


def test_apply_is_refused_when_it_would_break_a_check(tmp_path: Path) -> None:
    """取り込んだ後の姿を先に検査し、増えた指摘があれば書かない（done には対応するテストが要る、で試す）。"""
    _scaffold(tmp_path)
    client = _client(tmp_path)
    # 写しの中では検査が通らない値も置ける（編集の場なので）。ここでは正本側の検査で弾かれることを見る。
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)
    (tmp_path / ".harness" / "wbs-edit" / "tree" / "work" / "EP-90-alpha" / "T-9001-a.md").write_text(
        "---\nid: T-9001\nkind: task\nstatus: done\nstart: 2026-08-03\ndue: 2026-08-07\n---\n", encoding="utf-8"
    )
    before = _fingerprints(tmp_path)

    reply = client.post("/apply", json={}, headers=AUTH)
    assert reply.status_code == 409
    assert "verified_by" in reply.json()["detail"]
    assert _fingerprints(tmp_path) == before


def test_discard_throws_the_working_copy_away(tmp_path: Path) -> None:
    """破棄すると写しをいまの正本から取り直す（正本は変わらない）。"""
    _scaffold(tmp_path)
    before = _fingerprints(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)
    assert client.get("/changes").json()["files"]

    dropped = client.post("/discard", headers=AUTH)
    assert dropped.status_code == 200
    assert dropped.json()["dropped"] == 1
    assert client.get("/changes").json()["files"] == []
    assert _fingerprints(tmp_path) == before


def test_the_working_copy_survives_a_restart(tmp_path: Path) -> None:
    """サーバを開き直しても書きかけは残る（写しはディスクにあるので、続きから直せる）。"""
    _scaffold(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)

    again = TestClient(create_app(tmp_path, today=TODAY, token=TOKEN), base_url="http://127.0.0.1")
    assert again.get("/changes").json()["files"], "開き直したら書きかけが消えていた"


def test_apply_and_discard_need_the_token(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)
    assert client.post("/apply", json={}).status_code == 403
    assert client.post("/discard").status_code == 403


def test_a_second_apply_after_more_edits_succeeds(tmp_path: Path) -> None:
    """取り込んだ後に続けて編集して 2 度目に取り込んでも、自分の apply を「別の手」と誤検知して 409 にならない（A）。

    取り込みで土台は「いまの正本」へ進む。サーバが古い土台を握り続けると、1 度目の apply で動いた正本が
    drift と見なされ 2 度目が 409 になる（「続けて編集できる」設計に反する）。
    """
    _scaffold(tmp_path)
    client = _client(tmp_path)
    client.post("/edit", json={"ref": "T-9001", "field": "status", "value": "in-progress"}, headers=AUTH)
    first = client.get("/changes").json()
    assert client.post("/apply", json={"confirm": first["confirm"]}, headers=AUTH).status_code == 200
    # 続けて別の行を直し、もう一度取り込む。
    client.post("/edit", json={"ref": "T-9002", "field": "status", "value": "in-progress"}, headers=AUTH)
    second = client.get("/changes").json()
    assert second["files"], "2 度目の変更が写しに出ていない"
    applied = client.post("/apply", json={"confirm": second["confirm"]}, headers=AUTH)
    assert applied.status_code == 200, applied.text
    assert _status_of(tmp_path, "T-9002") == "in-progress"
    # 取り込む変更が無くなった状態での apply は従来どおり拒否される（fail-closed は維持）。
    assert client.post("/apply", json={}, headers=AUTH).status_code == 409
