---
id: T-0081
kind: task
status: done
title: pipeline 完成度（TransformedTargetRegressor log1p・TruncatedSVD エンコーダ・poisson/quantile 回帰）
created: 2026-07-06
depends_on: [T-0064]
verified_by:
  - tests/test_ds_pipeline.py::test_target_transform_predicts_in_original_scale
  - tests/test_ds_pipeline.py::test_target_transform_model_save_load_roundtrip
  - tests/test_ds_pipeline.py::test_svd_encoder_registered_and_seeded
  - tests/test_ds_pipeline.py::test_poisson_reg_beats_dummy_on_poisson_counts
  - tests/test_ds_pipeline.py::test_quantile_reg_prediction_covers_requested_quantile
---
# T-0081 pipeline 完成度

## 背景（次点部品・sklearn 素通し・DEC-0006/0010）
- **TransformedTargetRegressor（log1p）**：歪んだ回帰ターゲットは頻出。現状は手前で y を変換するしかなく逆変換を雛形が背負う。
- **TruncatedSVD エンコーダ**：tfidf＋疎素通し（`_to_numpy`）まで作ったのに、疎を受けられる次元圧縮が無い（PCA は密のみ）＝
  テキスト経路の穴。
- **poisson/quantile 回帰**：件数・分位型ターゲットの線形基準。hist_gb_reg が loss=poisson/quantile を持つので重複を避け
  `poisson_reg`（PoissonRegressor）と `quantile_reg`（QuantileRegressor）の 2 種に絞る。

## 受け入れ基準（sklearn 素通し・DEC-0009 入口まで）
- `target_transform: log1p` を build_model が解釈し `TransformedTargetRegressor(func, inverse_func)` で包む。func/inverse は
  **モジュール関数**（np.log1p/np.expm1・pickle 可）。回帰のみ・分類指定は fail-loud。rmse 等が原スケールで測れる。save/load 往復可。
- `svd` を ENCODERS（または DIMRED）に登録：`TruncatedSVD`（疎対応・n_components）。tfidf→svd→model が疎のまま fit。
- `poisson_reg`/`quantile_reg` を MODELS に登録（task="regression"・params 素通し・quantile は alpha 分位）。
- **DEC-0009**：3 つとも `data models`/`data encoders` カタログに description つきで掲載（test_catalog が守る）。docstring に config 書き方。

## 触ってよいファイル
`src/harness/ds/pipeline.py`＋`tests/test_ds_pipeline.py`（必要なら test_catalog）。`eval.py`/`eda.py`/`cv.py`/`experiment.py`/`analysis.py`/`tune.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- log1p 包み：正のターゲット合成で TransformedTargetRegressor の予測が原スケール・save/load 往復一致。分類指定で fail-loud。
- svd：疎（tfidf 出力相当）で n_components に落ちる・fit/transform が疎のまま通る・列数が n_components。
- poisson_reg：ポアソン合成で dummy_reg より poisson deviance 改善。quantile_reg：分位 alpha で予測が分位側に寄る。
- カタログ掲載（data models / data encoders）を検査。

## 独立レビュー（maker≠checker・差分のみ・実測）
異常なし。log1p 包みは原スケール予測（相対誤差 4e-10）・func/inverse がモジュール関数で pickle 往復可・分類/未知で fail-loud・
tune で TTR が最外。svd は疎のまま n_components に落ちる（密化なし）・決定的。poisson がポアソン計数で deviance 改善・quantile は
`quantile=`（`alpha=` 取り違えなし）で被覆一致。カタログ 3 件掲載。変異 5/5 撃墜。models.py 未変更。
