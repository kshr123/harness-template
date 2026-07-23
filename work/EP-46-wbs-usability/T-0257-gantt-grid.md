---
id: T-0257
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
requirements: []
depends_on: []
verified_by:
  - tests/test_deliver_geometry.py::test_every_row_carries_the_time_grid
  - tests/test_deliver_geometry.py::test_non_working_days_are_shaded
  - tests/test_deliver_geometry.py::test_the_drawing_window_snaps_to_whole_months
  - tests/test_deliver_geometry.py::test_a_one_day_project_does_not_fill_the_whole_column
---
# T-0257 ガントを図表に見せる

## 直すこと
- **時間軸の格子**を各行に引く（軸の目盛と同じ位置）。棒だけが浮いていると図表に見えない。
- **非稼働日（土日・祝日・案件の休業日）の帯**を敷く。営業日で数えていることが図でも分かる。
- **描画の窓**を月の境目に合わせる（1 日始まり・月末終わり）。期間が数日の案件で棒が列いっぱいに広がり、
  ただの帯にしか見えない状態を無くす。

## 受け入れ基準
- [x] 各行に時間軸の格子が引かれ、位置が軸の目盛と一致するか。
- [x] 土日・祝日・案件の休業日に帯が敷かれるか（長すぎる期間では敷かない）。
- [x] 期間が 1 日の木でも、棒が列いっぱいにならないか。
- [x] 描画の窓が月の境目に揃っているか。
