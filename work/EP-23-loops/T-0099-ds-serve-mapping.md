---
id: T-0099
kind: task
status: todo
title: ds/serve への loops 語彙の写像（sweep の goal 化の判断点・serve は loop でない旨の正本化）
created: 2026-07-07
depends_on: [T-0095]
verified_by: []
---
# T-0099 ds/serve への loops 語彙の写像（outline・later）

## 狙い
loops 語彙（trigger×stop×policy）を ds/serve に写像し、**どこまで適用し・どこは適用しないか**を正本化する。
ds の実験 sweep（「閾値達成（`passes`）まで変種探索」）は goal-based の 2 個目の消費候補＝
`loops.StopCondition` を一般化するかの **DEC-0012 判断点**。serve はリクエスト駆動（1 呼び 1 応答）＝
loop ではなく、**適用しない判断**も写像表に残す（無理に統一しない）。

## 受け入れ基準の骨子（着手時に detailed 化）
- ds：sweep を goal 語彙で書くと何が良くなるか（自動打ち切り？）を実需要で判断。要るなら StopCondition の
  引数一般化（output: str 固定を外す）を DEC で決めてから（プロファイル境界は core 経由のまま・DEC-0004）。
- serve：docs/serve.md か docs/agent.md の loops 節に「serve は loop でない」1 段落（理由：レイテンシ契約と
  評価器ゲートの衝突）。
- 写像表（EP-23 item.md）を実装の実名で更新。

## やらないこと
実需要の無い一般化（消費者が現れる前に StopCondition を広げない＝YAGNI・DEC-0012）。
