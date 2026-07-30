---
id: T-0292
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-48]
verified_by:
  - tests/test_deliver_script.py::test_the_fold_controls_target_only_toggle_buttons
  - tests/test_deliver_browser.py::test_folding_all_does_not_write_a_triangle_into_leaf_rows
---
# T-0292 折りたたみが末端行に三角（▸）を書く不具合（E）
設計は EP-49 の DESIGN.md（E 節）。「全て折りたたむ／展開」の `setAll` が `.tw`（末端の空 `<span class="tw">` を
含む）すべてに `▸`/`▾` を書き込み、子を持たない末端行に無いはずの三角が出る。個別クリックの `closest('.tw')` も
同じ。トグルの対象を `button.tw`（親行の実ボタン）に限る。

## 受け入れ基準
- [ ] 折りたたみ／展開の対象が親行の `button.tw` に限られ、末端の `span.tw` に三角が書かれない。
- [ ] 親行の折りたたみ・展開・個別クリックの挙動は従来どおり。
