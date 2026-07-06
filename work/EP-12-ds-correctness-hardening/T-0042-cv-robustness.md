---
id: T-0042
kind: task
status: done
title: CV の頑健性（陽性クラス解決・重複 id 検出・train/valid 重なり検査）
created: 2026-07-05
verified_by:
  - tests/test_ds_cv.py::test_predict_proba_uses_class_label_1_column
  - tests/test_ds_cv.py::test_predict_proba_requires_label_1
  - tests/test_ds_cv.py::test_fold_indices_rejects_duplicate_df_ids
  - tests/test_ds_cv.py::test_fold_indices_rejects_duplicate_fold_table_ids
  - tests/test_ds_cv.py::test_fold_indices_expanding_equivalence
  - tests/test_ds_cv.py::test_run_cv_rejects_overlapping_train_valid
  - tests/test_ds_cv.py::test_run_cv_rejects_length_mismatch
  - tests/test_ds_cv.py::test_run_cv_valid_split_still_runs
---
# T-0042 CV の頑健性

## 受け入れ基準
- `_predict` は陽性クラスを **`classes_` から解決**（`predict_proba[:, classes_==1]`）。ラベルが `{1,2}`/`{-1,1}` でも
  正しい列を返す。ラベル 1 が無ければ明示エラー。単一クラス fold の既存挙動は維持。
- `fold_indices` は **重複 id を検出**（df・fold 表の双方で `n_unique!=height` を弾き、polars の 1:1 join で対応付け）。
  `how="cv"/"expanding"` と fold 0 の扱いは不変（既存の往復・不一致テストが通る）。
- `run_cv` は **train/valid の重なりと `x` 行数/`y` 長の不一致を弾く**（既存の valid 重複検査は維持）。
  clone-per-fold・oof_mask の構造は変えない。

## 結果
実装・テスト先書き（pre-fix で 6 件失敗を確認）・独立レビュー・verify 緑で完了予定。`docs/ds-review-2026-07-05.md` 参照。
二値ハードコードの本格解消（多クラス）は ISS-0009 で別途。
