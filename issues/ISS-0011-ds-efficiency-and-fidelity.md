---
id: ISS-0011
kind: risk
state: open
found_in: ds-review-2026-07-05
created: 2026-07-05
title: DS の一部が大規模データで O(n²) 等に落ちる／TargetEncoder が分類で非層化
---
# ISS-0011 DS の効率と忠実性（大規模で破綻する箇所）

## 事象
スモーク規模では問題ないが、実データ規模で効く欠陥が数点：
- `unsupervised.py` の `silhouette_score` が `cluster_summary`/`k_scan` で **sample_size 無し**＝O(n²)
  （20 万行で概算 320GB／`embed_2d` の t-SNE は `max_rows=5000` で守っているのに silhouette は無防備）。
- `eval.threshold_table` の既定スイープが「全ユニークスコア × 毎回 full `confusion_matrix`」＝O(n²)。かつ P/R/F1 を
  手書き（`_curve` の sklearn 出力を使えば重複しない・DEC-0006）。
- `pipeline._target` が `TargetEncoder` に平の `KFold` を渡し、分類でも **層化を失う**（sklearn 既定は内部で
  StratifiedKFold）＝不均衡で稀少カテゴリのエンコードが劣化。
- `eda.missing_patterns`／`high_correlation_pairs` が Python 行ループ・ペア毎 `corrcoef`（polars/行列で 1 パス可）。
- `data.fixed_split` が per-row Python sha256 ループ。

## 根拠・影響
いずれも「落ちない既定」を掲げる方針に反して、規模が出た案件で静かに実用外になる。多くは小さな修正
（`sample_size=min(n,10_000), random_state=seed`／ベクトル化／分類時 `StratifiedKFold`）。

## 対処の方針（決めてから）
実データ案件で規模が見えた時に、上記を個別修正（各々テスト付き）。silhouette の sample_size と TargetEncoder の
層化は影響が大きく安価なので優先候補。時系列 fold 境界は `TimeSeriesSplit(test_size=)` 委譲も併せて検討。
