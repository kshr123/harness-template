"""チーム・担当者の名簿（`docs/wbs.yaml` の teams / members）のテスト。

毎回打つと表記ゆれが起きる（同じ人が別人として並ぶ）ので、画面では名簿から選ぶ。新しい名前を入れたら
名簿にも足す＝**選ぶ先と実際に使われている名前がずれない**、が守りたい性質。
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from fastapi.testclient import TestClient

from harness.deliver import render
from harness.deliver import wbs as wbs_mod
from harness.deliver.editor import add_to_roster, apply_edit, file_digest
from harness.deliver.overlay import load_overlay
from harness.deliver.server import create_app

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)
TOKEN = "test-token"


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _project(tmp_path: Path, overlay: str | None = None) -> Path:
    _write(
        tmp_path / "work" / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    if overlay is not None:
        (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "docs" / "wbs.yaml").write_text(overlay, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("initial", "expected"),
    [
        (None, ["データ基盤"]),  # 上書きファイルが無い
        ("teams: []\n", ["データ基盤"]),  # 空の並び
        ("teams: [コンサル]\n", ["コンサル", "データ基盤"]),  # 1 行の並び
        ("teams:\n  - コンサル\n", ["コンサル", "データ基盤"]),  # 箇条書き
        ("project: 見本\n", ["データ基盤"]),  # そのキーがまだ無い
    ],
)
def test_a_name_is_added_whatever_the_yaml_looks_like(tmp_path: Path, initial: str | None, expected: list[str]) -> None:
    """名簿の書き方（1 行の並び・箇条書き・未記入）に関わらず足せる。人の書き方に合わせる。"""
    root = _project(tmp_path, initial)
    add_to_roster(root, "teams", "データ基盤")
    assert load_overlay(root).teams == expected


def test_adding_the_same_name_twice_changes_nothing(tmp_path: Path) -> None:
    root = _project(tmp_path, "teams: [コンサル]\n")
    add_to_roster(root, "teams", "コンサル")
    assert (root / "docs" / "wbs.yaml").read_text(encoding="utf-8") == "teams: [コンサル]\n"


def test_the_comments_around_the_roster_survive(tmp_path: Path) -> None:
    """名簿を足しても、上書きファイルのコメント・他の設定は動かない。"""
    root = _project(tmp_path, "# 案件の設定\nproject: 見本\nteams: [コンサル]\n")
    add_to_roster(root, "teams", "データ基盤")
    after = (root / "docs" / "wbs.yaml").read_text(encoding="utf-8")
    assert "# 案件の設定" in after
    assert "project: 見本" in after


def test_saving_a_new_name_puts_it_in_the_roster(tmp_path: Path) -> None:
    """画面から新しい担当を入れると、その名前が名簿にも入る（次から選べる）。"""
    root = _project(tmp_path, "members: [桜田]\n")
    path = root / "work" / "T-9001-a.md"
    apply_edit(root, ref="T-9001", field="owner", value="山田", base_digest=file_digest(path), today=TODAY)
    assert load_overlay(root).members == ["桜田", "山田"]
    assert "owner: 山田" in path.read_text(encoding="utf-8")


def test_saving_a_team_puts_it_in_the_team_roster(tmp_path: Path) -> None:
    root = _project(tmp_path, "teams: [コンサル]\n")
    path = root / "work" / "T-9001-a.md"
    apply_edit(root, ref="T-9001", field="team", value="データ基盤", base_digest=file_digest(path), today=TODAY)
    assert load_overlay(root).teams == ["コンサル", "データ基盤"]
    built = wbs_mod.build(root, today=TODAY)
    assert next(row for row in built.walk() if row.ref == "T-9001").team == "データ基盤"


def test_clearing_a_field_does_not_touch_the_roster(tmp_path: Path) -> None:
    """空にする操作で名簿が増えない（空文字が名簿に並ぶのを防ぐ）。"""
    root = _project(tmp_path, "members: [桜田]\n")
    path = root / "work" / "T-9001-a.md"
    apply_edit(root, ref="T-9001", field="owner", value="桜田", base_digest=file_digest(path), today=TODAY)
    apply_edit(root, ref="T-9001", field="owner", value="", base_digest=file_digest(path), today=TODAY)
    assert load_overlay(root).members == ["桜田"]


def test_the_edit_page_offers_the_roster_as_choices(tmp_path: Path) -> None:
    """画面のチーム・担当の欄が、名簿を選択肢として持っている。"""
    root = _project(tmp_path, "teams: [コンサル, データ基盤]\nmembers: [桜田, 山田]\n")
    page = TestClient(create_app(root, today=TODAY, token=TOKEN), base_url="http://127.0.0.1").get("/")
    # 属性に入れるので HTML の実体参照に置き換わる（生の JSON では一致しない）。
    assert html.escape(json.dumps(["コンサル", "データ基盤"], ensure_ascii=False)) in page.text
    assert html.escape(json.dumps(["桜田", "山田"], ensure_ascii=False)) in page.text


def test_the_exported_file_has_no_choices(tmp_path: Path) -> None:
    """渡す生成物には選択肢を入れない（編集の口が無いので不要）。"""
    root = _project(tmp_path, "teams: [コンサル]\n")
    html = render.render_html(wbs_mod.build(root, today=TODAY))
    assert "data-choices" not in html


def test_a_manual_row_assignee_is_written_as_a_list(tmp_path: Path) -> None:
    """手動行の担当は一覧の欄なので、画面から選んだ 1 人を並びとして書く（型を崩さない）。"""
    root = _project(
        tmp_path,
        "members: [桜田]\nrows:\n  - id: W-001\n    name: 承認\n    status: todo\n",
    )
    path = root / "docs" / "wbs.yaml"
    apply_edit(root, ref="W-001", field="assignees", value="山田", base_digest=file_digest(path), today=TODAY)
    overlay = load_overlay(root)
    assert overlay.rows_by_id["W-001"].assignees == ["山田"]
    assert overlay.members == ["桜田", "山田"]
