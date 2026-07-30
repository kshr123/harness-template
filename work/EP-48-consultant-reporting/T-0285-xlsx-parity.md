---
id: T-0285
kind: task
status: done
created: 2026-07-30
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [T-0281]
verified_by:
  - tests/test_deliver_formats.py::test_the_spreadsheet_marks_the_today_week_and_holiday_weeks_and_has_a_legend
  - tests/test_deliver_formats.py::test_the_spreadsheet_matches_the_tree
  - tests/test_deliver_formats.py::test_the_spreadsheet_does_not_write_live_formulas_from_user_text
---
# T-0285 xlsx の体裁パリティ（本日週・休業週・凡例）
設計は EP-48 の DESIGN.md（T-0285 節）。週の見出しに、本日を含む週＝赤字（--today と同色）、休業（祝日/会社休＝
土日以外の非稼働日）を含む週＝淡い灰（--off と同意味）を付け、凡例行（期間/完了/遅れ/◆節目/休業週/本日）を出す。
色は既存の意味色のみ（新色なし）。週粒度は据え置き。数式無害化（_put）は維持。木との一致テストも緑のまま。

## 受け入れ基準
- [x] 本日を含む週の見出しが赤字。
- [x] 休業を含む週が淡い灰（休業の無い週は塗らない）。土日はどの週にもあるので信号にしない。
- [x] 凡例行が出る（意味の対応）。
- [x] 既存の「木と一致」テストが緑・数式無害化が維持。
