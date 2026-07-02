---
id: T-0009
kind: task
status: done
title: ディレクトリ再編（1リポジトリ＝1案件：projects/ を docs/ へ）＋決定記録
requirements: [REQ-003]
verified_by: [tests/test_structure.py]
depends_on: [T-0005, T-0006, T-0007, T-0008]
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0009 ディレクトリ再編＋決定記録

## 目的
1リポジトリ＝1案件の構成に寄せる。案件レベルの文書を `docs/`（charter・requirements・data・decisions・learnings）へ移し、
`projects/` の層を廃止する。参照（テンプレート・完了の定義・手順書・README）を新しい置き場に合わせ、
主要な決定を記録に残す。呼称・造語の残り（開発基盤に統一）も整える。

## 受け入れ基準
- `docs/charter.md`・`docs/requirements/`・`docs/data/`・`docs/decisions/`・`issues/`・`.harness/config.toml` が存在し、`projects/` が無い。
- 参照（README・DoD・テンプレート・スキル）が新しい置き場を指す。
- 主要な決定（1リポジトリ＝1案件と作業単位4種類、テーブル定義とデータの層）を決定記録に残す。
- `uv run verify` にすべて成功する。
