---
id: T-0051
kind: task
status: done
title: 多クラス分類の経路（task=binary|multiclass|regression・metric/_predict/evaluate を拡張）
created: 2026-07-06
depends_on: [T-0048]
verified_by:
  - tests/test_ds_eval.py::test_evaluate_multiclass_perfect_from_construction
  - tests/test_ds_eval.py::test_evaluate_multiclass_random_near_chance
  - tests/test_ds_eval.py::test_evaluate_multiclass_rejects_mismatched_metrics_and_shape
  - tests/test_ds_cv.py::test_predict_multiclass_returns_full_proba_matrix
  - tests/test_ds_cv.py::test_predict_multiclass_requires_contiguous_labels
  - tests/test_ds_cv.py::test_run_cv_multiclass_oof_and_macro_f1
  - tests/test_ds_pipeline.py::test_build_model_multiclass_uses_classification_models
---
# T-0051 多クラス分類の経路

## 受け入れ基準
- 課題語彙を `binary | multiclass | regression` に拡張（現行は分類＝二値のみ）。`MetricEntry.task` は
  `classification|regression` のままでも、`tasks` は測れる課題の並び（binary/multiclass/regression）で表す。
- `metric_fn_for`／`evaluate`／`passes` が多クラスに対応（macro 平均系＝macro-f1・macro-precision・macro-recall・
  accuracy・log_loss(multi)・roc_auc は ovr/ovo マクロ。すべて sklearn 素通し・average 引数で。手書きしない）。
- `cv._predict` は多クラスで proba を「クラス数分の列」で返す（二値の陽性列固定を分岐）。回帰は value のまま。
- 二値・回帰の既存挙動は不変（回帰なし）。多クラスは新経路として追加。

## 検査（テスト先書き・構成から期待を導く）
- 3 クラスの小さな合成データ（クラス毎に分離した平均のガウス）で、macro-f1 が完全分離では 1.0 近傍・
  でたらめ予測では 1/クラス数近傍に落ちる（構成から導ける境界で確認）。
- `_predict(proba)` の戻りが (n, n_classes) 形で各行が和 1。二値・回帰の既存テストが不変で緑。
- `evaluate` に multiclass 指標を渡すと macro 値が返る。二値指標を multiclass に混ぜたら ValueError（task 不一致）。

## 触ってよいファイル
`src/harness/ds/eval.py`・`src/harness/ds/cv.py`・`src/harness/ds/pipeline.py`（`_predict` ガード・task 受け渡し）・
`src/harness/registry.py`（MetricEntry の tasks 語彙。既存 API 破壊は不可）と対応テスト。
`models.py`・`tests/test_ds_models.py` は触らない（別レビュー進行中）。

## 独立レビュー（2026-07-06・maker≠checker）
実測で確認。important 1 件（IS-1）を修正：`cv._predict` の多クラス分岐が `classes_` の連番（0..k-1）を検査せず、
ラベル {2,5,9} や fold 間クラス集合ズレで**指標が黙って誤る**穴。二値のラベル 1 検査と対に `np.array_equal(classes,
arange)` を追加（連番でなければ ValueError・回帰テスト追加）。minor：`evaluate_multiclass` の 2 列拒否を明示
（IS-3・macro_roc_auc の不透明エラー回避）、valid クラス欠けで macro_roc_auc が nan になる旨を docstring に明記
（IS-2・passes は NaN で fail-closed）。IS-4（単一クラス fold の退化・層化前提で回避）・IS-5（カタログ tasks 列）は
minor として据え置き（IS-5 は Wave 3 のカタログ拡張で拾う）。

## 結果
実装・独立レビュー（IS-1 反映）・verify 緑で done。ISS-0009 を消化＝promoted_to。
