---
id: T-0021
kind: task
status: done
title: 部品カタログの出口（uv run data blocks / data encoders＋説明文必須）
requirements: [REQ-004]
depends_on: [T-0018, T-0020]
verified_by:
  - tests/test_catalog.py::test_blocks_have_docstrings
  - tests/test_catalog.py::test_encoders_have_docstrings
  - tests/test_catalog.py::test_catalog_commands_run
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0021 部品カタログの出口

## 目的
`BLOCKS`/`ENCODERS`（機械可読カタログ）を、エージェントが元コードを読まず 1 コマンドで発見できる出口にする。

## 受け入れ基準（テスト先行で）
- `uv run data blocks`（BLOCKS から生成・kind／引数／説明文1行）・`uv run data encoders`（ENCODERS から生成）。手書きの一覧を作らない（生成ビュー）。
- pipeline.py の工場6つに docstring（1行目＝何をするか・config の書き方）。ブロックは docstring 済み。
- `tests/test_catalog.py`：レジストリ全項目に docstring がある（無い＝カタログに載れない＝入口欠落）・一覧コマンドが例外なく走る。
- `uv run verify` 全成功。
