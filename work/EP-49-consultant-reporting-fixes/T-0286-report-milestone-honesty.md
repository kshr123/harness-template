---
id: T-0286
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-48]
verified_by:
  - tests/test_deliver_report.py::test_a_done_milestone_without_a_recorded_finish_is_not_stamped_with_its_due
  - tests/test_deliver_report.py::test_the_report_heading_names_the_resolved_commit_of_the_baseline
---
# T-0286 報告のマイルストーン粉飾を塞ぐ（D1）＋見出しに解決コミット（W1）＋定例/節目の docs 矛盾（F）
設計は EP-49 の DESIGN.md（D1・W1・F 節）。done だが実績終了（`closed`／`actual_finish`）が無いマイルストーンで、
予定日を「実績」と名乗る粉飾を止める（記録が無ければ「実績日の記録なし」と明記し、遅延判定も実績があるときだけ）。
報告の見出しに合意時点の解決コミットを併記する（`stamp.label_for`）。定例会議は `events` に一本化する記述へ
docs/deliver.md と overlay.py の矛盾を正す。

## 受け入れ基準
- [ ] done・実績終了なしのマイルストーンが「達成／実績 <予定日>」と出ない（「実績日の記録なし」と明記する）。
- [ ] 実績終了があり期日超過なら「遅れて達成（予定→実績）」、期日内なら「達成（実績）」と出る。
- [ ] `--against` の見出しに解決コミットが併記される。
- [ ] docs/overlay に「定例会議を rows／期間の帯として置く」矛盾が残っていない。
