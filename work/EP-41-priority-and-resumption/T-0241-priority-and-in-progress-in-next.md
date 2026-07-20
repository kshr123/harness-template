---
id: T-0241
kind: task
status: done
title: priority を status --next の並べ替えに消費させ、仕掛かり中の再開候補を可視化する
created: 2026-07-21
closed: 2026-07-21
depends_on: []
verified_by:
  - tests/test_pm.py::test_next_actionable_orders_ready_by_priority_then_id
  - tests/test_pm.py::test_next_actionable_lists_in_progress_leaves
  - tests/test_pm.py::test_invalid_priority_value_is_rejected
---
# T-0241 優先度の運搬と再開の可視化

## なぜ
`Item.priority`・`owner` は models.py に定義だけあって消費箇所ゼロだった。優先順位は条件3が明記する
「人にしか置けない判断」だが、機械の役割は決めることでなく人が置いた順位をエージェントまで運ぶこと。今は会話で
運んでいて、セッションを跨ぐと消え、fork 後に `status --next` から自走するエージェントには届かず ready は ID 順＝
偶然の FIFO。定義だけして何も消費しない状態はこの基盤が最も嫌うスキーマの静かな嘘でもある。あわせて、blocked/
in-review は「人の判断待ち」に出るのに in-progress の放置はどこにも警告されず、セッション跨ぎ・並列 worktree で
「再開せず新規着手」の逸失が起きうる。

## 何を
- `models.py`：`Priority`（high/normal/low）を列挙で定義（自由文字列は順序づけられない・タイポは検証で失敗＝
  保証(a)）。`priority: Priority | None`。`Item.priority_rank`（high=0/normal・無指定=1/low=2）を並べ替え鍵に。
- `pm.py`：`next_actionable` を4分類（in_progress / ready / waiting / to_outline）に拡張。並びは
  priority→ID。`render_next` に「仕掛かり中（再開の候補）」節を先頭に追加。門番にはしない（時間閾値なし）。
- `AGENTS.md`：item frontmatter の任意欄に `priority` を追記し、`status --next` の並び順を明記（発見可能性）。
- `owner` は削除しない：履歴タスク（work/EP-05/07/08 等）と init_project の生成テンプレに実データとして存在し、
  extra=forbid で消すと過去単位が parse 不能になる（履歴の書き換えを強いる）ため残す。

## 検証
`uv run verify` 全成功。`test_next_actionable_orders_ready_by_priority_then_id`＝high が先頭・low が末尾・無指定は
中位で ID 順（優先度を置いた単位だけが上下する）。`test_next_actionable_lists_in_progress_leaves`＝in-progress の
末端だけを再開候補に集める（分解済み epic は出さない）。`test_invalid_priority_value_is_rejected`＝未知の優先度
`urgent` は pm.lint が error（列挙で done にさせない）。

maker≠checker（別 fable）が「置いた判断が静かに捨てられる」型の取りこぼしを3件指摘＝すべて修正：
(1) in-progress の investigation が再開候補に出なかった → 末端の作業単位を task/experiment/investigation に統一
（`test_next_actionable_lists_in_progress_leaves` に investigation を追加）。(2) outline epic に置いた priority が
無視されていた → to_outline も priority→ID で並べ替え＋印表示（`test_next_actionable_orders_outline_epics_by_priority`）。
(3) `cli.py` の --next ヘルプが3分類のまま → 仕掛かり中を追記。
