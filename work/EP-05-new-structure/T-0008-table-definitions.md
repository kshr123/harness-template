---
id: T-0008
kind: task
status: done
title: テーブル定義YAML＋検証（data-lint・保存＝検証済みだけ）
requirements: [REQ-003]
verified_by: [tests/test_ds_schema.py]
depends_on: [T-0005]
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0008 テーブル定義YAML＋検証

## 目的
データの構造・意味を宣言的なYAML（正本）で持ち、静的検査（data-lint）と実データ検証を正本から組み立てる。
保存の入口 `save(df, table_id)` は定義に照らして検証し、通ったデータだけを書く。split 層は再書き込みを拒否する。
検証の実行器は polars で実装し、より本格的な検証が要る案件は同じ正本から差し替えられる。

## 受け入れ基準
- `docs/data/<id>.yaml`（共有）と `work/<単位ID>/data/<id>.yaml`（実験スコープ）を読み、型を検証する。
- `data-lint`（ID重複・型名・processed/split の系譜・入力の存在・越境参照）が `uv run verify` に含まれ、失敗を検出する。
- `save` は定義違反のデータを拒否し、通ったデータを parquet に書きマニフェストを残す。split は再書き込み不可。
- `uv run verify` にすべて成功する。
