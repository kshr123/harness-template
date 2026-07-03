---
id: T-0027
kind: task
status: done
title: analysis.py（セグメント・誤差行・並べ替え重要度・残差）と深掘り導線
depends_on: [T-0024]
created: 2026-07-03
verified_by:
  - tests/test_ds_analysis.py::test_segment_metrics_classification
  - tests/test_ds_analysis.py::test_segment_metrics_regression_residual_mean
  - tests/test_ds_analysis.py::test_residual_summary_from_construction
  - tests/test_ds_analysis_integration.py::test_permutation_importance_zero_for_unused_column
  - tests/test_ds_analysis_integration.py::test_cv_permutation_importance_runs_over_folds
---
# T-0027 OOF 予測の深掘り（analysis.py）

## 受け入れ基準
- `analysis`：segment_metrics（セグメント別指標・回帰は residual_mean）／worst_rows（誤差の大きい行）／
  permutation_importance（並べ替え重要度・悪化量を向きで統一・sklearn.inspection は polars 非対応で自作）／
  cv_permutation_importance（fold の valid だけで＝OOF 規律を引数で強制）／residual_summary（回帰の残差）。
- 指標計算は eval（METRICS）へ委譲。入口：experiment スキルに「結果の深掘り」節（すべて OOF で）。
- 期待値は構成から導出（未使用列の重要度==0.0 厳密・残差 mean 等）。

## 結果
実装・verify 緑・DESIGN §1-3＋§9-3 完了。エラー分析（どこで・どんな行で・どの列で外すか）が部品化。
