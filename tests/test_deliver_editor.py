"""編集した内容を正本へ書き戻す部分のテスト。

いちばん確かめたいのは「書き戻しても差分が小さいまま」＝コメント・並び・他のキーが動かないこと
（動くと、差分だけを見る独立レビューが成り立たなくなる）。次に、競合・不正値・検査失敗のいずれでも
正本が壊れた状態で残らないこと。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from harness.deliver import wbs_lint
from harness.deliver.editor import EditRejected, apply_edit, file_digest

pytestmark = pytest.mark.unit

TODAY = date(2026, 8, 20)

# コメント・空行・並びをわざと混ぜた作業単位（書き戻しでこれらが動かないことを確かめる）。
_ITEM = """\
---
id: T-9001
kind: task
# この行はコメント（書き戻しで消えてはいけない）
status: todo
title: 設計
start: 2026-08-03
due: 2026-08-07

depends_on: []
verified_by: []
---
# T-9001 設計

本文。
"""

_OVERLAY = """\
# 顧客向けの上書き（コメントは書き戻しで残ること）
project: 見本
calendar:
  country: JP
rows:
  - id: W-001
    name: 承認
    team: クライアント
    status: todo
    start: 2026-08-10
    due: 2026-08-11
"""


def _project(tmp_path: Path) -> Path:
    """作業単位 1 件（軽い単位＝ファイル 1 つ）と、手動行を持つ上書きを置く。"""
    (tmp_path / "work").mkdir(parents=True)
    (tmp_path / "work" / "T-9001-a.md").write_text(_ITEM, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "wbs.yaml").write_text(_OVERLAY, encoding="utf-8")
    return tmp_path


def _item_path(root: Path) -> Path:
    return root / "work" / "T-9001-a.md"


def _changed_lines(before: str, after: str) -> list[tuple[str, str]]:
    """行数が同じときに、変わった行だけを (前, 後) で返す。"""
    b, a = before.splitlines(), after.splitlines()
    assert len(b) == len(a), "行数が変わった（挿入・削除が起きている）"
    return [(x, y) for x, y in zip(b, a, strict=True) if x != y]


def test_editing_a_date_changes_exactly_one_line(tmp_path: Path) -> None:
    """日付を直すと、その 1 行だけが変わる（コメントも他のキーも本文も動かない）。"""
    root = _project(tmp_path)
    path = _item_path(root)
    before = path.read_text(encoding="utf-8")
    apply_edit(root, ref="T-9001", field="due", value="2026-08-12", base_digest=file_digest(path), today=TODAY)
    after = path.read_text(encoding="utf-8")
    assert _changed_lines(before, after) == [("due: 2026-08-07", "due: 2026-08-12")]
    assert "# この行はコメント（書き戻しで消えてはいけない）" in after
    assert after.endswith("本文。\n")


def test_editing_a_manual_row_changes_exactly_one_line(tmp_path: Path) -> None:
    """手動行も同じ（上書きファイルのコメント・節構成は動かない）。"""
    root = _project(tmp_path)
    path = root / "docs" / "wbs.yaml"
    before = path.read_text(encoding="utf-8")
    apply_edit(root, ref="W-001", field="status", value="done", base_digest=file_digest(path), today=TODAY)
    after = path.read_text(encoding="utf-8")
    assert _changed_lines(before, after) == [("    status: todo", "    status: done")]
    assert "# 顧客向けの上書き（コメントは書き戻しで残ること）" in after


def test_a_missing_key_is_added_and_an_emptied_one_is_removed(tmp_path: Path) -> None:
    """まだ書いていない欄は足され、空にした欄は行ごと消える（空文字を値として書き込まない）。"""
    root = _project(tmp_path)
    path = _item_path(root)
    apply_edit(root, ref="T-9001", field="owner", value="桜田", base_digest=file_digest(path), today=TODAY)
    assert "owner: 桜田" in path.read_text(encoding="utf-8")  # 要らない引用符を足さない（差分を読みやすく保つ）
    apply_edit(root, ref="T-9001", field="owner", value="", base_digest=file_digest(path), today=TODAY)
    assert "owner:" not in path.read_text(encoding="utf-8")


def test_a_stale_reader_cannot_overwrite(tmp_path: Path) -> None:
    """画面を開いた後に正本が別の手で動いていたら、書かずに拒否する（黙って巻き戻さない）。"""
    root = _project(tmp_path)
    path = _item_path(root)
    stale = file_digest(path)
    apply_edit(root, ref="T-9001", field="due", value="2026-08-12", base_digest=stale, today=TODAY)
    kept = path.read_text(encoding="utf-8")
    with pytest.raises(EditRejected):
        apply_edit(root, ref="T-9001", field="due", value="2026-08-31", base_digest=stale, today=TODAY)
    assert path.read_text(encoding="utf-8") == kept


def test_the_returned_digest_lets_the_next_save_through(tmp_path: Path) -> None:
    """保存が返す新しい指紋を使えば、続けて 2 回目も保存できる（誤って拒否されない）。"""
    root = _project(tmp_path)
    path = _item_path(root)
    first = apply_edit(root, ref="T-9001", field="due", value="2026-08-12", base_digest=file_digest(path), today=TODAY)
    apply_edit(root, ref="T-9001", field="due", value="2026-08-13", base_digest=first, today=TODAY)
    assert "due: 2026-08-13" in path.read_text(encoding="utf-8")


def test_bad_values_are_refused_and_nothing_is_written(tmp_path: Path) -> None:
    root = _project(tmp_path)
    path = _item_path(root)
    before = path.read_text(encoding="utf-8")
    for field, value in (("due", "8/12"), ("status", "とりあえず"), ("effort_days", "0"), ("effort_days", "多め")):
        with pytest.raises(EditRejected):
            apply_edit(root, ref="T-9001", field=field, value=value, base_digest=file_digest(path), today=TODAY)
    assert path.read_text(encoding="utf-8") == before


def test_fields_outside_the_allowed_set_are_refused(tmp_path: Path) -> None:
    """画面から直せる欄は決め打ちの一覧だけ（完了↔検証の結びつけなどを画面から書き換えられない）。"""
    root = _project(tmp_path)
    path = _item_path(root)
    with pytest.raises(EditRejected):
        apply_edit(root, ref="T-9001", field="verified_by", value="x", base_digest=file_digest(path), today=TODAY)
    with pytest.raises(EditRejected):
        apply_edit(root, ref="T-9001", field="id", value="T-9999", base_digest=file_digest(path), today=TODAY)


def test_an_edit_that_breaks_the_invariants_is_rolled_back(tmp_path: Path) -> None:
    """書いた後の検査に失敗したら元へ戻す（矛盾した状態を正本に残さない）。

    先行タスクの終了予定より後続の開始予定を前に動かす操作を、画面からできないようにする。
    """
    root = _project(tmp_path)
    second = root / "work" / "T-9002-b.md"
    second.write_text(
        "---\nid: T-9002\nkind: task\nstatus: todo\nstart: 2026-08-10\ndue: 2026-08-12\ndepends_on: [T-9001]\n---\n",
        encoding="utf-8",
    )
    before = second.read_text(encoding="utf-8")
    with pytest.raises(EditRejected):
        apply_edit(root, ref="T-9002", field="start", value="2026-08-04", base_digest=file_digest(second), today=TODAY)
    assert second.read_text(encoding="utf-8") == before


def test_an_unknown_row_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with pytest.raises(EditRejected):
        apply_edit(root, ref="T-9999", field="due", value="2026-08-12", base_digest="", today=TODAY)
    with pytest.raises(EditRejected):
        apply_edit(root, ref="W-404", field="due", value="2026-08-12", base_digest="", today=TODAY)


def test_a_comment_inside_a_manual_row_does_not_break_the_write_back(tmp_path: Path) -> None:
    """列 0 のコメントが手動行の途中にあっても、狙った行が置き換わる。

    塊の切り出しがコメントで打ち切られると、その先のキーを見落として同じキーを書き足す＝「保存した」と
    出るのに値が変わらない、が起きる（読み戻しの突き合わせでも捕まえるが、そもそも起こさない）。
    """
    root = _project(tmp_path)
    path = root / "docs" / "wbs.yaml"
    text = path.read_text(encoding="utf-8").replace(
        "    status: todo\n", "    status: todo\n# 途中にコメントを入れてみる\n"
    )
    path.write_text(text, encoding="utf-8")
    apply_edit(root, ref="W-001", field="due", value="2026-08-19", base_digest=file_digest(path), today=TODAY)
    after = path.read_text(encoding="utf-8")
    assert after.count("due:") == 1  # 同じキーを書き足していない
    assert "due: 2026-08-19" in after
    assert "# 途中にコメントを入れてみる" in after


def test_a_write_back_that_does_not_take_effect_is_refused(tmp_path: Path) -> None:
    """書き戻しが効かなかった場合は「保存できた」と言わない（黙って捨てない）。"""
    root = _project(tmp_path)
    path = _item_path(root)
    # 同じキーが 2 つある壊れた状態を作る（後ろが勝つので、前を書き換えても値は変わらない）。
    text = path.read_text(encoding="utf-8").replace("due: 2026-08-07\n", "due: 2026-08-07\ndue: 2026-09-30\n")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(EditRejected) as caught:
        apply_edit(root, ref="T-9001", field="due", value="2026-08-12", base_digest=file_digest(path), today=TODAY)
    assert "効いていない" in str(caught.value)


def test_an_unrelated_pre_existing_problem_does_not_block_saving(tmp_path: Path) -> None:
    """この編集と関係のない指摘が既に出ていても、保存はできる。

    全体の検査で断ると、画面から直せない指摘が 1 つあるだけで他の行も一切保存できなくなる
    （「編集面を開いたのに何も保存できない」状態）。**増えた指摘だけ**を拒否の理由にする。
    """
    root = _project(tmp_path)
    # 子を持つのに日程を宣言している親＝画面からは直せない指摘を、先に作っておく。
    epic = root / "work" / "EP-90-alpha"
    epic.mkdir(parents=True)
    (epic / "item.md").write_text(
        "---\nid: EP-90\nkind: epic\nstatus: in-progress\nplan: detailed\nstart: 2026-08-01\ndue: 2026-08-31\n---\n",
        encoding="utf-8",
    )
    (epic / "T-9010-c.md").write_text(
        "---\nid: T-9010\nkind: task\nstatus: todo\nstart: 2026-08-03\ndue: 2026-08-07\n---\n",
        encoding="utf-8",
    )
    assert any(p.level == "error" for p in wbs_lint.check(root, today=TODAY))  # 既に赤い
    path = _item_path(root)
    apply_edit(root, ref="T-9001", field="due", value="2026-08-12", base_digest=file_digest(path), today=TODAY)
    assert "due: 2026-08-12" in path.read_text(encoding="utf-8")
