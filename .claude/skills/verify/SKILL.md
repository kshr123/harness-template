---
name: verify
description: 変更の完了を判定する際に自動参照。共通の検証コマンドを緑になるまで回し、テスト出力などの証拠を示して done を確定する。テスト・検証・完了・CI の語で発火。
---

# verify（完了判定）

## 共通の検証コマンド（実体は uv。make は使わない）
- `uv run verify` … check full（孤児検出＋STATUS 一致＋ruff＋mypy＋pytest）
- 段階：`uv run check --level fast|standard|full`

## 手順
1. `uv run status` で STATUS.md を最新化する（タスクを変更したら必ず）。
2. `uv run verify` を実行し、赤なら理由を読む。
3. 実装だけ直して緑まで回す（テストは緩めない・消さない）。
4. 緑の出力（証拠）を示す。緑になって初めて done。

## 禁止事項
- 証拠（緑の出力）なしに done と宣言してはならない。
- テストを改変・削除して緑にしてはならない。
- `tasks/STATUS.md` を手編集してはならない（生成物）。
