---
id: T-0205
kind: task
status: done
title: 目的変数・ID 列が特徴量テーブルに同乗したら ValueError（リークの発生源を塞ぐ）
created: 2026-07-11
closed: 2026-07-11
depends_on: []
verified_by:
  - tests/test_ds_schema.py::test_forbidden_feature_columns_from_declarations
  - tests/test_ds_schema.py::test_validate_rejects_target_leak_into_feature_table
  - tests/test_ds_schema.py::test_validate_feature_table_allows_own_primary_key
  - tests/test_ds_schema.py::test_validate_leak_check_only_for_feature_role
  - tests/test_ds_schema.py::test_save_rejects_target_leak_into_feature_table
  - tests/test_ds_schema.py::test_data_lint_target_column_must_exist
---
# T-0205 目的変数の同乗を発生源で塞ぐ

## 何が問題か（実測で確認）
`schema.validate` は宣言外の列を検査しないので、目的変数のコピーが features テーブルに同乗して保存できる。
これはリークの中でも最悪の形——**良い指標つきで出荷される**。本番で崩壊するまで誰も気づかない。

## 当初設計の訂正（独立レビュー 2026-07-10）
当初は「宣言外の列を既定 error」にする案だったが**効かない**：one-hot 等のエンコーダ由来の列は値に依存して
動的に増えるので、特徴量テーブルの全列宣言は実務的に不可能。そのテーブルだけ `allow_extra: true` にする
ことになり、**標的（目的変数の同乗）が起きる場所でちょうど検査が無効化される**。

正しい形は、発生源が**有限に列挙できる**集合だけを狙い撃つこと：目的変数の列名・ID 列名が特徴量テーブルに
現れたら `ValueError`。宣言済みの名前との照合なので、対象集合は構文（YAML の宣言）から機械的に導ける＝(b)。

## やったこと
- `TableSchema.target_column`（このテーブルが持つ目的変数の列名。宣言はラベルの出所側の 1 か所だけ）を追加。
  `data_lint` で target_column が実在の列かを検査。
- `forbidden_feature_columns(schemas, own_primary_key=…)`：全テーブルの `target_column` と `primary_key` を
  集めた集合から、特徴量テーブル自身の primary_key（正当な結合キー）を除いた集合を返す。
- `validate(df, schema, all_schemas=…)`：`schema.role == "feature"` のとき、禁止列が df に同乗していれば違反。
- `store.save` は `load_schemas` の全定義を `all_schemas` として渡す（validate の唯一の呼び手なので、
  ここを通す保存だけが検査される）。EDA の中間テーブルは save を通らないので誤検出しない（実測）。

## 受け入れ基準
- 目的変数を宣言した名前の列が feature テーブルに同乗 → `save` が `ValueError`（先に赤くなるのを確認）。
- 特徴量テーブル自身の primary_key は禁止しない（自分の結合キーは正当）。
- role が "feature" でないテーブル、`all_schemas` を渡さない呼びには影響しない。
- `uv run verify` 全成功。
