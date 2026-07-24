"""編集面のローカルサーバのテスト。

書き込みの口を開けるので、守りが実際に効いているか（合言葉・名乗ったホスト名・競合検出）を確かめる。
画面そのものは閲覧用と同じ描き方なので、ここでは「直せる欄に書き戻し先の目印が付くこと」だけを見る。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harness.deliver.editor import file_digest
from harness.deliver.server import Idle, create_app, host_is_allowed, new_token

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)
TOKEN = "test-token"

_ITEM = """\
---
id: T-9001
kind: task
status: todo
title: 設計
start: 2026-08-03
due: 2026-08-07
---
"""


def _live(root: Path) -> Path:
    """画面からの書き込み先（編集の場＝作業用の写し）。正本へは「取り込む」ときだけ書かれる。"""
    return root / ".harness" / "wbs-edit" / "tree"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "T-9001-a.md").write_text(_ITEM, encoding="utf-8")
    return tmp_path


def _client(root: Path) -> TestClient:
    """名乗るホスト名を手元にして繋ぐ（既定の testserver では守りに弾かれるのが正しい）。"""
    return TestClient(create_app(root, today=TODAY, token=TOKEN), base_url="http://127.0.0.1")


def test_allowed_hosts_are_only_local() -> None:
    assert host_is_allowed("127.0.0.1:8000")
    assert host_is_allowed("localhost")
    assert not host_is_allowed("attacker.example.com")
    assert not host_is_allowed(None)


def test_idle_expires_only_after_the_timeout() -> None:
    idle = Idle(timeout_seconds=60.0)
    idle.touch(1000.0)
    assert not idle.expired(1059.0)
    assert idle.expired(1060.0)


def test_page_marks_the_editable_cells(project: Path) -> None:
    page = _client(project).get("/")
    assert page.status_code == 200
    assert 'data-field="due"' in page.text
    assert TOKEN in page.text  # 合言葉は本文に埋める（URL には載せない）
    assert "T-9001" in page.text


def test_a_request_naming_another_host_is_refused(project: Path) -> None:
    """攻撃者のドメインが手元に解決されて叩かれる形を、名乗りの検査で止める。"""
    with TestClient(create_app(project, today=TODAY, token=TOKEN), base_url="http://attacker.example.com") as client:
        assert client.get("/").status_code == 400


def test_saving_without_the_token_is_refused(project: Path) -> None:
    """合言葉が無ければ保存できない（他の画面から送られた要求を弾く）。"""
    path = project / "work" / "T-9001-a.md"
    before = path.read_text(encoding="utf-8")
    reply = _client(project).post(
        "/edit", json={"ref": "T-9001", "field": "due", "value": "2026-08-12", "base": file_digest(path)}
    )
    assert reply.status_code == 403
    assert path.read_text(encoding="utf-8") == before


def test_saving_writes_to_the_working_copy_and_returns_the_new_digest(project: Path) -> None:
    """保存先は編集の場（作業用の写し）。正本は「取り込む」まで 1 バイトも変わらない。"""
    source = project / "work" / "T-9001-a.md"
    before = source.read_text(encoding="utf-8")
    client = _client(project)
    staged = _live(project) / "work" / "T-9001-a.md"
    reply = client.post(
        "/edit",
        json={"ref": "T-9001", "field": "due", "value": "2026-08-12", "base": file_digest(staged)},
        headers={"X-WBS-Token": TOKEN},
    )
    assert reply.status_code == 200, reply.text
    assert "due: 2026-08-12" in staged.read_text(encoding="utf-8")
    assert reply.json()["digest"] == file_digest(staged)
    assert source.read_text(encoding="utf-8") == before  # 正本は無傷


def test_saving_from_a_stale_page_is_refused_with_a_reason(project: Path) -> None:
    path = project / "work" / "T-9001-a.md"
    client = _client(project)
    stale = file_digest(path)
    client.post(
        "/edit",
        json={"ref": "T-9001", "field": "due", "value": "2026-08-12", "base": stale},
        headers={"X-WBS-Token": TOKEN},
    )
    kept = path.read_text(encoding="utf-8")
    reply = client.post(
        "/edit",
        json={"ref": "T-9001", "field": "due", "value": "2026-08-31", "base": stale},
        headers={"X-WBS-Token": TOKEN},
    )
    assert reply.status_code == 409
    assert "書き換わっている" in reply.json()["detail"]
    assert path.read_text(encoding="utf-8") == kept


def test_an_unknown_field_is_refused(project: Path) -> None:
    path = project / "work" / "T-9001-a.md"
    reply = _client(project).post(
        "/edit",
        json={"ref": "T-9001", "field": "verified_by", "value": "x", "base": file_digest(path)},
        headers={"X-WBS-Token": TOKEN},
    )
    assert reply.status_code == 409


def test_tokens_differ_between_runs() -> None:
    assert new_token() != new_token()
