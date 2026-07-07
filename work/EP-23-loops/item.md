---
id: EP-23
kind: epic
status: todo
title: loops 運用モデル（trigger×stop×policy）と goal-based 停止ゲート（評価器が合格と言うまで止めない）
plan: detailed
requirements: [REQ-002]
depends_on: [EP-22]
created: 2026-07-07
---
# EP-23 loops 運用モデル（trigger×stop×policy）

## 目的（Anthropic「Getting started with loops」の取り込み＝運用モデルへの昇格）
出典: https://claude.com/blog/getting-started-with-loops 。**loop＝停止条件が満たされるまで作業サイクルを
繰り返すエージェント**で、**trigger（起動）× stop-condition（停止）× policy（方針）**で分類される：
(1) turn-based/manual（発話が起動・モデルが完了判断）・(2) goal-based（**評価器**が宣言した成功基準を検査し、
満たすまで止めさせない）・(3) time-based（時間間隔で起動・cancel で停止）・(4) proactive（schedule＋goal の
合成。各タスクは goal 達成で退場・routine は無効化まで継続）。

この分類を**プロジェクト全体の運用モデル**（agent / ds / serve / ops をすべて loop として運用する語彙）へ
昇格する（DEC-0017）。最大スコープはビジョンであり、**ビルドは全体→詳細**（method.md A 節）：最初の縦切りは
「core の語彙＋agent の goal-based ループ」だけを detailed にし、time/proactive と横展開は outline に留める。

**なぜ goal-based が本ハーネスに効くか**：AGENTS の第一原則「完了＝検証にすべて成功したときだけ・自己申告で
完了にしない」は、いま人間とスキルの規律で守られている。goal-based loop はこの原則を**エージェント実行そのもの**
に機械化する＝モデルの end_turn（「完了した気になった」）を宣言済みの評価器（`AGENT_METRICS`＋`eval.passes`・
fail closed）が検査し、未達なら続行を注入する。maker（モデル）≠checker（評価器）の構図がループ内に入る。

## 写像表（何が既存流用・何が新規＝再発明しない・DEC-0006/0008）
| loops 類型 | trigger | stop | policy | 既存で足りる（実名） | 新規/変更 |
|---|---|---|---|---|---|
| turn-based / manual | ユーザ発話・`agent run` | provider の `end_turn`＋`max_turns` backstop | AgentSpec（宣言） | `runtime.run_agent`（tool_use 往復・`stop_reason="max_turns"` 打ち切りまで実装済み） | **なし**（語彙の再解釈のみ） |
| goal-based | 呼び出し時に goal を宣言 | **評価器ゲート**（`AGENT_METRICS`＋`eval.passes`）合格 or `max_cycles` backstop | Goal（metrics×thresholds×expected）＋続行文の注入 | 採点＝`AGENT_METRICS`・合否＝`eval.passes`（fail closed）・往復＝`run_agent` を丸ごと再利用 | **唯一の新 primitive**：core `loops.py`（StopCondition 語彙）＋`agent/goal.py`（GoalGate・run_agent_to_goal）＋`run_agent` の続行口 `prior_messages`（T-0095） |
| time-based | 時間間隔（cron/CI schedule・Claude 側 /loop・/schedule スキル） | cancel・無効化 | runbook（何を見て何をするか） | `agent monitor`・`data monitor`（読む側は完成）・issues backend | 雛形と runbook のみ（実行基盤は利用者環境＝EP-21 の CI テンプレと同じ思想）。outline（T-0097） |
| proactive | event/schedule＋goal の合成 | 各タスク＝goal 達成で退場・routine＝無効化まで | triage 方針（冪等起票・門番にしない） | `agent monitor --file-issue`（冪等起票＝閉ループの前半円は実装済み） | 後半円（issue→修正→検証緑で close）を loops 語彙で設計。outline（T-0098） |
| （横展開）ds | 実験の反復 | 閾値達成（`passes`）まで変種探索 | config の変種 | `run_experiment`・`leaderboard`・`promote_model` | 語彙の写像のみ＝StopCondition の 2 個目の消費が出たら一般化（DEC-0012）。outline（T-0099） |
| （横展開）serve | リクエスト駆動 | —（loop ではない） | — | `/predict`・`/invoke` | **適用しない判断を正本に残す**だけ。outline（T-0099） |
| （横展開）ops | schedule＋goal の合成（retrain） | 監視帯→再学習→関門合格で昇格 | retrain.yml | EP-21 の CT 雛形（monitor→experiment→promote） | **EP-21 着地後**に loops 語彙へ位置づけ（T-0120・depends_on: EP-21） |

## 置き場所の設計判断（core に語彙だけ・実装はプロファイル）
- **`src/harness/loops.py`（core・新規）に置くのは語彙だけ**：`Trigger`（4 類型の Literal）・`StopDecision`・
  `StopCondition`（Protocol）。**stdlib のみ**（DEC-0013 の軽さ＝core は numpy を 1 つも持たない実測を守る）。
  根拠：loop は agent 固有でない（ds の sweep・ops の retrain も trigger×stop×policy で書ける＝一般性が既に
  見えている）が、**プロファイル同士は import できない（DEC-0004）**ので共有は core 経由が唯一の置き場。
- **loop 実行エンジン（scheduler・常駐 runner）は core に作らない**：時間起動は cron/CI schedule/Claude 側
  /loop・/schedule スキルが既にある＝再発明（DEC-0006/0008）。ハーネスが持つのは停止条件の**宣言と検査**だけ。
- **goal ゲートの実装は agent プロファイル**（`src/harness/agent/goal.py`）：採点器（`AGENT_METRICS`）と合否
  （`eval.passes`）は agent の資産で、core へ引き上げない（消費者は今 1 つ＝DEC-0012 の「必要になった時に即」
  の反対側。3 個目の消費が出たら昇格を DEC 化する＝eval.py の複製と同じ扱い）。
- **`LoopSpec` は作らない**（YAGNI）：宣言の正本は AgentSpec と Goal 側にあり、core に宣言の重複を作ると
  二重管理になる。分類の語彙（Trigger）だけで足り、束ねる型は 2 個目の消費で判断（DEC-0012）。

## タスク分解（近い作業だけ detailed＝AGENTS 原則）
- **T-0095 歩く骨組み（detailed）**：core `loops.py`（語彙）＋`agent/goal.py`（GoalGate・run_agent_to_goal）＋
  `run_agent` の続行口＋`agent run` の goal オプション＋`--test` スモーク。**verify は無ネットワーク**
  （dummy の台本＋`_cut_network`＝DEC-0015 の既存パターン）。DEC-0017 の accepted 化まで。
- **T-0096 goal の judge 化と宣言化（outline・soon）**：rubric/LLM-judge 採点器（dummy judge→cassette）＋
  goal の YAML 宣言。
- **T-0097 time-based の導線（outline・soon）**：monitor 定期実行の runbook＋schedule 雛形（実行基盤は利用者環境）。
- **T-0098 proactive triage 閉ループ（outline・later）**：`--file-issue` の後半円（issue→修正→検証緑で close）。
- **T-0099 ds/serve への語彙の写像（outline・later）**：sweep の goal 化の判断点・serve は loop でない旨の正本化。
- **T-0120 ops retrain 閉ループ（outline・later・EP-21 着地後）**：CT 雛形を time+goal 合成として位置づけ。
  **EP-21 が進行中のため `src/harness/ops/**`・`docs/ops.md` には着地まで一切触れない**（depends_on: EP-21）。

## やらないこと（過剰設計の釘・順序の理由）
- **汎用 loop 実行エンジン／常駐デーモン／自前 cron**：実行基盤は利用者環境（cron・CI schedule・Claude 側
  スキル）に委ねる（EP-21 と同じ「テンプレ＋構造 lint＋導線」の思想。DEC-0006/0008）。
- **`LoopSpec`・loop レジストリ・StopCondition の早すぎる一般化**：消費者 1 つで抽象を切らない
  （2 個目＝ds sweep が実際に要ったとき DEC-0012 で判断）。
- **自律 auto-fix の即時実装**：proactive の後半円（修正の自動適用）は maker≠checker を壊しやすい＝
  独立レビュー・人の承認を挟む設計を T-0098 で先に固めてから（起票までの前半円は実装済みで十分回る）。
- **goal の自動生成・goal 未宣言時の推定**：goal は人が宣言する（宣言が正本＝DEC-0004 と同型）。
- **serve への goal 適用**：`/invoke` はリクエスト駆動（1 呼び 1 応答の契約）＝loop でない。レイテンシに
  評価器ゲートを挟むのは配信の関心と衝突する（写像表に「適用しない」を残す）。
- いずれも DEC-0014 の対象内で順序後回し（対象外ではない）。
