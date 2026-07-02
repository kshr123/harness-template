---
id: T-0002
kind: task
status: todo
title: CI とコミット前検査
requirements: [REQ-001]
depends_on: [T-0001]
owner: sakurada
---
# T-0002 CI とコミット前検査

## 目的
ローカルと CI が同じ共通の検証コマンド（uv run verify）を使い、完了の定義を一致させる。

## 受け入れ基準
- `uvx pre-commit run --all-files` にすべて成功する。
- CI（.github/workflows/ci.yaml）が uv run verify を実行する。
