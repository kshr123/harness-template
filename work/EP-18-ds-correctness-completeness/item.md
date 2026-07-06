---
id: EP-18
kind: epic
status: in-progress
title: ds 正しさと完成度の詰め（静かに誤る欠陥の修正＋次点部品の取り込み）
plan: detailed
requirements: [REQ-002]
depends_on: [EP-15, EP-16]
created: 2026-07-06
---
# EP-18 ds 正しさと完成度の詰め（Wave A＋D）

## 目的
配信プロファイル（EP-17）を積む前に、ds プロファイルの**「静かに誤る/実用外になる」correctness 欠陥**を先に正し、
続けて**明示的に先送りされていた次点部品**（sklearn/scipy 素通し）を DEC-0010・DEC-0012 に基づき取り込む。
3 面の fable 調査（2026-07-06）で棚卸し済み。原則「correctness を completeness より先に・依存の浅い順」。

## Wave A（correctness 最優先・単一ファイル局所・依存ゼロ）
- **T-0074 pipeline 正しさ**：`TargetEncoder` 分類時の層化（非層化の静かな劣化・G2）＋回帰 `tune:` の内側 CV 分岐
  （現状 StratifiedKFold 固定で回帰モデル＋tune が落ちる・G8）＋`mutual_info_regression` を score_func に（G9）。
- **T-0075 silhouette sample_size**：`cluster_summary`・`k_scan` の silhouette に `sample_size`（大データで O(n²)＝実用外・G1）。
- **T-0076 threshold_table**：sklearn 曲線委譲＋累積カウントでベクトル化（O(n²) 解消・手書き P/R/F1 の DEC-0006 違反解消・G3）。
- **T-0077 eda ベクトル化**：`missing_patterns`・`high_correlation_pairs`・`duplicate_columns` を polars/行列 1 パスに（G4）。
- **T-0078 継ぎ目の task 三値**：`run_experiment` の task 注釈を三値に（G6）＋雛形 train.py の task 分岐（regression/multiclass の
  `--test` スモーク・G7）＋`analysis` の多クラス OOF 対応（G10）。

## Wave D（completeness・次点部品・各小・sklearn/scipy 素通し）
KS/Wasserstein（eda）・bootstrap CI（eval/analysis）・cost-sensitive 閾値（eval・T-0076 の累積土台に相乗り）・
TransformedTargetRegressor log1p（pipeline）・TruncatedSVD エンコーダ（pipeline・疎対応の穴）・poisson/quantile 回帰＋
pinball α（pipeline・eval）・mutual_information 表（eda）・leakage_scan（eda・既存部品の合成のみ・docstring 方針更新）。

## やらないこと（ノイズとして記録・DEC-0012 の「一般性で判断」）
OOF blending（champion＝1 Pipeline の保存/predict/promote 契約を壊す）・CatBoost（lightgbm と重複）・
「入れない」8 項目（RidgeClassifier・RBF-SVC・GaussianNB・imbalanced-learn・PolynomialFeatures・FeatureHasher・
repeated CV・multilabel）。lag/rolling ブロックは DESIGN 先行で本エピック外（推論時履歴の契約が要る）。

## 進め方
各タスク＝1 PR・テスト先書き（期待値は入力構成から導く）・fable 実装（disjoint files 並列）・別 fable の maker≠checker
レビュー（差分のみ）・`uv run verify` 緑で done。部品追加は DEC-0009（registry＋docstring→カタログ）まで。
