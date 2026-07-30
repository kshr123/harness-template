---
id: T-0291
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-48]
verified_by:
  - tests/test_deliver_lint.py::test_a_manual_row_depending_on_a_missing_id_fails
  - tests/test_deliver_lint.py::test_a_manual_row_depending_on_an_existing_id_is_fine
  - tests/test_deliver_lint.py::test_a_manual_row_depending_on_itself_fails
  - tests/test_deliver_lint.py::test_a_milestone_dated_before_its_predecessor_ends_fails
---
# T-0291 手動行 depends_on の参照検査＋マイルストーンの依存順序（C+D）
設計は EP-49 の DESIGN.md（C・D 節）。手動行（ManualRow）の各 `depends_on` が「作業単位 ID ∪ 手動行 ID」に
実在することを wbs_lint で検査する（pm は手動行を知らないので素通りしていた穴）。依存順序の検査は
`start is None` でマイルストーンを飛ばさず、マイルストーンの実効開始＝`due` として矛盾を見る。

## 受け入れ基準
- [ ] 手動行の depends_on が実在しない ID を指すと error になる。
- [ ] 手動行が実在する作業単位・他の手動行を指すのは通る。
- [ ] 先行の終了予定より前に置いたマイルストーンが依存順序の矛盾として error になる。
