---
id: T-0044
kind: task
status: done
title: 依存フロアの引き上げと疎行列の非密化
created: 2026-07-05
verified_by:
  - tests/test_ds_pipeline.py::test_to_numpy_keeps_sparse_sparse
  - tests/test_ds_pipeline.py::test_tfidf_output_reaching_model_stays_sparse
  - tests/test_ds_pipeline_integration.py::test_tfidf_hist_gb_densifies_at_model
---
# T-0044 依存フロアと疎行列

## 受け入れ基準
- ds extra の floor を **実使用 API に合わせて引き上げ**：`scikit-learn>=1.9`（`TargetEncoder(cv=<splitter>)` は
  ≤1.8 で int のみ）・`polars>=1.42`（`join(nulls_equal=…)`・`explode(empty_as_null=…)`）。各 floor に理由コメント。
  下流の最小解決で fit 時クラッシュしないこと。
- `pipeline._to_numpy` は **疎行列を密化しない**（`return x`）。polars/pandas フレームだけ `to_numpy`。
  大語彙 tfidf が疎のままモデルに届き、OOM しないこと。**疎を受けない HistGradientBoosting** は工場側
  （`_dense_model`）で直前に密化し、tfidf 等との組合せを壊さない（独立レビューで検出した退行の補修）。

## 結果
実装・テスト先書き（pre-fix で密化を確認）・独立レビュー・verify 緑で完了予定。`docs/ds-review-2026-07-05.md` 参照。
TargetEncoder の層化は quality 事項として ISS-0011 で別途。
