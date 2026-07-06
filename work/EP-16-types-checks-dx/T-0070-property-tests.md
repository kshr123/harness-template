---
id: T-0070
kind: task
status: done
title: property テスト（hypothesis）＝不変条件で核の性質を固定する
created: 2026-07-06
depends_on: [T-0053]
verified_by:
  - tests/test_properties.py::test_passes_nan_is_always_fail_closed
  - tests/test_properties.py::test_passes_finite_values_follow_metric_direction
  - tests/test_properties.py::test_psi_is_nonnegative
  - tests/test_properties.py::test_psi_zero_on_identity_and_grows_when_shifted
  - tests/test_properties.py::test_fixed_split_is_deterministic_partition
  - tests/test_properties.py::test_bucket_range_deterministic_and_salt_sensitive
  - tests/test_properties.py::test_fold_indices_cover_every_row_exactly_once
  - tests/test_properties.py::test_scale_output_has_no_nan_and_is_standardized
  - tests/test_properties.py::test_missing_flags_are_binary_and_match_nan_positions
---
# T-0070 property テスト（hypothesis）

## 受け入れ基準
`tests/test_properties.py` に核の不変条件を hypothesis で固定：passes の NaN fail-closed・向き／psi の非負と移動検知／
fixed_split の決定性・被覆・排他・**所属の契約照合**／`_bucket` の範囲・決定性・**salt 感度**／fold の全被覆・重複なし・
train∩valid=∅／scale の NaN 補完後 mean≈0・std≈1／missing_flags は 0/1 かつ isnan 一致。`@settings(derandomize=True)` で決定的。

## 独立レビュー（2026-07-06・maker≠checker・ミューテーション実験 24 変異）
7 property は実装破壊 18 パターンで反例を出し金メッキでないと確認。important 2 件を反映：
- `test_bucket_...` が金メッキ（% 101・salt 無視・定数の 3 変異が生存）→ **複数 id で範囲検査＋salt 感度**（salt を変えたら
  1 つはバケットが変わる）に強化し 3 変異とも殺す。
- `test_fixed_split_...` が pct/salt を結果に結線せず「全 train の定数分割」でも通る（リポ全体でこの穴を殺すテストが無い）
  → 各 id の所属を `_bucket` と pct 閾値の**公開契約で照合**（test=[0,test_pct)・valid=[…)・train=残り）に強化。
minor（psi の 2 点比較・cv の seed/stratify 未検査）は既存例示テストが補完＝据え置き。

## 結果
実装・独立レビュー（金メッキ 2 件を強化）・verify 緑で done。ideal-build-plan Wave 4。
