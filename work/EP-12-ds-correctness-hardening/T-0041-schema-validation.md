---
id: T-0041
kind: task
status: done
title: schema 検証の穴（Datetime 型・NaN・複合鍵・null 一意）
created: 2026-07-05
verified_by:
  - tests/test_ds_schema.py::test_validate_datetime_and_duration_dtypes
  - tests/test_ds_schema.py::test_validate_nan_violates_nullable_false
  - tests/test_ds_schema.py::test_validate_range_fires_even_with_nan
  - tests/test_ds_schema.py::test_validate_composite_primary_key
  - tests/test_ds_schema.py::test_validate_unique_allows_multiple_nulls
---
# T-0041 schema 検証の穴

## 受け入れ基準
- **Datetime/Duration 型が保存できる**：`validate` は型を構造比較（`series.dtype == getattr(pl, col.dtype)`）で見る。
  `str(dtype)` の `Datetime(time_unit=…)` 表記に依存しない。`data_lint`/`POLARS_DTYPES` は変更しない。
- **NaN をすり抜けさせない**：float 列で `nullable=false` かつ NaN があれば違反。range 検査は `fill_nan(None)` 後に測る。
- **複合 primary_key のデータ一意性**を `validate` で検査（重複キー行を違反にする）。
- **一意判定は非 null 上で**行う（null が 1 個でも 2 個でも通り、真の重複だけ落とす）。

## 結果
実装・テスト先書き（pre-fix で 4 件失敗を確認）・独立レビュー・verify 緑で完了予定。`docs/ds-review-2026-07-05.md` 参照。
検証の高度化（checks 評価・pandera 導出）は ISS-0010 で別途。
