---
id: T-0026
kind: task
status: done
title: 相関・train/test 比較・PSI・分布差 AUC と data compare
depends_on: [T-0025]
created: 2026-07-03
verified_by:
  - tests/test_ds_eda.py::test_correlations_and_constant_column
  - tests/test_ds_eda.py::test_psi_categorical_known_value
  - tests/test_ds_eda.py::test_compare_numeric_and_categorical
  - tests/test_ds_eda_integration.py::test_drift_auc_detects_shift
  - tests/test_ds_eda_integration.py::test_drift_auc_half_when_indistinguishable
---
# T-0026 相関・比較・PSI・分布差 AUC

## 受け入れ基準
- `eda`：correlations／high_correlation_pairs／compare（train/test 統計・カテゴリの共通/固有・PSI）／psi
  （数値=train 分位のビン境界・カテゴリ=train カテゴリ＋その他）／drift_auc（build_estimator＋run_cv＋eval の合成・
  目的変数を使わない）。リーク禁止は API の形（2 表を別々に集計）。
- 入口：`uv run data compare <train> <test> [--auc]`＋marimo に比較セル（同じ関数を呼ぶだけ）＋eda スキル手順3更新。
- 期待値は構成から導出（相関 1.0/-1.0/定数 0・PSI 手計算値・分離で AUC≥0.95・定数で AUC=0.5）。

## 結果
実装・verify 緑・DESIGN §5 手順3 完了。EDA の train/test 比較まで一巡。
