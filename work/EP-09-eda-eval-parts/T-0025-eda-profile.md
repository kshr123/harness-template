---
id: T-0025
kind: task
status: done
title: eda.profile と data profile・eda スキル・marimo ビュー
depends_on: [T-0024]
created: 2026-07-03
verified_by:
  - tests/test_ds_eda.py::test_profile_nulls_and_duplicates
  - tests/test_ds_eda.py::test_target_summary_classification_ratios
  - tests/test_ds_eda.py::test_cli_profile_outputs_yaml
  - tests/test_ds_eda.py::test_notebook_is_thin_view
  - tests/test_e2e_eda_notebook.py::test_eda_notebook_runs_headless
---
# T-0025 eda.profile と入口（CLI・スキル・marimo ビュー）

## 受け入れ基準
- `eda.profile`（列概要・数値統計・カテゴリ最頻・重複行数・to_dict）と `eda.target_summary`（分類=比率・回帰=統計量）。
  集計は polars 委譲・正本は構造化レポート（YAML に落ちる）。
- 入口（DEC-0009）：`uv run data profile <table_id> [--target --task]`（YAML 出力）・**eda スキル新設**
  （investigation kind との接続・してはいけないこと）。
- **人のビュー**：`notebooks/eda.py`（marimo の薄い雛形・同じ関数を呼ぶだけ）。`marimo`・`altair` を ds extra へ。
  腐り防止＝e2e スモークが `python notebooks/eda.py` をヘッドレス実行（終了コード0のみ・図は比較しない）。
  ビューが薄い（sklearn を import しない）ことを unit の構造検査で担保。

## 結果
実装・独立レビュー・verify 緑・DESIGN §5 手順2 完了。EDA も端まで一巡（store→レポート→YAML／人は marimo）。
compare/psi/drift・analysis・回帰経路は T-0026 以降。
