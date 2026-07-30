---
id: T-0261
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 1
requirements: []
depends_on: [T-0260]
verified_by:
  - tests/test_deliver_geometry.py::test_both_the_week_and_month_grids_are_available
  - tests/test_deliver_geometry.py::test_the_view_offers_the_gantt_units
---
# T-0261 ガントを日・週・月の単位で見られるようにする

## 作ったもの
- 見出しに「自動／月／週／日」。**1 日あたりの幅を変えるだけ**なので、棒も格子も同じ表の中で伸び縮みし、
  行と棒がずれない（表ごと横にスクロールする＝行ごとの図形という作りを崩さない）。
- 週と月の**両方の目盛**を書き出しておき、見せる組を単位で切り替える（切り替えのたびにサーバへ行かない）。
- 自動は期間の長さで粒度を選ぶ（短い案件は週・長い案件は月）＝これまでの見え方。

## 受け入れ基準
- [x] 週と月の両方の目盛が書き出されているか。
- [x] 単位を選ぶ操作が画面にあるか。
