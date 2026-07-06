---
id: T-0078
kind: task
status: done
title: run_experiment の task 三値注釈（G6）＋analysis の多クラス OOF 対応（G10）
created: 2026-07-06
depends_on: [T-0074]
verified_by:
  - tests/test_ds_experiment.py::test_run_experiment_multiclass_task
  - tests/test_ds_analysis.py::test_segment_metrics_multiclass_argmax_accuracy_from_construction
  - tests/test_ds_analysis.py::test_worst_rows_multiclass_orders_by_true_class_proba
  - tests/test_ds_analysis.py::test_worst_rows_multiclass_rejects_out_of_range_labels
---
# T-0078 experiment / analysis の task 三値対応

## 背景（G6・G10）
- **G6**：`experiment.py` の `run_experiment(task:)` の型注釈が `Literal["classification","regression"]` の二値のまま
  （L34 付近の `Task`）。`ExperimentSpec.task` と `final_eval_on_holdout` は既に三値（binary|multiclass|regression）なのに
  取り残し＝ISS-0009 の残り。work/ は mypy 対象外なので静かに素通りしている。
- **G10**：`analysis.py` の `segment_metrics`/`worst_rows` が多クラス OOF（n×k proba）を受けられない（二値注釈＋|y−score| 前提）。
  多クラス champion の深掘りが部品でできない。

## 受け入れ基準
- G6：`Task` の語彙を三値（binary|multiclass|regression。既存の他モジュールと同じ Literal）に統一。run_experiment 本体が
  三値で正しく動く（既存の binary/regression 経路は不変・multiclass 経路が型で通る）。tests/ に multiclass を渡すテストを置き
  mypy strict が通ることを担保（work/ でなく tests/ で型を守る）。
- G10：`segment_metrics`/`worst_rows` が多クラス OOF（n×k の proba 行列）を受けたら argmax ラベルベースの指標（accuracy 等）で
  セグメント表・worst 行を出す。二値・回帰の既存挙動は不変（分岐で対応・fail-loud で未対応形状を弾かない）。

## 触ってよいファイル
`src/harness/ds/experiment.py`・`src/harness/ds/analysis.py`＋`tests/test_experiment*.py`・`tests/test_analysis*.py`（実在名は確認）。
`pipeline.py`/`eval.py`/`cv.py`/`eda.py`/`train.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- multiclass task で run_experiment（または型のみの経路）が通る・binary/regression が不変。
- 多クラス OOF（3 クラス・argmax が既知になる構成）で segment_metrics/worst_rows が argmax ラベル指標を返す。二値・回帰は不変。

## 独立レビュー（maker≠checker・差分のみ・実測）
CONFIRMED 欠陥なし。3 クラス構成で segment_metrics/worst_rows の argmax 指標を実測・二値/回帰は新旧 equals で不変を確認・
fail-loud 境界（次元/範囲/長さ）確認・変異 5/5 撃墜。Task 三値化は multiclass テストが mypy 型ガードとして実働。軽微 PLAUSIBLE 2 件
（worst_rows の長さ不一致が明示 ValueError でなく非対称・2 列 proba+multiclass の受理差）は完了を妨げず記録に留める。
