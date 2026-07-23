"""案件固有の上書き（`docs/wbs.yaml`）のスキーマのテスト。

このプロファイルの中心の主張は「導出できる値を保存できない」こと。**書けないことを確かめる**テストを
中心に置く（書ける欄が増えたら失敗する＝二重台帳の再発を検出する）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness.deliver.overlay import ManualRow, Overlay, SectionEntry, load_overlay

pytestmark = pytest.mark.unit


def test_derived_values_have_no_place_to_be_written() -> None:
    """WBS 番号・日数・進捗・親の日程を書く欄が無い（未知キーとして拒否される）。"""
    for key, value in (
        ("code", "1.1"),
        ("wbs_no", "1.1"),
        ("workdays", 5),
        ("progress", 0.5),
        ("percent_complete", 50),
    ):
        with pytest.raises(ValidationError):
            ManualRow.model_validate({"id": "W-001", "name": "承認", "status": "todo", key: value})


def test_section_entry_cannot_carry_status_or_dates() -> None:
    """作業単位を指す項目に、状態・日程を書く欄が無い（あれば木と 2 か所に書けてしまう）。"""
    for key, value in (("status", "done"), ("start", "2026-08-03"), ("due", "2026-08-07")):
        with pytest.raises(ValidationError):
            SectionEntry.model_validate({"work": "EP-90", key: value})


def test_section_entry_points_at_exactly_one_thing() -> None:
    with pytest.raises(ValidationError):
        SectionEntry.model_validate({"work": "EP-90", "row": "W-001"})
    with pytest.raises(ValidationError):
        SectionEntry.model_validate({})
    assert SectionEntry.model_validate({"work": "EP-90"}).row is None


def test_manual_row_requires_status() -> None:
    """手動行は導出元が無いので状態が必須（書き忘れが既定で合格にならない）。"""
    with pytest.raises(ValidationError):
        ManualRow.model_validate({"id": "W-001", "name": "承認"})


def test_manual_row_id_must_be_distinguishable_from_work_units() -> None:
    with pytest.raises(ValidationError):
        ManualRow.model_validate({"id": "T-0001", "name": "承認", "status": "todo"})


def test_milestone_needs_a_date_and_has_no_span() -> None:
    with pytest.raises(ValidationError):
        ManualRow.model_validate({"id": "W-001", "name": "節目", "status": "todo", "milestone": True})
    with pytest.raises(ValidationError):
        ManualRow.model_validate(
            {
                "id": "W-001",
                "name": "節目",
                "status": "todo",
                "milestone": True,
                "due": "2026-08-21",
                "start": "2026-08-20",
            }
        )


def test_manual_row_date_contradictions_fail_on_load() -> None:
    with pytest.raises(ValidationError):
        ManualRow.model_validate(
            {"id": "W-001", "name": "承認", "status": "todo", "start": "2026-08-21", "due": "2026-08-20"}
        )
    with pytest.raises(ValidationError):
        ManualRow.model_validate({"id": "W-001", "name": "承認", "status": "todo", "actual_finish": "2026-08-20"})


def test_duplicate_manual_row_ids_fail_on_load() -> None:
    with pytest.raises(ValidationError):
        Overlay.model_validate(
            {
                "rows": [
                    {"id": "W-001", "name": "承認", "status": "todo"},
                    {"id": "W-001", "name": "別の承認", "status": "todo"},
                ]
            }
        )


def test_missing_overlay_file_gives_empty_overlay(tmp_path: Path) -> None:
    """上書きが無い案件でも読める（節構成は木からそのまま導くので、見えなくなる単位は出ない）。"""
    over = load_overlay(tmp_path)
    assert over.sections == []
    assert over.rows == []
    assert over.calendar.country is None


def test_overlay_file_is_read(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "wbs.yaml").write_text(
        "project: 需要予測\n"
        "calendar:\n"
        "  country: JP\n"
        "  extra_holidays: [2026-08-13]\n"
        "sections:\n"
        "  - name: 要件定義\n"
        "    entries:\n"
        "      - work: EP-90\n",
        encoding="utf-8",
    )
    over = load_overlay(tmp_path)
    assert over.project == "需要予測"
    assert over.calendar.to_calendar().extra_holidays == frozenset({date(2026, 8, 13)})
    assert [s.name for s in over.sections] == ["要件定義"]
    assert over.sections[0].entries[0].work == "EP-90"
