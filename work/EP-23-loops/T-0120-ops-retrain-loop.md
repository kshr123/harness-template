---
id: T-0120
kind: task
status: done
title: ops retrain 閉ループを time+goal 合成として位置づける
created: 2026-07-07
depends_on: [T-0095, EP-21]
verified_by:
  - tests/test_ci_lint.py::test_repo_retrain_template_passes
  - tests/test_ci_lint.py::test_retrain_template_out_of_order_steps_flagged
  - tests/test_ds_models.py::test_promotion_value_threshold_and_champion_move
  - tests/test_ds_models.py::test_promotion_change_threshold_reject
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
---
# T-0120 ops retrain 閉ループの loops 位置づけ（done）

## 狙い
EP-21（`harness.ops`）の継続学習（CT）雛形＝「schedule→experiment→`data monitor`→閾値を満たせば promote」は、
loops 語彙では **time-based（起動）× goal-based（停止＝関門合格）** の合成そのもの。EP-21 着地後、
retrain 雛形とその文書を loops 語彙（trigger×stop×policy）へ位置づけ、EP-23 の写像表を閉じた。

## 設計・判断（fable 詳細設計・確定）＝コード変更なし・docs＋同型性の固定＋EP-23 クローズ
**核の判断：ops retrain は `loops.py`（StopCondition）を実際に import しない**（DEC-0018 の再判断トリガ(2) を No で確定）。
コードの事実に基づく理由：(a) 実行体は GitHub Actions（`templates/ci/.../retrain.yml`・利用者環境）＝DEC-0017 が「loop 実行
エンジンは作らない」と引いた線の外＝`check()` を呼ぶ主体がハーネス側に無い（import させても形だけ＝金メッキ）。(b) 各 scheduled
run はステートレスな 1 周（sync→train→monitor→promote で終了）＝プロセス内に「停止条件まで繰り返すサイクル」が実在しない（反復を
統べるのは cron であって `StopCondition.check` でない＝T-0099 が ds sweep を loop でないとした同じ判定基準）。(c) 停止（先へ進む/
進まない）は `promote_model`（絶対 thresholds＝ds `eval.passes` ＋相対＝champion 越え）が既に完全に持つ＝StopCondition を挟むと
判定の正本が二重になる（DEC-0004 違反への入口）。DEC-0018 の accepted 本文は編集しない（No 確定の正本は本 item と docs/ops.md）。
- **同型性の固定**：agent の goal ゲート（`GoalGate`＝`AGENT_METRICS`＋agent `eval.passes`）と ops/ds の promote 関門
  （`promote_model`＝ds `eval.passes`〔絶対〕＋champion 越え〔相対〕）は**同じ形**＝「宣言済みの成功基準を、作った側とは別の評価器が
  検査して合格したときだけ先へ進む」（AGENTS 第一原則の機械化）。差分も固定（同型≠同一）：goal ゲートは同一プロセス内で未達なら
  続行注入して反復（`prior_messages`）／promote 関門はステートレスな 1 周を終えるだけ（不合格＝ValueError で退場・「続行」は次周の
  schedule が担う＝time が trigger・goal が stop の分業）。**実装は共有しない**（DEC-0004・`eval.passes` の agent/ds 併存は意図した
  複製・共有したくなったら DEC-0012＝DEC-0018 の再判断トリガに合流）。書く場所は item.md 写像表＋docs/ops.md の 2 箇所のみ
  （docs/agent.md の 4 類型表に ops 行は足さない＝T-0099 の判断を踏襲・二重管理を作らない）。
- **retrain 閉ループの loops 記述**（docs/ops.md の CT 節末尾を `### loops 語彙での位置づけ（time+goal 合成・T-0120）` に置換）：
  trigger=time（`schedule.cron`＋`workflow_dispatch`）× stop 2 層（1 周＝`promote_model` 関門／ループ全体＝workflow 無効化・停止規律
  の正本は docs/agent.md の T-0097 節を参照）× policy（`retrain.yml`×実験フォルダ config×thresholds/primary）。前半円
  （`data monitor --file-issue`）＋後半円（schedule→train→promote）は agent 版 proactive 閉ループ（T-0098）と対称＝参照（重複記述
  しない）。

## 受け入れ基準（detailed）
- `docs/ops.md` に loops 位置づけ subsection（trigger×stop 2 層×policy・前半/後半円・同型性＋実装非共有・実コード消費なしの確定・
  T-0097/0098 は参照のみ）。
- EP-23 item.md 写像表 ops 行を「実コード消費なし（T-0120 で確定）・promote 関門は GoalGate と同型（実装非共有）」で最終化。
- **`src/harness/**`・`templates/**` に差分なし**。`uv run verify` 全成功。
- EP-23 epic を done にする段取り（全 6 タスク done→epic status→done＋closed）。epic に verified_by は不要（pm 検査は task のみ対象）。

## verified_by（すべて既存・実在確認して束ねる）
- `tests/test_ci_lint.py::test_repo_retrain_template_passes`
- `tests/test_ci_lint.py::test_retrain_template_out_of_order_steps_flagged`
- `tests/test_ds_models.py::test_promotion_value_threshold_and_champion_move`
- `tests/test_ds_models.py::test_promotion_change_threshold_reject`
- `tests/test_doclint.py::test_real_repo_docs_have_no_dead_links`
（実名は着手時に grep で確認し、指す先が無ければ実在する同等テストに合わせる＝空振りは verify で失敗。）

## 効かせる guard（maker≠checker・このミューテーションで RED＝記述の指す実体の両端が既存テストで固定）
1. retrain.yml の step を並べ替え（監視→昇格の順序を崩す）→ `test_repo_retrain_template_passes`（ci_lint の ordered）が RED。
2. `promote_model` の相対関門を外す → `test_promotion_change_threshold_reject` が RED（絶対なら `test_promotion_value_threshold_and_champion_move`）。
3. 同型のもう一端（GoalGate）を DEC なしに一般化 → T-0099 の番人 `test_stop_condition_signature_stays_agent_shaped_until_dec` が RED（既存・重複計上しない）。

## やらないこと
実需要の無い StopCondition 消費（ops が `loops.py` を import しない＝形だけの統一は金メッキ）・数値メトリクス Protocol の今の新設・
`GoalGate`/`eval.passes` の core 引き上げ・ds⟷agent 相互 import（DEC-0004）・CI の再実装（schedule runner/retry を持ち込まない＝
DEC-0006/0008/0017）・retrain.yml/ci_lint の変更（EP-21 で完成）・docs/agent.md 4 類型表への ops 行追加・DEC-0018 本文の改変・新 CLI/スキル。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）＝EP-23 を閉じる最後のレビュー
設計・判断＝fable・実装＝sonnet・レビュー＝Opus（別モデル）。判断＋docs タスクなので観点は 3 つ：
- **実コード無変更の確認**：`git diff --stat -- src/harness templates` が空＝docs/ops.md＋item.md＋本 item のみ。ops retrain は
  `loops.py` を import しない判断が実装にも反映（形だけの統一＝金メッキを作っていない）。✓
- **判断の faithfulness**：docs/ops.md の loops 位置づけ節は trigger×stop（2 層）×policy・前半/後半円・**同型性（GoalGate ⟺
  promote_model）を差分込みで固定**（同型≠同一・実装非共有 DEC-0004）・「`loops.py` import 不要（T-0120 で確定）」を明言（両論
  併記に薄めていない）。T-0097（停止規律）・T-0098（proactive）は参照のみで重複記述なし。DEC-0018 本文は不改変。薄まりなし。✓
- **記述の指す実体が既存テストで固定**：verified_by の 5 テスト（ci_lint の retrain 緑＋順序検査・promote の絶対/相対関門・doclint
  参照整合）を実在確認＋実行し 5 passed＝docs が語る「監視→昇格の順序」「絶対＋相対の関門」「同型のもう一端＝GoalGate 番人（T-0099）」
  の両端が緑で固定。ci_lint/promote の順序・関門 guard は EP-21 着地時にミューテーションレビュー済み（[[harness-project-state]]）。✓
- `uv run verify` 全成功（epic done↔verified_by 結びつけ・epic 整合含む）。`uv run status` で EP-23 = 6/6 done。**APPROVE**。
  **これで EP-23（loops 運用モデル）の写像表は全行が「実装済み／適用しない判断済み／記述で確定」で閉じ、epic クローズ。**
