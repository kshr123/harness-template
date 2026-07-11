---
id: T-0224
kind: task
status: todo
title: TS_MODELS に 3.14 で入る住人を増やす（pmdarima の auto_arima 等・ForecastLike 契約のまま）
created: 2026-07-11
depends_on: []
verified_by: []
---
# T-0224 時系列の住人（環境の軸に依存しない範囲）

## 何が問題か
`TS_MODELS`（`src/harness/ds/forecast.py`）の住人は statsmodels の arima・sarima・ets の 3 つだけで、
次数の自動選択（auto_arima）が無い。statsforecast は 3.14 に入らない（T-0225）が、
**3.14 に入る範囲の拡充は T-0188 の結論を待たずに進められる**（エピックの 2 段構えの前段）。

## やること
- pmdarima（計画時の調査では cp314 あり。**着手時に PyPI で再測定**——依存の可否は日付つきの事実）を
  optional extra にし、条件登録で `auto_arima` を足す。既存の `ForecastLike` 契約
  （`fit(y)` → `forecast(h)`・単変量・exog なし）に薄い包みで載せる（翻訳層を増やさない）。
- 既存の `run_forecast`（バックテスト）・`make_backtest_folds`・`evaluate_regression` に**そのまま**載る
  ことを確かめる（評価・分割・保存の二重化をしない＝forecast.py の規約）。

## やらないこと
- 外生変数（exog）・多変量・パネル予測（`ForecastLike` の契約拡張は消費者が来てから。
  パネルは T-0225 の判断と一体）。
- prophet・tsfresh・chronos 等の網羅（`fit(y)/forecast(h)` に素直に載らないもの——prophet は日付列を
  要求する——は契約拡張の議論が先で、このタスクに入れない）。

## 受け入れ基準
- 構成から導ける系列（例：既知の線形トレンド＋既知の季節周期）のバックテストで、予測が持ち上げた
  トレンドの近傍に入る（許容幅つき。実装出力の写経をしない）。
- 同じ `(y, seed)` で 2 回走らせると同じ予測（決定性）。
- pmdarima 未導入環境で import 成功・カタログに出ない・extras_hint が出る（statsmodels と同じ作法）。
- `uv run verify` 全成功。
