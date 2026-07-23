"""作業単位の木から WBS を導出する部分のテスト。

期待値はすべて、下の `_scaffold` が一時ディレクトリに組み立てる木の構成から導ける（実装の出力を写した
固定値は書かない）。組み立てる木（暦は 2026-08-01 が土曜・08-03〜08-07 が月〜金）:

    alpha（エピック・子 2 件）
      1 件目  done   予定 08-03〜08-07（月〜金＝営業日 5）実績 08-03〜08-06
      2 件目  todo   予定 08-10〜08-12（月〜水＝営業日 3）1 件目に依存
    beta（エピック・子なし＝末端）予定 08-17〜08-21（月〜金＝営業日 5）
    gamma（エピック・子なし・日程なし）＝未日程
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest

from harness.deliver import wbs as wbs_mod
from harness.deliver.overlay import Overlay
from harness.models import Status

pytestmark = pytest.mark.unit

TODAY = date(2026, 8, 20)  # 木曜。T-9002 の予定終了（08-12）より後・EP-91 の予定終了（08-21）より前。


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _scaffold(root: Path) -> None:
    alpha = root / "work" / "EP-90-alpha"
    _write(alpha / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        alpha / "T-9001-a.md",
        {
            "id": "T-9001",
            "kind": "task",
            "status": "done",
            "title": "設計",
            "owner": "sakurada",
            "start": "2026-08-03",
            "due": "2026-08-07",
            "effort_days": 4.0,
            "created": "2026-08-03",
            "closed": "2026-08-06",
        },
    )
    _write(
        alpha / "T-9002-b.md",
        {
            "id": "T-9002",
            "kind": "task",
            "status": "todo",
            "title": "実装",
            "start": "2026-08-10",
            "due": "2026-08-12",
            "effort_days": 2.0,
            "depends_on": ["T-9001"],
        },
    )
    _write(
        root / "work" / "EP-91-beta" / "item.md",
        {"id": "EP-91", "kind": "epic", "status": "todo", "start": "2026-08-17", "due": "2026-08-21"},
    )
    _write(root / "work" / "EP-92-gamma" / "item.md", {"id": "EP-92", "kind": "epic", "status": "todo"})


def _build(root: Path, overlay: Overlay | None = None) -> wbs_mod.Wbs:
    return wbs_mod.build(root, today=TODAY, overlay=overlay if overlay is not None else Overlay())


def _by_ref(built: wbs_mod.Wbs) -> dict[str, wbs_mod.WbsRow]:
    return {row.ref: row for row in built.walk() if row.ref is not None}


def test_codes_follow_position_in_the_tree(tmp_path: Path) -> None:
    """WBS 番号は木の位置から導く（保存されていない）。work/ 直下は名前順。"""
    _scaffold(tmp_path)
    rows = _by_ref(_build(tmp_path))
    assert rows["EP-90"].code == "1"
    assert rows["T-9001"].code == "1.1"
    assert rows["T-9002"].code == "1.2"
    assert rows["EP-91"].code == "2"
    assert rows["EP-92"].code == "3"


def test_parent_dates_roll_up_from_children(tmp_path: Path) -> None:
    """親の日程は子の最小の開始・最大の終了（親自身は日程を持っていない）。"""
    _scaffold(tmp_path)
    parent = _by_ref(_build(tmp_path))["EP-90"]
    assert parent.start == date(2026, 8, 3)  # T-9001 の開始
    assert parent.due == date(2026, 8, 12)  # T-9002 の終了


def test_parent_dates_come_from_children_even_if_the_parent_declares_its_own(tmp_path: Path) -> None:
    """親が自分で日程を宣言していても、子がいる限り子から導く（宣言した値は採用しない）。"""
    _scaffold(tmp_path)
    _write(
        tmp_path / "work" / "EP-90-alpha" / "item.md",
        {
            "id": "EP-90",
            "kind": "epic",
            "status": "in-progress",
            "plan": "detailed",
            "start": "2026-01-01",
            "due": "2026-12-31",
        },
    )
    parent = _by_ref(_build(tmp_path))["EP-90"]
    assert parent.start == date(2026, 8, 3)
    assert parent.due == date(2026, 8, 12)


def test_parent_status_rolls_up(tmp_path: Path) -> None:
    """done が 1 件・todo が 1 件なら親は進行中（全部 done のときだけ done）。"""
    _scaffold(tmp_path)
    rows = _by_ref(_build(tmp_path))
    assert rows["EP-90"].status is Status.in_progress
    assert rows["EP-91"].status is Status.todo


def test_progress_is_done_leaves_over_total_leaves(tmp_path: Path) -> None:
    """進捗は末端の done 数 ÷ 末端の総数（子 2 件のうち 1 件 done なので 1/2）。"""
    _scaffold(tmp_path)
    parent = _by_ref(_build(tmp_path))["EP-90"]
    assert (parent.done_leaves, parent.total_leaves) == (1, 2)
    assert parent.progress == pytest.approx(0.5)


def test_workdays_count_both_ends_and_skip_weekends(tmp_path: Path) -> None:
    """月〜金は 5 日、月〜水は 3 日（両端を含む・土日は数えない）。"""
    _scaffold(tmp_path)
    rows = _by_ref(_build(tmp_path))
    assert rows["T-9001"].workdays == 5
    assert rows["T-9002"].workdays == 3
    assert rows["EP-91"].workdays == 5


def test_actuals_come_from_created_and_closed(tmp_path: Path) -> None:
    """実績は created / closed から導く（done でない単位に終了実績は付かない）。"""
    _scaffold(tmp_path)
    rows = _by_ref(_build(tmp_path))
    assert rows["T-9001"].actual_start == date(2026, 8, 3)
    assert rows["T-9001"].actual_finish == date(2026, 8, 6)
    assert rows["T-9002"].actual_finish is None


def test_late_marks_only_overdue_and_unfinished(tmp_path: Path) -> None:
    """遅れの印は「予定終了が基準日より前」かつ「まだ done でない」ときだけ付く。"""
    _scaffold(tmp_path)
    rows = _by_ref(_build(tmp_path))
    assert rows["T-9002"].late  # 予定終了 08-12 < 基準日 08-20・todo
    assert not rows["T-9001"].late  # 予定終了は過ぎているが done
    assert not rows["EP-91"].late  # 予定終了 08-21 は基準日より後


def test_effort_days_sum_up_to_the_parent(tmp_path: Path) -> None:
    """親の見積り工数は子の合計（4 人日＋2 人日）。"""
    _scaffold(tmp_path)
    assert _by_ref(_build(tmp_path))["EP-90"].effort_days == pytest.approx(6.0)


def test_owner_becomes_the_assignee(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    assert _by_ref(_build(tmp_path))["T-9001"].assignees == ["sakurada"]


def test_unscheduled_units_are_listed_not_dropped(tmp_path: Path) -> None:
    """日程を持たない単位も行としては出る（黙って消えない）。"""
    _scaffold(tmp_path)
    built = _build(tmp_path)
    assert "EP-92" in {row.ref for row in built.walk()}
    assert [row.ref for row in built.unscheduled] == ["EP-92"]


def test_span_covers_every_dated_row(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    assert _build(tmp_path).span == (date(2026, 8, 3), date(2026, 8, 21))


def test_span_is_none_when_nothing_is_scheduled(tmp_path: Path) -> None:
    _write(tmp_path / "work" / "EP-93-delta" / "item.md", {"id": "EP-93", "kind": "epic", "status": "todo"})
    assert _build(tmp_path).span is None


def test_sections_reorder_and_add_manual_rows(tmp_path: Path) -> None:
    """節を書くと第 1 階層が節になり、work/ に置けない行（承認待ち）を同じ並びに混ぜられる。"""
    _scaffold(tmp_path)
    overlay = Overlay.model_validate(
        {
            "sections": [
                {
                    "name": "設計フェーズ",
                    "team": "コンサル",
                    "entries": [{"work": "EP-90"}, {"row": "W-001"}],
                }
            ],
            "rows": [
                {
                    "id": "W-001",
                    "name": "設計書の承認",
                    "team": "クライアント",
                    "status": "todo",
                    "start": "2026-08-13",
                    "due": "2026-08-14",
                }
            ],
            "exclude": ["EP-91", "EP-92"],
        }
    )
    built = _build(tmp_path, overlay)
    assert [row.code for row in built.rows] == ["1"]
    assert built.rows[0].name == "設計フェーズ"
    rows = _by_ref(built)
    assert rows["EP-90"].code == "1.1"
    assert rows["W-001"].code == "1.2"
    assert rows["W-001"].status is Status.todo
    assert rows["W-001"].team == "クライアント"
    # 節の日程・進捗は中身から導く（EP-90 の 08-03〜08-12 と手動行の 08-13〜08-14 を覆う）。
    assert built.rows[0].start == date(2026, 8, 3)
    assert built.rows[0].due == date(2026, 8, 14)
    assert (built.rows[0].done_leaves, built.rows[0].total_leaves) == (1, 3)


def test_missing_reference_is_reported_not_silently_dropped(tmp_path: Path) -> None:
    """節が実在しない単位を指したら、行を落とすのでなく指摘を積む（fail-closed）。"""
    _scaffold(tmp_path)
    overlay = Overlay.model_validate({"sections": [{"name": "架空", "entries": [{"work": "EP-99"}]}]})
    built = _build(tmp_path, overlay)
    assert [p.level for p in built.problems] == ["error"]
    assert "EP-99" in built.problems[0].message
