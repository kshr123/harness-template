---
id: T-0018
kind: task
status: done
title: 特徴量ブロック（Ratios/Differences/GroupAggregate/CountEncode＋レジストリ）
requirements: [REQ-004]
depends_on: [T-0013]
verified_by:
  - tests/test_ds_features.py::test_group_aggregate_learns_group_stats
  - tests/test_ds_features.py::test_count_encode
  - tests/test_ds_features.py::test_feature_names_match_output_columns
  - tests/test_ds_features.py::test_stateful_unfitted_and_clone_lose_state
  - tests/test_ds_features_integration.py::test_group_aggregate_fits_on_train_fold_only
  - tests/test_ds_features_integration.py::test_count_encode_fits_on_train_fold_only
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0018 特徴量ブロックの追加

## 目的
複数列から作るモデル非依存の特徴量ロジックを FeatureBlock として足す。参考リポ blocks の精査結果
（Fable 設計）を我々の流儀に翻訳。sklearn で足りるものは作らない（DEC-0006/0007）。

## 受け入れ基準（テスト先行で）
- 無状態：`Ratios(pairs)`（`a_div_b`・0/null は null）・`Differences(pairs)`（`a_minus_b`）。
- 有状態：`GroupAggregate(group_by,columns,aggs,derived)`（グループ別集約を train で学習・未知グループは全体統計・derived＝ratio/diff・null も 1 グループ・未対応 agg は失敗）・`CountEncode(columns,normalize)`（度数/割合・未知は 0）。fit は train でだけ・未 fit は NotFittedError・`_AGG_EXPRS` 辞書で集約を拡張。
- `BLOCKS` レジストリ（config の kind→クラス）。全ブロックで `feature_names()＝出力列順`。
- 個別の標準変換（OneHot/Ordinal/TargetEncoder/KBins/PCA/Tfidf/multi-hot）は**作らず** sklearn を ColumnTransformer に直接入れる（設計に明記）。
- 漏れ検知（integration）：GroupAggregate/CountEncode を run_cv に通し、fold の train だけで統計が学習される（clone-per-fold）ことを構成から厳密に確認。
- 追記は `src/harness/ds/features.py` 1 ファイル（過剰分割しない）。`uv run verify` 全成功。
