---
id: T-0300
kind: task
status: done
created: 2026-07-31
closed: 2026-07-31
start: 2026-07-31
due: 2026-07-31
effort_days: 1
requirements: []
depends_on: []
verified_by:
  - tests/test_verification_mechanism.py::test_retracted_checks_are_not_re_registered
---
# T-0300 効かない不変検査を撤回する（retraction_lint・pm.spec_lint）

fable の全体棚卸しに基づく撤回（撤回の是非はオーナー判断＝承認済み）。基盤自身の「効かない決まりごとは
撤回する」を verify そのものに適用。

- `retraction_lint`：`RETRACTED={}` で常に空＝steady state が no-op。モジュールとテストを削除し、INVARIANT_CHECKS
  から外す。残骸検査は撤回という一手の中で 1 度 grep すれば足りる（AGENTS の撤回原則＋harvest スキルへ移した）。
- `pm.spec_lint`：SPEC.md の見出しの有無だけ＝空見出しは通る＝防ぎたい失敗（受け入れ基準の欠落）を防げていない
  儀式。関数とテストを削除し INVARIANT_CHECKS から外す。受け入れ基準の質はレビュー観点（level c）。
- 後戻り防止：tombstone テスト（loops.py と同じ作法）で誤った再登録・モジュール復活を止める。
- 撤回の記録は `docs/learnings.md` L-026。core.md は doc-sync で再生成（不変検査 18→16）。
