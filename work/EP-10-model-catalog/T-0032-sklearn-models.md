---
id: T-0032
kind: task
status: done
title: sklearn モデル一括（knn/tree/random_forest/hist_gb・lasso/elasticnet/rf_reg/hist_gb_reg）
depends_on: [T-0031]
created: 2026-07-03
verified_by:
  - tests/test_ds_models_catalog.py::test_nonlinear_models_beat_linear_on_xor
  - tests/test_ds_models_catalog.py::test_quantile_objective_shifts_predictions
  - tests/test_ds_models_catalog.py::test_lasso_l1_zeroes_coefficients_as_alpha_grows
---
# T-0032 sklearn モデル一括（T-B）

## 受け入れ基準
- MODELS に 8 kind 追加（分類 knn/tree/random_forest/hist_gb・回帰 lasso/elasticnet/random_forest_reg/hist_gb_reg）。
  全部「使う」（sklearn 素通し・自作ゼロ）。安全既定は seed 配線のみ（性能の好みは焼かない）。docstring に用途・主ハイパラ・目的関数の変え方。
- 目的関数は文字列 params 素通し（criterion/loss/quantile）。experiment スキルにモデル選びの目安＋目的関数変更例。
- 期待値は構成から導出（XOR で木＞線形・quantile 0.9＞0.1・L1 で係数減）。`data models` に 10 kind。

## 結果
実装・verify 緑。分類 5・回帰 5＝10 kind（＋ lightgbm 系は T-0033 で条件登録）。
