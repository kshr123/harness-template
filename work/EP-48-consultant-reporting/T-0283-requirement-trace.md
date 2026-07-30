---
id: T-0283
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
  - tests/test_deliver_report.py::test_the_requirement_trace_shows_coverage_and_gaps
  - tests/test_deliver_report.py::test_the_trace_section_is_omitted_without_a_requirements_layer
  - tests/test_pm.py::test_requirements_referencing_missing_docs_is_an_error_even_without_the_dir
  - tests/test_pm.py::test_no_requirements_at_all_is_ok
---
# T-0283 要件トレース被覆ビュー（DEM→REQ→work）＋ pm の fail-open 修正
設計は EP-48 の DESIGN.md（T-0283 節）。

- **pm の fail-open を塞ぐ**：work→REQ 参照検査が `docs/requirements/` が無いと素通りだった（satisfies は既に
  fail-closed）。`pm.requirement_trace`（known/referenced_by/dangling/uncovered）に集約し、req_dir が無くても
  非空の requirements は参照エラーにした（satisfies と対称）。要件を 1 つも書かない案件は従来どおり素通り。
- **被覆ビュー**：`WbsRow.requirements` を作業単位から導出で足し、report の付録に「要件→作業→状態／未カバーの
  要件」を出す。lint（pm.check）と同じ `requirement_trace` を見る（表と検査が食い違わない）。要件文書が無い
  案件では節ごと出さない（空表を出さない）。可視化でありゲートではない（参照切れ・未カバーは pm が扱う）。
  画面語は pm 既存の「未カバーの要件」を再利用（造語しない）。

## 受け入れ基準
- [x] 要件を参照する作業がある案件で REQ→作業→状態が出る。
- [x] 作業ゼロの REQ が「未カバーの要件」として出る／被覆集合が pm.check の未カバー info と一致。
- [x] 要件文書が無い案件では要件トレース節が出ない。
- [x] req_dir 不在でも非空 requirements が lint error（satisfies と対称の fail-closed・ミューテーションで RED 実測）。
