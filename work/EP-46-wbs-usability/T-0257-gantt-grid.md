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
  - tests/test_deliver_geometry.py::test_no_shaded_bands_clutter_the_gantt
  - tests/test_deliver_geometry.py::test_the_drawing_window_snaps_to_whole_months
  - tests/test_deliver_geometry.py::test_a_one_day_project_does_not_fill_the_whole_column
---
# T-0257 ガントを図表に見せる

## 直すこと
- **時間軸の格子**を各行に引く（軸の目盛と同じ位置）。棒だけが浮いていると図表に見えない。
- 時間軸の格子（各行）で週・月の区切りを示す。（非稼働日の帯は後に撤去＝T-0265。各週の右に灰色が並んで棒より目立ったため。営業日は「日数」の列で分かる。）
- **描画の窓**を月の境目に合わせる（1 日始まり・月末終わり）。期間が数日の案件で棒が列いっぱいに広がり、
  ただの帯にしか見えない状態を無くす。

## 受け入れ基準
- [x] 各行に時間軸の格子が引かれ、位置が軸の目盛と一致するか。
- [x] 週・月の区切りが格子で分かるか。
- [x] 期間が 1 日の木でも、棒が列いっぱいにならないか。
- [x] 描画の窓が月の境目に揃っているか。
