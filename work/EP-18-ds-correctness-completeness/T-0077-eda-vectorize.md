---
id: T-0077
kind: task
status: done
title: eda ベクトル化（missing_patterns・high_correlation_pairs・duplicate_columns の Python ループ解消）
created: 2026-07-06
depends_on: []
verified_by:
  - tests/test_ds_eda.py::test_missing_patterns_deterministic_order_and_top
  - tests/test_ds_eda.py::test_high_correlation_pairs_from_matrix_construction
  - tests/test_ds_eda.py::test_high_correlation_pairs_constant_column_never_flagged
  - tests/test_ds_eda.py::test_high_correlation_pairs_large_offset_no_catastrophic_cancellation
  - tests/test_ds_eda.py::test_duplicate_columns_groups_and_order
---
# T-0077 eda ベクトル化

## 背景（G4）
- `missing_patterns`（L214 付近）が Python 行ループ。
- `high_correlation_pairs`（L328 付近）がペア毎 Python `_corr`＝O(p²·n) の Python 定数。
- `duplicate_columns`（L233 付近）が列毎に全行 hash の Python tuple 化。

## 受け入れ基準（polars/numpy 素通し・出力不変）
- `missing_patterns`：polars `group_by(struct(is_null))` 等でベクトル化。
- `high_correlation_pairs`：相関を行列 1 パス（`DataFrame.corr` か numpy corrcoef）で計算し閾値抽出。
- `duplicate_columns`：列ハッシュ/等価判定を polars でベクトル化。
- **公開 API・戻り値の内容は不変**（並び順が変わり得る箇所は決定的な整列を明示＝安定出力）。既存テストの期待値が不変で緑。

## 触ってよいファイル
`src/harness/ds/eda.py`（対象 3 関数と補助のみ）＋`tests/test_ds_eda.py`。
`pipeline.py`/`eval.py`/`unsupervised.py` は触らない（並行作業あり）。psi/drift_auc は触らない（EP-17 monitor が使う・不変）。

## 検査（テスト先書き・構成から導く）
- 欠損パターンが既知の小データで missing_patterns が構成どおり（パターンと件数）。
- 相関が既知（完全相関列・無相関列を仕込む）で high_correlation_pairs が閾値どおりのペアを返す。
- 重複列を仕込んだデータで duplicate_columns が検出。並びは決定的。
- 既存 eda テストが不変で緑。

## 独立レビュー（maker≠checker・差分のみ・実測）
実装欠陥なし。最重点の欠損対応 pairwise 相関（`_pairwise_corr_matrix`）を旧 `_corr` 総当たりと照合＝列別欠損・片側欠損・共通
有効行 0/1/2・定数列・1e9 オフセット・乱数 100 試行で全一致（±1 クリップ・0.0 規約も一致）。missing_patterns は予約列名でも
別名回避が機能・duplicate_columns は並べ替え非検出/真重複検出/指紋衝突でも eq_missing で正しく確定。指摘 1（軽微・テスト穴）：
中心化（桁落ち防止）を守るテストが無く変異が素通り → 1e9 オフセット比例列で r≈1 を検出するテスト追加（中心化除去の変異が赤に）。
verify 全体緑で done。
