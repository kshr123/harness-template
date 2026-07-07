---
id: T-0120
kind: task
status: todo
title: ops retrain 閉ループを time+goal 合成として位置づける（EP-21 着地後）
created: 2026-07-07
depends_on: [T-0095, EP-21]
verified_by: []
---
# T-0120 ops retrain 閉ループの loops 位置づけ（outline・later・**EP-21 着地後**）

## 狙い
EP-21（`harness.ops`）の継続学習（CT）雛形＝「schedule→experiment→`data monitor`→閾値を満たせば promote」は、
loops 語彙では **time-based（起動）× goal-based（停止＝関門合格）** の合成そのもの。EP-21 が着地したら、
retrain 雛形とその文書を loops 語彙（trigger×stop×policy）へ位置づけ、EP-23 の写像表を閉じる。

## 受け入れ基準の骨子（着手時に detailed 化・EP-21 の実装実名で書き直す）
- retrain 雛形の trigger（schedule）・stop（`promote_model` の絶対/相対関門＝goal ゲートの ds 版と等価）・
  policy（何を再学習するか）を docs（EP-21 の正本 docs/ops.md）に 1 節。
- goal ゲート（agent）と promote 関門（ds/ops）の**同型性**を写像表に固定（実装は共有しない＝プロファイル
  境界・DEC-0004。共有したくなったら T-0099 の DEC-0012 判断に合流）。

## 制約（並行作業との衝突禁止）
**EP-21 が別 worktree で進行中。着地（main へのマージ）まで `src/harness/ops/**`・`docs/ops.md` には
一切触れない。**本タスクは depends_on: [EP-21] で待つ（着手時に EP-21 の実装実名で detailed 化する）。
