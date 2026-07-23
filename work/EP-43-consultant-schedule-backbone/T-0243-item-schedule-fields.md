---
id: T-0243
kind: task
status: done
title: work item に日程フィールド（start/due/effort_days/milestone）を足し task-lint で整合を検査する
created: 2026-07-23
closed: 2026-07-23
depends_on: []
verified_by:
  - tests/test_pm.py::test_schedule_start_after_due_is_error
  - tests/test_pm.py::test_schedule_valid_dates_are_ok
  - tests/test_pm.py::test_milestone_without_due_is_error
  - tests/test_pm.py::test_negative_effort_days_is_error
---
# T-0243 日程フィールドと整合検査

## なぜ
コンサルが顧客に見せる WBS/ガントには、各作業の予定開始・終了・見積り・マイルストーンが要る。`work/` の木は
既に WBS だが、日程情報を持つ受け皿が無かった。`work/` を単一正本に保ったまま日程を載せ、ガント/Excel は
そこから生成物にする（STATUS.md と同じ思想）。

## 何を
- `models.py` の `Item` に任意フィールド：`start: date|None`・`due: date|None`・`effort_days: float|None`・
  `milestone: bool=False`。語は標準（PMBOK/MS Project/GitHub）。%完了・実績日付は持たない（木と created/closed から導出）。
- `pm.lint`（task-lint）に整合検査：`start > due`＝error、`milestone` なのに `due` 無し＝error。日付は任意なので
  置いたときだけ矛盾を咎める（無指定は正常）。
- `AGENTS.md` に任意欄として明記。

## 検証
`uv run verify` 緑。`test_schedule_start_after_due_is_error`＝開始>終了は error、`test_schedule_valid_dates_are_ok`＝
正しい日付＋見積りは通る、`test_milestone_without_due_is_error`＝節目に期日無しは error。maker≠checker（別 fable）で差分確認。
