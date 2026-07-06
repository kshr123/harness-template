---
id: T-0062
kind: task
status: done
title: dummy ベースライン（DummyClassifier/DummyRegressor を MODELS に）
created: 2026-07-06
depends_on: [T-0048]
verified_by:
  - tests/test_ds_pipeline.py::test_dummy_returns_prior_probabilities
  - tests/test_ds_pipeline.py::test_dummy_task_check_and_strategy_override
  - tests/test_ds_pipeline.py::test_dummy_reg_predicts_mean
---
# T-0062 dummy ベースライン

## 背景
「学習したモデルが本当に効いているか」は、何も学習しない基準（多数派・平均を返すだけ）と比べて初めて分かる。
sklearn の DummyClassifier/DummyRegressor を MODELS に足し、実験の相対関門・比較の土台にする（参考リポの baseline 比較に相当）。

## 受け入れ基準（sklearn 素通し・DEC-0006）
- `pipeline.py` の MODELS に登録（既存 `_logreg` 等と同じ書き方）：
  - `dummy`（分類）＝`DummyClassifier`（既定 strategy="prior"＝多数派の事前確率を返す・predict_proba あり）。task="classification"。
  - `dummy_reg`（回帰）＝`DummyRegressor`（既定 strategy="mean"）。task="regression"。
  - strategy 等は params で上書き可（素通し）。seed は使わない決定的モデルだが署名は既存と揃える。
- `data models` カタログに description つきで載る（DEC-0009）。既存モデル・build_model は不変。

## 触ってよいファイル
`src/harness/ds/pipeline.py`（MODELS 登録＋factory）＋`tests/test_ds_pipeline.py`（＋必要なら test_catalog）。
`eval.py`/`cv.py`/`models.py`/`analysis.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- `dummy`（prior）：クラス不均衡データ（例 陽性 20%）で predict_proba が全行ほぼ [0.8, 0.2]（事前確率＝構成から）。
  build_model で task="classification" 通過・task="regression" で拒否。
- `dummy_reg`（mean）：y=[0,10] で predict が全行 5（平均＝構成から）。
- カタログ（data models）に dummy/dummy_reg が載る・task が正しい。

## 独立レビュー（2026-07-06・maker≠checker）
prior の predict_proba＝クラス比率・mean・task 検査・カタログ掲載を実測で確認。important 1：`_dummy` が seed を捨てるが
docstring は乱数を使う stratified/uniform を案内＝「seed 固定なのに再現しない」罠 → `random_state=seed` を配線
（prior/most_frequent には無害）。回帰テスト追加。minor：dummy_reg テストのマーカーを integration に揃えた（fit を伴う）。

## 結果
実装・独立レビュー（seed 配線を反映）・verify 緑で done。参考リポ baseline 比較＝ideal-build-plan Wave 3・§参考。
