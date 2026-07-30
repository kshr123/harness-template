---
id: T-0289
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-48]
verified_by:
  - tests/test_deliver_session.py::test_a_second_apply_after_more_edits_succeeds
---
# T-0289 取り込み後に編集セッションの土台を更新（A）
設計は EP-49 の DESIGN.md（A 節）。`apply` が新しい土台の `Session` も返し、サーバは `nonlocal` で `edit` を
差し替える（`discard` も返り値を使う）。取り込んだ後に続けて編集して 2 度目に `apply` しても、自分の apply を
「別の手が動かした」と誤検知して 409 にならない（「続けて編集できる」設計どおりに動く）。

## 受け入れ基準
- [ ] 1 度 apply → さらに編集 → 2 度目の apply が成功する（drift 誤検知の 409 が出ない）。
- [ ] 取り込む変更が無い状態での apply は従来どおり拒否される（fail-closed は維持）。
