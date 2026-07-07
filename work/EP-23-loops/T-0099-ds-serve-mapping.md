---
id: T-0099
kind: task
status: done
title: ds/serve への loops 語彙の写像（sweep の goal 化の判断点・serve は loop でない旨の正本化）
created: 2026-07-07
depends_on: [T-0095]
verified_by:
  - tests/test_agent_goal.py::test_stop_condition_signature_stays_agent_shaped_until_dec
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
---
# T-0099 ds/serve への loops 語彙の写像（done）

## 狙い
loops 語彙（trigger×stop×policy）を ds/serve に写像し、**どこまで適用し・どこは適用しないか**を正本化する。
ds の実験 sweep（「閾値達成（`passes`）まで変種探索」）は goal-based の 2 個目の消費候補＝
`loops.StopCondition` を一般化するかの **DEC-0012 判断点**。serve はリクエスト駆動（1 呼び 1 応答）＝
loop ではなく、**適用しない判断**も写像表に残す（無理に統一しない）。

## 設計・判断（fable 詳細設計・確定）＝コード変更なし・docs と判断の正本化のみ
**核の判断：ds sweep を `loops.StopCondition` の 2 個目の消費に「しない」。** コードの事実＝`ds/experiment.py::run_experiment`
は 1 変種を 1 回 CV 評価して `ExperimentResult(passed=passes(...))` を返して終わる（反復・サイクル無し）。変種は人が config で
宣言する fan-out（experiment スキル）で、`passes` は各変種への**合否ラベル（フィルタ）**＝loop の停止条件として消費されていない。
**ds sweep は loop でなく fan-out＋filter**＝`StopCondition.check(output: str, ...)` を広げる実在の根拠が無い（DEC-0012 の判断点で
No）。将来の一般化トリガ：(1) sklearn `*SearchCV`／optuna で吸収できない反復制御が実案件で要る、(2) T-0120 で ops 閉ループが実
コードの停止条件消費を要すると判断されたとき。そのときも `output: str` を広げず**数値メトリクス用の別 Protocol を core に足す**方向を
第一候補にする（agent の GoalGate を触らない）。
- **DEC-0018（新規・accepted）**：`docs/decisions/DEC-0018-loops-scope-ds-serve-ops.md`。「loops 語彙の適用範囲＝StopCondition は
  当面 agent 専用・ds は fan-out+filter（loop でない）・serve は loop でない・ops retrain は記述のみ」＋再判断トリガ条件＋「広げる
  ときは別 Protocol」の釘。関連 [[DEC-0004]][[DEC-0006]][[DEC-0012]][[DEC-0017]]。新規 DEC の理由＝DEC-0017 が ds sweep を候補と
  名指ししたが「loop として実在しなかった」という期待の更新（accepted 本文は書き換えず新 DEC で上書き＝DEC-0012 が DEC-0005 を改定
  したのと同型）。
- **serve = not a loop**：`docs/serve.md` 末尾に 1 節（1 呼び 1 応答のレイテンシ契約＝「繰り返して停止条件」に該当しない・応答経路に
  評価器ゲートを挟むのは配信の関心と衝突・serve を回す loop は外側＝予測 JSONL→data monitor→retrain の ops 周回）。`docs/agent.md` の
  loops 節末尾に導線 1 行（横展開の正本は DEC-0018）。
- **ops retrain＝記述のみ・`src/harness/ops/**` は触らない**：写像＝time（cron）＋workflow_dispatch trigger × `promote_model`（絶対
  thresholds＋相対 champion 越え）関門 stop × `retrain.yml`（ci_lint 検査）policy。実コードの停止条件消費は T-0120 の領分（DEC-0017/item.md
  が既定）。`docs/ops.md` の CT 節に位置づけ 1–2 文だけ足す。
- **写像表（EP-23 item.md）** の ds/serve/ops 行を実名・「消費なし／適用しない／記述のみ」で更新。

## 受け入れ基準（detailed）
- `docs/decisions/DEC-0018-*.md` が存在（ds=fan-out+filter／serve=not a loop／ops=記述のみ＋再判断トリガ）。
- `docs/serve.md` に「serve は loop でない」節（DEC-0018 参照）・`docs/agent.md` 導線 1 行・`docs/ops.md` CT 節 1–2 文。
- EP-23 item.md 写像表 3 行を実名・消費有無で更新。
- **`src/harness/**` の実装コードに差分なし**（下の番人テスト以外）。`uv run verify` 全成功。

## verified_by（代表テスト）
- `tests/test_agent_goal.py::test_stop_condition_signature_stays_agent_shaped_until_dec`（新規・番人。
  T-0133／DEC-0020 で `harness.loops` が `agent/goal.py` へ畳み込まれ、旧 `tests/test_loops.py` から移設）。
- `tests/test_doclint.py::test_real_repo_docs_have_no_dead_links`（新 DEC・パス参照の整合）
- （退場）`tests/test_loops_module_import_is_stdlib_only` は `harness.loops` モジュールの消滅（T-0133）に伴い削除。
  「軽さ維持」の保証はモジュールごと消えた＝現在は対象なし（`agent/goal.py` は元々 agent 内の重さを許容）。

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. `loops.StopCondition.check` のシグネチャを広げる（例：`output` の型を外す／引数追加）→
   `test_stop_condition_signature_stays_agent_shaped_until_dec` が RED（DEC なしの一般化を機械で止める＝DEC-0012 の「ルール昇格は
   違反すると失敗する検査を先に」）。

## やらないこと
実需要の無い一般化（消費者が現れる前に StopCondition を広げない＝YAGNI・DEC-0012）。`StopCondition` の引数一般化・数値メトリクス
Protocol の今の新設・`LoopSpec`・core への `passes` 引き上げ・ds への自動探索 CLI（第一候補は sklearn `*SearchCV`／optuna＝再発明しない）・
serve への goal ゲート適用・`src/harness/ops/**`／`src/harness/serve/**` の実コード変更・docs/agent.md の 4 類型表への ds/serve/ops 行追加
（横展開の正本は DEC-0018＋item.md 写像表に一本化＝二重管理を作らない）。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計・判断＝fable・実装＝sonnet・レビュー＝Opus（別モデル）。判断タスクなので観点は 2 つ：(1) 番人テストが本当に効くか、
(2) 判断の正本（DEC-0018・docs）が薄まっていないか。
- **番人テスト**：`loops.StopCondition.check` に kw-only 引数を 1 つ足すミューテーション → `test_stop_condition_signature_
  stays_agent_shaped_until_dec` が RED を実測（バックアップ→ミューテート→RED→loops.py をバイト同一復元）。DEC なしの一般化を
  機械で止める番人が生きている。✓
- **判断の faithfulness**：DEC-0018 は選択肢 A/B を挙げて **B を明確に採用**（両論併記に薄めていない）・理由はコードの事実
  （`run_experiment` は 1 変種 1 回・反復不在）に基づく・再判断トリガ 2 件＋「広げるときは `output:str` でなく別 Protocol」の釘・
  DEC-0004/0006/0012/0017 へ関連リンク。「否定形の判断は未着手と誤読されうる」悪い点も自認し docs 導線で緩和。docs/serve.md の
  「serve は loop でない」節・item.md 写像表 3 行（ds=消費なし／serve=適用しない／ops=記述のみ・実名つき）も一致。薄まりなし。✓
- **実コード無変更の確認**：`git diff --stat src/harness/` 空＝docs＋番人テストのみ（判断タスクの範囲を守っている）。✓
- doclint 緑（新 DEC・パス参照の整合）・`uv run verify` 全成功。**APPROVE**。
