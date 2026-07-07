---
id: T-0098
kind: task
status: todo
title: proactive 閉ループの後半円（issue→修正→検証緑で close・maker≠checker を保つ）
created: 2026-07-07
depends_on: [T-0097]
verified_by: []
---
# T-0098 proactive triage 閉ループ（outline・later）

## 狙い
blog の proactive（schedule＋goal の合成。各タスクは goal 達成で退場・routine は無効化まで継続）を閉じる。
前半円（監視→冪等起票）は `agent monitor --file-issue` で実装済み。後半円＝**起票された issue を goal として
拾い（例：「`uv run verify` 緑かつ non_end_turn_rate が安定帯」）、修正し、達成したら close して退場**する
流れを loops 語彙で設計する。

## 受け入れ基準の骨子（着手時に detailed 化）
- issue → goal の写像（issue frontmatter に成功基準を書ける形＝goal 宣言 T-0096 の再利用）。
- **自動 fix の適用はガード付き**：修正の作成と合否判定を分離（maker≠checker＝AGENTS 第 2 原則）。
  自動で許すのは「独立レビュー＋verify 緑」を通ったものだけ・人の承認点をどこに置くかを先に固める。
- routine の停止＝無効化の手順（T-0097 の runbook に合流）。close の冪等（同 issue を二重に閉じない）。

## やらないこと
承認無しの自動 merge・監視を門番化すること（monitor は exit 0 のまま＝起票は副作用、の既存規律を壊さない）。
