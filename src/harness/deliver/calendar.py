"""営業日の計算（土日・祝日・案件固有の非稼働日）。

WBS の「日数」は暦日でなく営業日で数える（クライアントに出す工程表の慣習）。祝日は業界標準の
`holidays`（vacanza）に委ね、自前の祝日表を持たない。法改正・臨時の祝日・会社休業日・振替出勤で
ライブラリの答えが実務とずれる場合に備え、案件側で足す／打ち消す口（`extra_holidays`／`extra_workdays`）
を持つ＝祝日データの正誤に検証が人質に取られない。

期間の端点は**両端を含む**（MS Project 等の工程表の慣習。1 日で終わるタスクは開始日＝終了日で 1 日）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

# 週末（月曜=0 … 日曜=6）。国別の週末（中東の金土等）は現状の案件に対象が無いので持たない。
_WEEKEND = (5, 6)


@lru_cache(maxsize=8)
def _country_holidays(country: str) -> Any:  # noqa: ANN401  holidays の国別オブジェクト（年は参照時に自動で増える）
    """国コードから holidays の祝日オブジェクトを引く（国ごとに 1 つを使い回す）。

    holidays（extra deliver）が無い環境では、導入方法を添えて ImportError を投げ直す
    （生の ImportError の栈でなく何をすればよいかを出す）。
    """
    try:
        import holidays
    except ImportError as exc:  # pragma: no cover - extra 未導入の環境でだけ通る
        raise ImportError(
            f"祝日ライブラリ holidays が無い（deliver extra 未導入）。`uv sync --extra deliver` で導入する: {exc}"
        ) from exc
    return holidays.country_holidays(country)


@dataclass(frozen=True)
class WorkCalendar:
    """営業日の判定に使う暦。`docs/wbs.yaml` の `calendar:` から作る。

    country … holidays の国コード（例 "JP"）。None なら祝日を見ず土日だけを非稼働日にする。
    extra_holidays … 会社休業日・クライアント休業日など、案件で足す非稼働日。
    extra_workdays … 振替出勤など、非稼働日の判定を打ち消して稼働日に戻す日。**こちらが優先**する
    （足す側と打ち消す側が同じ日を指したとき、人が明示した「働く」を勝たせる）。
    """

    country: str | None = None
    extra_holidays: frozenset[date] = field(default_factory=frozenset)
    extra_workdays: frozenset[date] = field(default_factory=frozenset)

    def is_workday(self, day: date) -> bool:
        """その日が稼働日か。振替出勤（extra_workdays）は週末・祝日・案件休業日より優先する。"""
        if day in self.extra_workdays:
            return True
        if day.weekday() in _WEEKEND:
            return False
        if day in self.extra_holidays:
            return False
        return not (self.country is not None and day in _country_holidays(self.country))

    def count(self, start: date, end: date) -> int:
        """start から end までの営業日数（**両端を含む**）。end が start より前なら 0。"""
        if end < start:
            return 0
        day = start
        total = 0
        while day <= end:
            if self.is_workday(day):
                total += 1
            day += timedelta(days=1)
        return total
