---
id: T-0290
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-48]
verified_by:
  - tests/test_deliver_stamp.py::test_the_fingerprint_covers_every_value_shown_on_the_page
  - tests/test_deliver_stamp.py::test_the_fingerprint_covers_events
---
# T-0290 由来の指紋を「表に出ている値の全部」へ広げる（B）
設計は EP-49 の DESIGN.md（B 節）。`tree_fingerprint` が覆う値を、表示する列すべて（team・担当・工数・実績日・
milestone・進捗）と出来事（開催日）まで広げる。担当や実績日だけ変えた 2 版が同じ指紋になる穴を塞ぐ
（docstring の「表に出ている値そのもの」を実装に一致させる）。`late` は基準日由来なので入れない（生成日は別欄）。

## 受け入れ基準
- [ ] 担当・工数・実績日・milestone・出来事のいずれかを変えると指紋が変わる。
- [ ] 同じ入力からは同じ指紋（決定的）＝既存の安定性テストは緑のまま。
