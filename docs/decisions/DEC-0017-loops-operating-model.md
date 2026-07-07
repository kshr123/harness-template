---
id: DEC-0017
status: accepted
date: 2026-07-07
---
# DEC-0017 loops（trigger×stop×policy）を運用モデルの語彙として正本化し、新規に作るのは goal-based 停止ゲートだけにする

## 状況（何を決める必要があったか）
Anthropic 公式コンセプト「Getting started with loops」（https://claude.com/blog/getting-started-with-loops）は
**loop＝停止条件が満たされるまで作業サイクルを繰り返すエージェント**と定義し、**trigger（起動）×
stop-condition（停止）× policy（方針）**で 4 類型に分類する：turn-based/manual（発話が起動・モデルが完了判断）・
goal-based（**評価器**が宣言済みの成功基準を検査し、満たすまで止めさせない）・time-based（時間間隔で起動・
cancel で停止）・proactive（schedule＋goal の合成。各タスクは goal 達成で退場・routine は無効化まで継続）。

本ハーネスには対応物が**語彙なしに**点在している：`agent/runtime.run_agent` は turn ループそのもの
（end_turn 停止＋max_turns backstop）・`agent monitor --file-issue` は proactive の前半円（監視→冪等起票）。
一方、AGENTS 第一原則「完了＝検証にすべて成功したときだけ・自己申告で完了にしない」を**エージェント実行
そのもの**へ機械化する仕組み＝「モデルの end_turn（完了した気になった）を評価器が検査する」停止ゲートは無い。
この分類を運用モデルとして正本化するか・抽象をどこに置くか・何を新規に実装するかを決める必要があった。

## 検討した選択肢
- A：agent プロファイル内に閉じる（core に置かない・loops は agent の実装詳細とする）。
- B：**core（`harness/loops.py`）に語彙だけ**（Trigger・StopDecision・StopCondition Protocol・stdlib のみ）を
  置き、実装はプロファイル側。新規実装は **goal-based 停止ゲート 1 点**（`agent/goal.py`＝`AGENT_METRICS`＋
  `eval.passes` の再利用・`run_agent` を丸ごと再利用して外側に巻く）。turn-based は既存の再解釈・
  time/proactive は雛形と runbook（実行基盤は利用者環境）に留める。
- C：core に loop 実行エンジン（scheduler・常駐 runner・キュー）を新設し 4 類型を一枚のランタイムで動かす。
- D：4 類型を最初から全部実装する（time の実行基盤・proactive の自動 fix まで一気に）。

## 決定と理由
**B を採用**（ビルド順は method.md A 節＝歩く骨組み：core 語彙＋agent goal ループだけ detailed・残りは outline）。
- **一般性は既に見えている**（DEC-0012 の「一般的・再発する形」）：ds の実験 sweep（閾値達成まで変種探索）・
  ops の retrain（schedule→関門合格で昇格＝EP-21）も trigger×stop×policy で書ける。だがプロファイル同士は
  import できない（DEC-0004）ため、共有語彙の置き場は core しかない。A はこの横展開を最初から塞ぐ。
- **C は再発明**：時間起動は cron・CI schedule・Claude 側 /loop・/schedule スキルが既にあり（DEC-0006/0008 の
  思想＝業界標準を再発明しない）、常駐ランタイムは core の軽さ（DEC-0013・stdlib 中心）と verify の決定性
  （DEC-0015・無ネットワーク）を壊す。ハーネスが持つべきは停止条件の**宣言と検査**であって実行基盤ではない
  （EP-21 の「テンプレ＋構造 lint＋導線」と同じ線引き）。
- **D は過剰**：4 類型のうち真に新規なのは goal-based だけ。turn-based は `run_agent` が既にその形・
  time/proactive は「読む側」（monitor・issues）が完成済みで、足りないのは起動の雛形と閉ループの後半円＝
  outline で十分。goal ゲートも新しい合否機構は作らず、既存の採点器レジストリ（`AGENT_METRICS`）と合否
  （`eval.passes`・fail closed・NaN 不合格）をそのまま門にする。
- **maker≠checker がループ内に入る**：goal-based は「作る側（モデルの end_turn）と確かめる側（宣言済み評価器）を
  分ける」という AGENTS 第 2 原則の実行時版。停止の権限をモデルの自己申告から評価器へ移す＝本ハーネスの
  完了規約と同型なので、運用モデルへの昇格に値する（DEC-0012 の即昇格）。
- 過剰設計の釘：`LoopSpec`・loop レジストリ・StopCondition の一般化（output: str 固定を外す）・core への
  `passes` 引き上げは**作らない**。2〜3 個目の消費（ds sweep 等）が現れた時に DEC-0012 で判断する。

## 影響（良い点・悪い点・これからやること）
- 良い点：「完了＝検証にすべて成功」の原則がエージェント実行そのものに機械化される（end_turn を疑う門）。
  既存部品（run_agent・monitor・issues・schedule 雛形）が 4 類型の語彙で位置づき、次の拡張の置き場が
  一意に決まる。verify は無ネットワークのまま（goal ループも dummy 台本＋`_cut_network` で検証・DEC-0015）。
- 悪い点：goal の質は評価器の質に依存する（骨組みの exact_match は答えが一意の場合に限る）→ 緩和：
  rubric/LLM-judge 採点器を T-0096 で足す（ゲートは metric 名しか見ない＝差し替えで届く）。max_cycles
  backstop があるため「満たすまで**絶対に**止めない」ではない → 意図的（黙って無限ループしない規律を優先）。
- これからやること：EP-23 T-0095（core 語彙＋goal ゲートの歩く骨組み・本 DEC の accepted 化・AGENTS へ 1 行）→
  T-0096（judge 化・宣言化）→ T-0097/T-0098（time/proactive の雛形と閉ループ後半円）→ T-0099/T-0120
  （ds/serve/ops への写像・ops は EP-21 着地後）。関連 [[DEC-0004]] [[DEC-0006]] [[DEC-0012]] [[DEC-0013]]
  [[DEC-0015]] [[DEC-0016]]。
