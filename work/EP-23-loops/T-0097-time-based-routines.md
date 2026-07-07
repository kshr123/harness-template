---
id: T-0097
kind: task
status: todo
title: time-based loop の導線（monitor 定期実行の runbook＋schedule 雛形・実行基盤は利用者環境）
created: 2026-07-07
depends_on: [T-0095, T-0093]
verified_by: []
---
# T-0097 time-based loop の導線（outline・soon）

## 狙い
blog の time-based（時間間隔で起動・cancel/無効化で停止）を、**実行基盤を作らずに**運用へ落とす：
読む側（`agent monitor`・`data monitor`）は完成済みなので、**起動（trigger）を時間に接続する雛形と runbook**
だけを足す。実行基盤（cron・CI schedule・Claude 側 /loop・/schedule スキル）は利用者環境に委ねる
（EP-21 の CI テンプレと同じ「テンプレ＋構造 lint＋導線」の思想・DEC-0006/0008 の再発明回避）。

## 受け入れ基準の骨子（着手時に detailed 化）
- `templates/` に schedule 雛形（例：GitHub Actions schedule → `uv run agent monitor --file-issue`）。
  雛形の構造検査は deploy_lint/ci_lint と同型（実行しない・EP-21 の ci_lint が着地していれば流用を検討）。
- `docs/agent.md` に runbook 節：**stop＝cancel/無効化**をどこで行うか（workflow の disable・スキルの解除）を
  明記（「止め方の無い routine を作らない」＝blog の stop-condition 規律）。
- Claude 側 /loop・/schedule スキルへの導線 1〜2 行（リポ内の正本は docs・スキルは導くだけ）。

## やらないこと
常駐デーモン・自前 cron・リポ内での実 schedule 実行（verify は時間起動を含まない＝無ネットワーク・決定性の維持）。
