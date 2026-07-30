---
id: T-0284
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
  - tests/test_deliver_geometry.py::test_each_row_carries_its_dependencies_as_json
  - tests/test_deliver_script.py::test_the_embedded_scripts_parse
---
# T-0284 依存の可視化（ホバーで先行/後続）
設計は EP-48 の DESIGN.md（T-0284 節）。`_row_html` に `data-deps`（先行の JSON 配列。空白入り ID でも壊れない）
を足し、後続は JS が逆写像で 1 回作る。行にかざすと先行・後続を淡く光らせる（既存の選択色・新色なし・矢印なし）。
ガント列には地色を当てない（不変条件を維持）。

## 受け入れ基準
- [x] 各行が先行を JSON で持つ（値が depends_on と一致・空は空配列）。
- [x] 埋め込み JS が構文として通る（script テスト）。
- [x] ホバーで先行/後続の行に dep-hi が付き、離すと消える（ヘッドレスで先行↔後続の両方向を実測）。
