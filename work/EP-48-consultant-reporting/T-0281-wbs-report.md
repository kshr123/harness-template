---
id: T-0281
kind: task
status: done
created: 2026-07-30
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-47]
verified_by:
  - tests/test_deliver_report.py::test_milestones_are_split_into_achieved_late_and_planned
  - tests/test_deliver_report.py::test_the_change_section_shows_the_commit_that_moved_a_date
  - tests/test_deliver_report.py::test_report_refuses_like_export
  - tests/test_deliver_report.py::test_zero_count_sections_say_so
  - tests/test_deliver_report.py::test_user_text_is_escaped_in_the_report
---
# T-0281 `wbs report`：定例/最終報告の 1 枚生成
設計は EP-48 の DESIGN.md（T-0281 節）。build＋baseline＋walk の合成で、前回からの変化・マイルストーンの状況・
遅れ・今後 N 日を 1 枚の自己完結 HTML に。拒否連鎖（lint/0件/未コミット）は `cli._prepare` に切り出し export と
共有（第 2 実装を作らない）。色トークンは `render._TOKENS` を参照（色の第 2 台帳なし）。マイルストーンの達成は
実績日で示し、期日超過は「遅れて達成」と予定/実績の両日付を出す（粉飾しない）。0 件の節は明記。

## 受け入れ基準
- [x] 達成／遅れ／予定の 3 区分に分かれ、closed>due が「遅れて達成」＋両日付で出る。
- [x] `--against` で前回からの日程変化がコミット件名つきで出る（テストデータ由来の日付で確認）。
- [x] 拒否は export と同じ関門（lint/0件/未コミット）を通る（`_prepare` 共有）。
- [x] 遅れ 0 件で「遅れなし」・今後 0 件で「該当なし」と出る。
- [x] 利用者文字列がエスケープされ、外部リソース参照ゼロ。
