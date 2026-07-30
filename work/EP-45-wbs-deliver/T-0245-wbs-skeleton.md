---
id: T-0245
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 1
requirements: [REQ-005, REQ-007]
depends_on: []
verified_by:
  - tests/test_deliver_overlay.py::test_derived_values_have_no_place_to_be_written
  - tests/test_deliver_overlay.py::test_section_entry_cannot_carry_status_or_dates
  - tests/test_deliver_wbs.py::test_parent_dates_come_from_children_even_if_the_parent_declares_its_own
  - tests/test_deliver_wbs.py::test_unscheduled_units_are_listed_not_dropped
  - tests/test_deliver_wbs.py::test_late_marks_only_overdue_and_unfinished
  - tests/test_deliver_wbs.py::test_workdays_count_both_ends_and_skip_weekends
  - tests/test_deliver_calendar.py::test_extra_workday_wins_over_weekend_and_holiday
  - tests/test_deliver_lint.py::test_uncovered_work_unit_fails
  - tests/test_deliver_lint.py::test_parent_declaring_its_own_dates_fails
  - tests/test_deliver_render.py::test_export_refuses_when_nothing_is_scheduled
  - tests/test_deliver_render.py::test_output_reads_nothing_from_outside
---
# T-0245 WBS の骨組み（入力→導出→出力が一巡する最小の実装）

端まで通る最小の骨組みを先に作り、`uv run verify` を全成功に保ったまま各部を本実装で差し替える。

## 作ったもの

- `src/harness/deliver/` プロファイル（`profile.py`・正本 `docs/deliver.md`・doc 索引への 1 行）。
- `overlay.py` … `docs/wbs.yaml`（暦・節構成・手動行）のスキーマ。導出できる値の欄を持たない。
- `calendar.py` … 営業日計算（土日＋祝日＋案件固有の非稼働日、振替出勤が優先）。期間は両端を含む。
- `wbs.py` … 木と上書きを結合し、WBS 番号・営業日数・ロールアップ・進捗・遅れを導出する（形式非依存）。
- `render.py` … 行レンダラ（1 つの表・各行のセル内に小さな SVG のバー）と自己完結 HTML の外殻。
- `wbs_lint.py` … 参照・覆い・重複・親子の日程・依存と日程の順序の検査（すべて既定を不合格側に置く）。
- `cli.py` … `uv run wbs export` と `uv run wbs lint`。
- 案件領域の根に `docs/wbs.yaml` を追加（`init_project.CASE_AREA_ROOTS`＋複製手順の `AREAS`）。
  併せて、還流候補を洗う pathspec に `docs/demands` が抜けていたのを補った（案件領域なのに本体領域として
  数えられていた）。

## 受け入れ基準

- [x] 上書きスキーマに WBS 番号・営業日数・進捗率・親行の日程を保存する欄が無く、未知キーが拒否されるか。
- [x] 日程あり・日程なしが混ざる木から生成したとき、出力にすべての単位が現れ、日程なしは未日程の印が付くか。
- [x] 日程を 1 件も持たない木からの生成が失敗するか（空の出力で成功しないか）。
- [x] 予定終了を過ぎて未完の単位だけが遅延の印を持ち、done・未到来には付かないか。
- [x] 営業日数が、土日・祝日・案件固有の非稼働日を除いて数えられ、振替出勤が非稼働日より優先されるか。
- [x] 生成物が外部リソースを 1 つも読まないか。
- [x] `uv run verify` にすべて成功するか。
