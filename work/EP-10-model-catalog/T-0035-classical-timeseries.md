---
id: T-0035
kind: task
status: done
title: 古典時系列（ARIMA/SARIMA/ETS）の別バックボーン forecast.py・run_forecast
depends_on: [T-0031, T-0034]
created: 2026-07-03
verified_by:
  - tests/test_forecast.py::test_seasonal_model_beats_naive
  - tests/test_forecast.py::test_backtest_is_past_to_future
  - tests/test_forecast.py::test_forecast_is_deterministic
  - tests/test_forecast.py::test_backtest_folds_input_checks
  - tests/test_catalog.py::test_ts_models_have_docstrings
---
# T-0035 古典時系列（T-E・別バックボーン）

## 受け入れ基準
- 新設 `forecast.py`：`ForecastLike`（fit(y)→forecast(h)）＋`_StatsmodelsForecaster`（翻訳層は最小 1 クラス）＋
  工場 arima/sarima/ets（statsmodels を「使う」）＋`TS_MODELS`（find_spec 条件登録）＋`build_ts_model`＋
  `ForecastResult`＋`run_forecast`（バックテスト）。**sklearn 背骨（run_cv/clone/build_estimator）に載せない**（DEC-0007）。
- `cv.make_backtest_folds`（時間順バックテストの fold 表・expanding を流用）。`data models` に [timeseries] を条件表示。
- statsmodels を optional extra＋mypy override＋TRACKED_DISTRIBUTIONS。experiment スキルに古典時系列の入口。
- 期待値は構成から導出（季節モデルが季節ナイーブに勝つ・時間順・決定性・入力検査）。

## 触っていない（別経路の証拠）
run_cv・experiment.py・eval.py・store.py・pipeline.py は無変更（評価/保存/分割の正本を流用のみ）。

## 結果
実装・verify 緑。EP-10 完了（分類6・回帰6・時系列 ML方式＋古典3）。雛形（train.py）は最初の時系列実験が作る（Rule of Three）。
