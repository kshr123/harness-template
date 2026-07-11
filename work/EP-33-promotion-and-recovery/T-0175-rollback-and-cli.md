---
id: T-0175
kind: task
status: done
title: 切り戻し（rollback）と昇格 CLI を揃える（ds 側に promote/champion が無い非対称の解消）
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0173]
verified_by:
  - tests/test_promotion_rollback.py::test_ds_rollback_restores_worse_previous_champion_without_a_gate
  - tests/test_promotion_rollback.py::test_ds_promote_after_rollback_still_obeys_the_gate
  - tests/test_promotion_rollback.py::test_ds_second_rollback_has_no_target_and_does_not_ping_pong
  - tests/test_promotion_rollback.py::test_ds_rejected_promotion_is_recorded_but_champion_does_not_move
  - tests/test_promotion_rollback.py::test_agent_rollback_restores_worse_previous_champion_without_a_gate
---
# T-0175 切り戻しと CLI

## 何が問題か
1. **戻せない。** champion が劣化していたと後から分かっても、前の版に戻す手段が無い。
   `promote_model(前の版)` は `change_threshold`（現 champion からの改善）に落ちて必ず却下される。
   昇格は一方向のラチェットで、外す機構が付いていない。
2. **却下の記録が残らない。** 何を却下したかは監査で最も知りたい情報のひとつ（SageMaker は Rejected の
   モデルパッケージを保持する）。今は例外を投げて消える。
3. **CLI が非対称。** `agent promote` / `agent champion` はあるのに、`data`（ds プロファイル）には昇格の
   入口が無い。モデルを昇格する正規の手順が CLI から辿れない。

## 構造
- `promotion.rollback(entity_dir, ...)`：alias が指す記録の `rollback_to` を辿り、alias を貼り替える。
  **判定は通さない**（切り戻しは昇格ではない。「劣る版に戻せない」は機能ではなく欠陥）。
  監査のため `kind: rollback` の記録を追記する。`rollback_to` が null なら ValueError（戻り先が無い）。
  切り戻し記録の `rollback_to` は、戻り先の記録の `rollback_to` を引き継ぐ（もう 1 段戻せる＝スタックを pop）。
- 却下も記録する（`status: rejected`・alias は貼り替えない）。alias が正本なので履歴に何が積まれても
  champion は動かない＝T-0174 が前提。
- CLI：`data promote` / `data champion` / `data rollback` / `data promotions`（履歴）、
  `agent rollback` / `agent promotions`。導線を正本 docs（`docs/ds.md`・`docs/agent.md`）とスキルに書く
  （書かないと `coverage_lint` が verify を失敗させる）。
- alias が指す版・記録の実在検査を lint に足す。

## 受け入れ基準
- 昇格 v1 → v2 のあと `rollback` で champion が v1 に戻る（判定に阻まれない）。
- 2 回目の `rollback` は v1 の戻り先（無ければ ValueError）へ。ping-pong（v1↔v2 を往復）しない。
- 切り戻し後に v2 を再昇格しようとすると、baseline は v1 になる。
- 却下された昇格の記録が `promotions/` に `status: rejected` で残り、`champion()` は動かない。
- 戻り先の版の実体が消えていたら ValueError（黙って壊れた champion を指さない）。
- `coverage_lint` が新コマンドを未到達にしない。
- `uv run verify` 全成功。
