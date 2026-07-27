"""出来事（定例など）を画面から足す・直す・消すのテスト。

書き戻し先は docs/wbs.yaml の events だけ（他のキーは触らない）。有限性・ID 一意などの門は Event/Overlay の
読み込み検査＝UI でなくサーバで落とす（fail-closed）。編集の場（写し）に書き、取り込みで正本へ。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from harness.deliver.events import EventInput, next_event_id, remove_event, upsert_event
from harness.deliver.overlay import Overlay, load_overlay

pytestmark = pytest.mark.integration

TODAY = date(2026, 10, 1)


def _project(root: Path) -> None:
    (root / "work").mkdir(parents=True)
    (root / "work" / "T-1-x.md").write_text(
        "---\nid: T-1\nkind: task\nstatus: todo\nstart: 2026-08-03\ndue: 2026-08-07\n---\n", encoding="utf-8"
    )
    (root / "docs").mkdir()
    (root / "docs" / "wbs.yaml").write_text("project: X\ncalendar:\n  country: JP\n", encoding="utf-8")


def test_a_recurring_event_is_added_as_a_finite_set_of_days(tmp_path: Path) -> None:
    _project(tmp_path)
    eid = upsert_event(
        tmp_path,
        EventInput(name="定例", lane="定例", dtstart=date(2026, 8, 5), rrule="FREQ=WEEKLY;INTERVAL=2;UNTIL=20261216"),
        today=TODAY,
    )
    assert eid == "EV-001"
    event = load_overlay(tmp_path).events[0]
    assert event.name == "定例" and len(event.occurrences) == 10  # 隔週（08-05〜12-16）


def test_a_one_off_event_uses_rdate_and_the_same_type(tmp_path: Path) -> None:
    _project(tmp_path)
    upsert_event(tmp_path, EventInput(name="最終報告会の予備", lane="報告", rdate=(date(2026, 12, 18),)), today=TODAY)
    assert load_overlay(tmp_path).events[0].occurrences == (date(2026, 12, 18),)


def test_editing_keeps_the_id_and_untouched_keys(tmp_path: Path) -> None:
    _project(tmp_path)
    eid = upsert_event(tmp_path, EventInput(name="定例", lane="定例", rdate=(date(2026, 8, 5),)), today=TODAY)
    upsert_event(tmp_path, EventInput(id=eid, name="定例（改）", lane="定例", rdate=(date(2026, 8, 5),)), today=TODAY)
    overlay = load_overlay(tmp_path)
    assert len(overlay.events) == 1 and overlay.events[0].name == "定例（改）"
    assert "calendar" in (tmp_path / "docs" / "wbs.yaml").read_text(encoding="utf-8")  # 他のキーは無傷


def test_removing_an_event(tmp_path: Path) -> None:
    _project(tmp_path)
    eid = upsert_event(tmp_path, EventInput(name="定例", lane="定例", rdate=(date(2026, 8, 5),)), today=TODAY)
    remove_event(tmp_path, eid, today=TODAY)
    assert load_overlay(tmp_path).events == []


def test_an_infinite_rule_is_refused(tmp_path: Path) -> None:
    """UNTIL も COUNT も無い規則は開催日が無限＝読み込みで落とす（有限を合格条件に含める）。"""
    _project(tmp_path)
    with pytest.raises(Exception, match="UNTIL"):
        upsert_event(
            tmp_path, EventInput(name="x", lane="y", dtstart=date(2026, 8, 5), rrule="FREQ=WEEKLY"), today=TODAY
        )


def test_ids_are_unique(tmp_path: Path) -> None:
    """出来事の ID の重複は読み込み時に落ちる（手動行と対称。ID で引くので一意でないと参照が壊れる）。"""
    with pytest.raises(ValueError, match="重複"):
        Overlay.model_validate(
            {
                "events": [
                    {"id": "EV-001", "name": "a", "rdate": ["2026-08-05"]},
                    {"id": "EV-001", "name": "b", "rdate": ["2026-08-06"]},
                ]
            }
        )


def test_next_id_skips_used_numbers(tmp_path: Path) -> None:
    _project(tmp_path)
    upsert_event(tmp_path, EventInput(name="a", lane="定例", rdate=(date(2026, 8, 5),)), today=TODAY)
    assert next_event_id(load_overlay(tmp_path)) == "EV-002"
