---
id: T-0075
kind: task
status: done
title: silhouette に sample_size（cluster_summary・k_scan の O(n²) を大データで回避）
created: 2026-07-06
depends_on: []
verified_by:
  - tests/test_unsupervised.py::test_cluster_summary_small_matches_full_silhouette
  - tests/test_unsupervised.py::test_cluster_summary_sampling_actually_fires
  - tests/test_unsupervised.py::test_silhouette_falls_back_to_none_when_sample_loses_a_cluster
  - tests/test_unsupervised.py::test_k_scan_large_is_deterministic_per_k
---
# T-0075 silhouette sample_size

## 背景（G1）
`unsupervised.py` の `silhouette_score` に `sample_size` 引数が無く O(n²)。`cluster_summary`（L186 付近）と
`k_scan`（L229 付近）の両方が無防備。t-SNE は `max_rows=5000` で守っているのに silhouette は大データで実用外。

## 受け入れ基準（sklearn 素通し・決定性）
- 両呼び出しに `sample_size=min(n, N)`（N は保守的な既定・例 10_000）と `random_state=seed` を渡す。seed は既存の
  明示引数から流す（グローバル種禁止）。
- 小データ（n ≤ N）では従来と同一値（サンプリングが発動しない）。n > N では件数上限が効く（決定的・seed 固定で再現）。
- docstring に「大データは sample_size で近似（決定的）」を 1 行。挙動の閾値 N を定数で明示。

## 触ってよいファイル
`src/harness/ds/unsupervised.py`＋`tests/test_unsupervised.py`。他の ds ファイルは触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- 小データ（明確な 2〜3 クラスタの合成）で silhouette 値が従来と一致（サンプリング未発動）。
- n を N 超に増やした合成データで、seed 固定なら 2 回同一（決定性）・値が妥当域（分離クラスタで高い）。
- k_scan が各 k で落ちない・決定的。

## 独立レビュー（maker≠checker・差分のみ・実測）
実装は正しい（小データで全件 silhouette とビット一致・大データで seed 固定 2 回一致かつ全件値と異なる＝サンプリング発動を実測・
n は hdbscan 雑音除外後の件数）。指摘 1（中・テスト穴）：サンプリング発動を検査するテストが無く、機能を丸ごと外しても緑だった
→ SILHOUETTE_MAX_ROWS を monkeypatch で縮めて発動を強制し全件値との差＋決定性を検査（変異 A/B/C すべて赤に）。指摘 2（低・端）：
抽出で片方クラスタが消えると silhouette_score が ValueError → try/except で None フォールバック（落とさない既定）＋テスト追加。
verify 全体緑で done。
