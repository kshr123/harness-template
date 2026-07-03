---
id: T-0028
kind: task
status: done
title: 回帰経路（run_experiment task=・MODELS ridge）と run_cv の int 丸め修正
depends_on: [T-0024, T-0027]
created: 2026-07-03
verified_by:
  - tests/test_ds_experiment_regression.py::test_regression_path_runs_and_passes
---
# T-0028 回帰経路

## 受け入れ基準
- `run_experiment(task="regression")` が指標（evaluate_regression）と予測（value）を task から切り替える。
- `MODELS` に `ridge`（sklearn.linear_model.Ridge）を追加＝回帰指標を死蔵にしない（DEC-0009）。E-0001 は無変更。
- 統合テスト：y=2·x1＋雑音(std 0.1) で ridge の OOF rmse <= 0.2・passes({rmse:0.2})・残差の偏り小。

## 見つけた不具合と修正
- `run_cv` が metric_fn へ渡す前に y_true を `.astype(np.int_)` していた（分類前提の丸め）。回帰では目的変数（連続値）が
  0 に切り捨てられ rmse が壊れる。**int 化を run_cv から eval.evaluate（分類側）へ移動**し、run_cv は元 dtype のまま
  渡すようにした（回帰は float のまま・分類は evaluate が int に揃える）。`MetricFn` の型も緩和。

## 結果
実装・verify 緑・DESIGN §1-2 の task 配線＋§9 の回帰まで完了。分類/回帰の両方を扱える土台になった。
train.py の回帰対応（後処理の分岐）は最初の回帰実験でコピー元から派生（Rule of Three）。
