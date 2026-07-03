---
id: T-0031
kind: task
status: done
title: MODELS を ModelEntry(factory, task) 化・task 検査・data models に task 列
depends_on: [EP-10]
created: 2026-07-03
verified_by:
  - tests/test_ds_pipeline.py::test_build_model_task_mismatch
  - tests/test_catalog.py::test_models_have_docstrings_and_task
---
# T-0031 レジストリの形（T-A）

## 受け入れ基準
- `MODELS: dict[str, ModelEntry]`（factory＋task・METRICS と同型）。build_model に `task` 引数を足し、回帰モデル×
  分類 task を config 段階で ValueError（task=None は互換）。`data models` の出力に task 列。test_catalog 更新。
- 既存 2 kind（logreg/ridge）のまま verify 全緑。train.py 雛形は `build_model(..., task=task)` の 1 行のみ変更。

## 結果
実装・verify 緑。以降の T-0032（sklearn 一括）・T-0033（lightgbm 条件登録）・時系列はこの形の上に載る。
