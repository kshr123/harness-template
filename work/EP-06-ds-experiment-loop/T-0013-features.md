---
id: T-0013
kind: task
status: done
title: 特徴量作成の枠組み features.py（BaseBlock の考え方・sklearn 互換）
requirements: [REQ-004]
depends_on: [T-0014]
verified_by:
  - tests/test_ds_features.py::test_interactions_computes_products
  - tests/test_ds_features.py::test_feature_pipeline_composes_and_describes
  - tests/test_ds_features.py::test_feature_pipeline_rejects_duplicate_output_columns
  - tests/test_ds_features_integration.py::test_feature_pipeline_runs_through_cv
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0013 特徴量作成の枠組み features.py

## 目的
モデルに依らない特徴量エンジニアリングの枠組み（BaseBlock の考え方）。sklearn 互換の transformer にして
モデルと一緒に 1 本の `Pipeline` に入れ、cv.run_cv が fold ごとに clone→train で fit するので
漏れ防止は構造で担保される。設計は DESIGN.md R。DEC-0007。

## 受け入れ基準（テスト先行で）
- `FeatureBlock`（BaseEstimator+TransformerMixin・polars 入出力・`feature_names`・`get_feature_names_out`）。
- 例ブロック `Interactions(pairs)`（`a_x_b`）・`Columns(columns)`（素通し）。**個別の標準変換（StandardScaler 等）は作らない**（sklearn を直接使う）。
- `FeaturePipeline`（ブロックを横に束ねる薄い sklearn 互換 transformer・`describe`・`feature_names`）。検査＝出力行数不変・出力列名の重複禁止。
- 統合：`Pipeline([("features", FeaturePipeline([...])), ("model", LogisticRegression())])` を run_cv に通し、OOF 全行・妥当な AUC（一気通貫の結線）。
- `uv run verify` 全成功。
