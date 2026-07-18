---
id: T-0227
kind: task
status: done
title: リーク検査の fail-open を塞ぐ（role を既知語彙に固定＋未分類の派生テーブルも target 列を検査）
created: 2026-07-18
closed: 2026-07-18
depends_on: []
verified_by:
  - tests/test_ds_schema.py::test_unknown_role_is_rejected_at_model_validation
  - tests/test_ds_schema.py::test_data_lint_surfaces_unknown_role
  - tests/test_ds_schema.py::test_validate_fires_target_leak_on_unclassified_processed_table
  - tests/test_ds_schema.py::test_validate_unclassified_table_keeps_its_own_target
  - tests/test_ds_schema.py::test_validate_unclassified_raw_table_does_not_fire
  - tests/test_ds_schema.py::test_save_fails_closed_when_any_schema_is_invalid
---
## 独立レビュー（fable・maker≠checker）で見つかった欠陥と対処
- **H1（直した）**：KNOWN_ROLES 固定が**新しい** fail-open を生んでいた。ラベルの出所テーブルの role が
  綴り違いだと load_schemas が黙ってそのテーブルを落とし、target_column が禁止集合から抜け、目的変数を
  載せた特徴量テーブルが保存できてしまう（`store.save` は problems 無しで load していた）。→ `store.save` を
  fail-closed に：定義の読み込みに error がある間は保存しない（`test_save_fails_closed_when_any_schema_is_invalid`）。
- **M1（直した）**：role 未設定の枝のエラー文言が「特徴量テーブル…ID 列」と誤誘導していた。枝ごとに hint を分けた。
- **M2（直した）**：`test_data_lint_surfaces_unknown_role` が lineage 欠落 error で空振り合格しえた。raw 層＋
  「テーブル定義が不正」への一致に締めた。
- **M3（直した＝正直化）**：docstring が「残るのは分類し忘れだけ」と過大主張。既知だが誤った role
  （feature に cleaned を付ける等）は検査を通り抜ける＝role を軸にする設計上の限界を docstring に明記。
- L2（据え置き）：target 名の scope 跨ぎ衝突は fail-closed 寄りで実害なし・リポ内に該当なし。記録のみ。
# T-0227 リーク検査の fail-open を塞ぐ

## 事象（塞いだ穴）
目的変数の同乗（リークの中でも最悪の形＝良い指標つきで出荷）を止める `schema.validate` の検査が、
`schema.role == "feature"`（自由記述の文字列との完全一致）でだけ発火していた。role は人が探すための
自由欄なので、`role="features"`（綴り違い）・`role="feature_store"`（亜種）・role 未設定のいずれかで
安全検査が黙って素通りする＝fail-open。目的（黙って間違わない）に反する。

## 直し方（保証(a)＋fail-closed の 2 段）
1. **role を既知語彙に固定**：`KNOWN_ROLES = {raw, cleaned, feature, split, prediction, evaluation}`。
   pydantic の field_validator で未知 role を load 時に ValidationError にする＝綴り違い・亜種を**構文で
   不可能にする**（保証(a)）。data_lint が未知 role を error として表に出す。リポ内の実 YAML の role は
   cleaned/prediction/split の 3 種だけで、全て語彙内＝固定しても既存は壊れない（着手前に実測で確認）。
2. **未分類の派生テーブルも検査**：role 未設定（None）の processed/split テーブルが他テーブルの目的変数を
   載せていたら発火（target 列だけ狙い撃ち。ID 列は派生に正当に相乗りするので対象外）。自分自身が宣言した
   target_column は除く。これで「分類し忘れ」も塞ぐ。raw 層は学習前の X・y 同居が正当なので発火させない。

これで報告された 3 つの fail-open（綴り違い・亜種・未設定）がすべて閉じる。

## 受け入れ基準（満たした・verify 緑）
- 未知 role は model_validate で ValidationError（`test_unknown_role_is_rejected_at_model_validation`）。
- 未知 role の YAML を data_lint が error にする（`test_data_lint_surfaces_unknown_role`）。
- role 未設定の processed テーブルの target 同乗を検出（`test_validate_fires_target_leak_on_unclassified_processed_table`）。
- 自分の target は違反にしない（`test_validate_unclassified_table_keeps_its_own_target`）。
- raw 層は発火させない（`test_validate_unclassified_raw_table_does_not_fire`）。
