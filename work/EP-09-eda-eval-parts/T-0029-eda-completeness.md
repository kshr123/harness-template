---
id: T-0029
kind: task
status: done
title: EDA 完全性（外れ値・品質フラグ・欠損パターン・重複列・カテゴリ×目的）
depends_on: [T-0025]
created: 2026-07-03
verified_by:
  - tests/test_ds_eda.py::test_profile_numeric_skew_and_iqr_outliers
  - tests/test_ds_eda.py::test_profile_flags
  - tests/test_ds_eda.py::test_missing_patterns
  - tests/test_ds_eda.py::test_duplicate_columns
  - tests/test_ds_eda.py::test_category_target_summary
---
# T-0029 EDA 完全性スイープ（DESIGN §9-1）

## 受け入れ基準
- profile.numeric に skew/kurtosis（polars 素通し）・IQR 外れ値（iqr_lower/upper・n_outliers・outlier_ratio）を追加。
- TableProfile に datetime（日時列の期間）・flags（all_null/constant/quasi_constant/id_like）を追加（to_dict キー末尾）。
- 独立関数：missing_patterns（欠損の同時発生）・duplicate_columns（同一内容の列ペア・eq_missing）・
  category_target_summary（カテゴリ別の目的率/平均・リーク疑いの読み口）。
- 入口：`data profile` の出力キーに追加（新 CLI なし）・marimo にセル追加・eda スキル手順2更新。additive（既存の数値期待値は不変）。

## 結果
実装・verify 緑・DESIGN §9-1 完了。テーブル品質の点検が 1 コマンド（data profile）に集約。
