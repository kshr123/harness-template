---
id: T-0001
status: done
priority: high
epic: EP-01
requirements: [REQ-001]
owner: sakurada
---
# T-0001 プロジェクト管理の CLI（status / task-lint / verify）

## 目的
タスクと WBS から STATUS を自動算出し、参照エラーを見つけ、共通の検証コマンドで合否（成功/失敗）を返す。

## 受け入れ基準
- `uv run status` が tasks/STATUS.md を作る。
- `uv run task-lint` が、存在しないエピックを指すタスクだけ失敗にする（未分解・未割り当ては許容）。
- `uv run verify` にすべて成功する。

## 細かい手順（小さいものは本文のチェックリスト）
- [x] models（Task / Epic の型）
- [x] pm（読み込み・STATUS 自動算出・参照チェック）
- [x] checks（共通の検証コマンド）
- [x] cli（typer 入口）
