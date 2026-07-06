---
id: T-0064
kind: task
status: done
title: 特徴選択段（SELECTORS＝select 節・to_numpy と model の間・fit-on-train でリークなし）
created: 2026-07-06
depends_on: [T-0048]
verified_by:
  - tests/test_ds_pipeline.py::test_variance_threshold_drops_constant_column
  - tests/test_ds_pipeline.py::test_selectkbest_picks_correlated_column
  - tests/test_ds_pipeline.py::test_from_model_estimator_spec_supports_regression
  - tests/test_ds_pipeline.py::test_build_estimator_inserts_select_between_to_numpy_and_model
  - tests/test_ds_pipeline.py::test_select_estimator_runs_through_run_cv
  - tests/test_catalog.py::test_selectors_have_docstrings
---
# T-0064 特徴選択段（SELECTORS）

## 背景
特徴が多いとノイズ列が過学習・遅さの原因になる。sklearn の特徴選択を「to_numpy と model の間の 1 段」として足す。
run_cv の clone-per-fold で選択も fold の train でだけ起きる＝リークなし（encode と同じ構造的担保）。

## 受け入れ基準（sklearn 素通し・DEC-0006）
- `pipeline.py` に `SELECTORS` レジストリ（registry.py の Registry/Entry・catalog "data selectors"）：
  - `variance_threshold`→`VarianceThreshold`（教師なし・低分散列を落とす）。
  - `selectkbest`→`SelectKBest`（`score_func` を "f_classif"（既定）/"f_regression"/"mutual_info_classif" 等の文字列で選ぶ・k）。
  - `from_model`→`SelectFromModel`（推定器で重要度選択・estimator は既定 or params）。工場は薄く（既定＋params 素通し）。
- `build_estimator` の spec に `select:`（1 個の dict）があれば `to_numpy` の後・`model` の前に選択段（"select"）を挿す。
  無ければ**従来どおり**（steps 不変＝回帰なし）。selectkbest 等が y を使うのは Pipeline が fit(y) を伝えるため
  （run_cv が train の y を渡す＝リークなし）。
- カタログ（`data selectors` か既存カタログ）に description つきで載る（DEC-0009）。最低限 registry の description は必須。

## 触ってよいファイル
`src/harness/ds/pipeline.py`（SELECTORS＋build_estimator の select 段）＋`tests/test_ds_pipeline.py`。
`eval.py`/`cv.py`/`models.py`/`cli.py` は触らない（並行作業あり）。CLI カタログ配線は registry の description があれば別途でよい。

## 検査（テスト先書き・構成から導く）
- `variance_threshold`：定数列（分散 0）＋変動列のデータで、選択後に定数列が落ちる（列数が減る＝構成から）。
- `selectkbest`（k=1）：y と強く相関する列と無関係な列で、選ばれるのが相関列（構成から導ける）。build_estimator に
  select 段が入り fit/predict が通る。
- `select` 無しの spec は steps が従来どおり（["features",...,"to_numpy","model"]・select が入らない）。
- リーク：run_cv に select 付き estimator を通して fit/predict が通る（clone-per-fold で train のみ選択）。

## 独立レビュー（2026-07-06・maker≠checker）
リーク防止（各 fold の select が train のみで fit＝valid の y 非混入）・to_numpy 後の numpy/疎受け・score_func 写像・
配線を実測で確認。important 1：`from_model` の既定 estimator が LogisticRegression 固定＝config(YAML) から回帰選択器を
組めず fit 時に落ちる → estimator を model spec（{kind}）で受け build_model で解決（回帰は estimator に回帰モデル指定）。
minor：selectkbest の k>特徴数 no-op を docstring 明記。据え置き：data selectors CLI 未配線（[[ISS-0012]] に集約）・
run_cv テストの no-leak は構造担保（cv 側テスト）に依存。

## 結果
実装・独立レビュー（from_model の回帰対応を反映）・verify 緑で done。ideal-build-plan Wave 3「feature selection 段」。
