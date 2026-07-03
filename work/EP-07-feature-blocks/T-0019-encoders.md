---
id: T-0019
kind: task
status: done
title: エンコード系ブロックの引き直し（MultiHot/TargetAggregate/CombineKeys＋契約是正）
requirements: [REQ-004]
depends_on: [T-0018]
verified_by:
  - tests/test_ds_features.py::test_multihot_min_count_unknown_and_null
  - tests/test_ds_features.py::test_target_aggregate_fit_transform_is_out_of_fold
  - tests/test_ds_features.py::test_target_aggregate_rejects_mean_and_missing_y
  - tests/test_ds_features.py::test_feature_pipeline_fit_transform_delegates_oof
  - tests/test_ds_features_integration.py::test_target_aggregate_fits_on_train_fold_only
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0019 エンコード系ブロックの引き直し

## 目的
OneHot/Ordinal/TargetEncoder/KBins/PCA/Tfidf/multi-hot の「作る/使う」を最新ベストプラクティスで引き直す。
基準は「sklearn が十分うまくやっているか」（データ依存かではない・DEC-0008）。設計は Fable（Web 裏取り）。

## 受け入れ基準（テスト先行で）
- **使う（作らない）**：OneHot/Ordinal/TargetEncoder(平滑化平均・OOF)/KBins/PCA/Tfidf は sklearn を ColumnTransformer に直接（set_output polars）。docstring・DESIGN に明記。
- **作る**：`MultiHot`（list 列のタグ・語彙を fit で学習・未知は無視・null/空は 0・feature_names は fit 後）／`TargetAggregate`（target の mean 以外の統計・OOF 内蔵の fit_transform・mean/y 無し/未対応 agg は失敗・未知グループは全体統計）／`CombineKeys`（多キーを1列に結合・null は <null>）。`BLOCKS` に追記。
- **契約是正**：`FeatureBlock.feature_names` は fit 後確定を許す（データ依存は fit 前 NotFittedError）。`FeaturePipeline.fit_transform` を新設し各ブロックの fit_transform を通す（OOF が動く）。describe は fit 前も可。
- 漏れ検知：TargetAggregate を run_cv に通し fold の train だけで学習（外側）／fit_transform が OOF（内側・cross-fitting）。期待値は分割・構成から導出。
- `DEC-0008` を起票。`uv run verify` 全成功（unit85/integration19/e2e2）。
