---
id: T-0282
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
  - tests/test_deliver_geometry.py::test_baseline_overlay_draws_the_agreed_bar_at_its_own_dates
  - tests/test_deliver_geometry.py::test_baseline_outside_the_current_window_stays_within_the_column
  - tests/test_deliver_geometry.py::test_no_baseline_means_no_agreed_bar
  - tests/test_deliver_formats.py::test_against_is_refused_for_non_html_and_with_at
---
# T-0282 ベースライン重ね描き（export --against <ref>）
設計は EP-48 の DESIGN.md（T-0282 節）。`tree_at`+`build` で合意時点の棒の期間を `WbsRow.key` ごとに集め
（`baseline.baseline_map`）、現状の棒の下に淡い棒（`.gbar-base`）を重ねる。座標は `_pct`/`_day_pct` の 1 実装、
描画窓は現行とベースラインの日付の合併（窓外で 0–100% を外れない）、色は既存の淡青（新色なし）。突き合わせ鍵は
`WbsRow.key`（差分と共通・規則を 2 か所に持たない）。

## 受け入れ基準
- [x] 合意時点の期間が別の淡い棒として `_at()` 由来の位置に出る（現状の棒は据え置き）。
- [x] 現行窓の外のベースライン日付でも left/width が 0–100% に収まる（窓の合併）。
- [x] `--against` 未指定なら淡い棒は要素として出ない。
- [x] `--against`×非 HTML と `--against`×`--at` は exit 1（黙って層を落とさない）。
- [x] 既存の geometry テストが緑（座標の第 2 実装を作らない）。
