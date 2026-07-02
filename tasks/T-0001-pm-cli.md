---
id: T-0001
status: done
priority: high
epic: EP-01
requirements: [REQ-001]
owner: sakurada
---
# T-0001 PM層 CLI（status / task-lint / verify）

## 目的
タスクと WBS から STATUS を導出し、孤児を検出し、共通の検証コマンドで緑/赤を返す。

## 受け入れ基準
- `uv run status` が tasks/STATUS.md を生成する。
- `uv run task-lint` が真の孤児だけ赤にする（outline・epic: none は許容）。
- `uv run verify` が緑。

## サブタスク（小さいものは本文チェックリスト＝方式C）
- [x] models（Task / Epic の型）
- [x] pm（読み込み・STATUS 導出・孤児検出）
- [x] checks（共通の検証コマンド）
- [x] cli（typer 入口）
