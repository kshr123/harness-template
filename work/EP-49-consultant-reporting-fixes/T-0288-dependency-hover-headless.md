---
id: T-0288
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-48]
verified_by:
  - tests/test_deliver_browser.py::test_hovering_a_successor_highlights_its_predecessor
  - tests/test_deliver_browser.py::test_hovering_a_predecessor_highlights_its_successor
---
# T-0288 依存ホバーのヘッドレス実測（D3）
設計は EP-49 の DESIGN.md（D3 節）。実ブラウザ（headless Chrome）で行に `mouseenter` を発火させ、`--dump-dom` の
DOM に `dep-hi` が先行・後続の**両方向**へ付くことを確かめる。土台（Chrome ロケータ＋dump-dom 実行）は
`tests/_headless.py` に置き再利用可能にする。Chrome が無い環境は ISS-0018 を参照して skip する。

## 受け入れ基準
- [ ] 依存 A→B で B にかざすと A（先行）に dep-hi が付く（実ブラウザの DOM で確認）。
- [ ] 同じく A にかざすと B（後続）に dep-hi が付く（逆写像の実測）。
- [ ] 無関係な行には dep-hi が付かない。
- [ ] Chrome が無ければ ISS-0018 参照で skip（データ側検査・JS 構文検査は常に回る）。
