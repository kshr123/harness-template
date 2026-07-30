"""営業日の暦（deliver プロファイル）のテスト。

期待値は暦の構成から導く（2026-08-01 は土曜・08-03〜08-07 は月〜金・08-11 は山の日）。
ライブラリの出力をそのまま写した固定値は書かない：祝日の扱いは「国を指定したときだけ 1 日減る」という
**差**で確かめる＝この基盤の結線を見ており、祝日表の中身を写経していない。
"""

from __future__ import annotations

from datetime import date

import pytest

from harness.deliver.calendar import WorkCalendar

pytestmark = pytest.mark.unit

MON = date(2026, 8, 3)  # 月曜
FRI = date(2026, 8, 7)  # 同じ週の金曜
SAT = date(2026, 8, 1)  # 土曜
SUN = date(2026, 8, 2)  # 日曜
MOUNTAIN_DAY = date(2026, 8, 11)  # 火曜・山の日（国民の祝日）


def test_weekend_is_not_a_workday() -> None:
    plain = WorkCalendar()
    assert not plain.is_workday(SAT)
    assert not plain.is_workday(SUN)
    assert plain.is_workday(MON)


def test_count_includes_both_ends() -> None:
    """月曜から金曜までは 5 日（両端を含む数え方）。"""
    assert WorkCalendar().count(MON, FRI) == 5


def test_single_day_counts_one() -> None:
    """開始日と終了日が同じ 1 日仕事は 1 日。"""
    assert WorkCalendar().count(MON, MON) == 1


def test_end_before_start_counts_zero() -> None:
    assert WorkCalendar().count(FRI, MON) == 0


def test_national_holiday_is_excluded_only_when_country_is_set() -> None:
    """祝日を挟む月〜水は、国を指定しなければ 3 日・指定すれば山の日が抜けて 2 日。"""
    span = (date(2026, 8, 10), date(2026, 8, 12))
    assert WorkCalendar().count(*span) == 3
    assert WorkCalendar(country="JP").count(*span) == 2


def test_extra_holiday_removes_one_day() -> None:
    """案件固有の非稼働日（会社の休業日）を 1 日足すと、その週は 5 日から 4 日になる。"""
    with_break = WorkCalendar(extra_holidays=frozenset({date(2026, 8, 5)}))
    assert with_break.count(MON, FRI) == 4


def test_extra_workday_wins_over_weekend_and_holiday() -> None:
    """振替出勤は、週末・祝日・案件の休業日のどれよりも優先する（人が明示した「働く」を勝たせる）。"""
    calendar = WorkCalendar(
        country="JP",
        extra_holidays=frozenset({date(2026, 8, 5)}),
        extra_workdays=frozenset({SAT, MOUNTAIN_DAY, date(2026, 8, 5)}),
    )
    assert calendar.is_workday(SAT)
    assert calendar.is_workday(MOUNTAIN_DAY)
    assert calendar.is_workday(date(2026, 8, 5))
