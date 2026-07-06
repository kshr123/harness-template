---
id: T-0050
kind: task
status: done
title: schema の checks を pl.sql_expr で実評価（pandera 不採用・DEC-0011）
created: 2026-07-05
verified_by:
  - tests/test_ds_schema.py::test_validate_column_check_counts_violations
  - tests/test_ds_schema.py::test_validate_table_check_cross_column
  - tests/test_ds_schema.py::test_validate_check_null_is_not_violation
  - tests/test_ds_schema.py::test_validate_check_invalid_expression_does_not_crash
  - tests/test_ds_schema.py::test_validate_empty_checks_behaves_as_before
---
# T-0050 schema の checks を実評価

## 受け入れ基準
- `Column.checks`／`TableSchema.checks`（cross-column 含む）を `pl.sql_expr` で評価（依存ゼロ＝標準への委譲・再発明でない）。
  違反件数は `df.filter(~expr.fill_null(True)).height`＝**NULL は違反にしない**（別途 nullable が見る）。
- 不正・存在しない列を指す式は try/except で握って**落とさない**（検証全体を止めない・その式だけ無視して他を続ける）。
- `checks` が空なら従来と完全に同じ挙動（回帰なし）。YAML を正本に保つ枠は不変（pandera 不採用＝DEC-0011）。

## 結果
実装（`_eval_checks`・sql_expr・NULL 非違反・例外握り）・テスト先書き（列 check の違反計数・cross-column・
NULL 非違反・不正式で無停止・空 checks の後方互換の5本）・独立レビュー・verify 緑で完了。
`docs/ideal-build-plan-2026-07-05.md` Wave 2・DEC-0011。ISS-0010 消化。
