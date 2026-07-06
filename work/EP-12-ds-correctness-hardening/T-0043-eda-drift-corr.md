---
id: T-0043
kind: task
status: done
title: EDA ドリフト/相関の正しさ（PSI の裾・相関の NaN 汚染）
created: 2026-07-05
verified_by:
  - tests/test_ds_eda.py::test_psi_detects_out_of_range_shift
  - tests/test_ds_eda.py::test_psi_all_null_train_returns_zero
  - tests/test_ds_eda.py::test_correlations_pairwise_complete_with_null
  - tests/test_ds_eda.py::test_high_correlation_pairs_flags_duplicate_with_null
---
# T-0043 EDA ドリフト/相関の正しさ

## 受け入れ基準
- `psi` は **裾/範囲のドリフトを捉える**：train 分位のビン端を計算後に外側ビンを開く（`edges[0], edges[-1] = -inf, inf`）。
  範囲外の test 値が脱落・正規化で消えないこと。all-null train は 0.0 を返す（`np.quantile` の IndexError を避ける）。
- `correlations`/`high_correlation_pairs` は **pairwise-complete** で相関を測る（`isfinite` マスク）。null が 1 個あっても
  NaN 化せず、相関ランキングの汚染・重複列の検出漏れが起きないこと。

## 結果
実装・テスト先書き（pre-fix で PSI≈0・NaN 相関を確認）・独立レビュー・verify 緑で完了予定。
`docs/ds-review-2026-07-05.md` 参照。行ループ等の効率は ISS-0011 で別途。
