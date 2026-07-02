---
id: T-0002
status: todo
priority: medium
epic: EP-01
requirements: [REQ-001]
dependencies: [T-0001]
owner: sakurada
---
# T-0002 CI とフック（pre-commit / GitHub Actions）

## 目的
ローカルと CI が同じ共通の検証コマンド（uv run verify）を叩き、完了の定義を一致させる。

## 受け入れ基準
- `uvx pre-commit run --all-files` が通る。
- CI（.github/workflows/ci.yaml）が uv run verify を実行する。
