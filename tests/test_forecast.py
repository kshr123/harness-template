"""古典時系列（別バックボーン）のテスト：期待値はデータの構成（トレンド＋季節）から導出する。

sklearn 背骨（run_cv/build_estimator）には触れない経路。素朴予測に勝つ・時間順・決定性・合否の接続を確かめる。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import cv
from harness.ds.forecast import TS_MODELS, build_ts_model, run_forecast


def _series(n: int, *, seasonal: bool) -> tuple[pl.DataFrame, np.ndarray]:
    t = np.arange(n)
    rng = np.random.default_rng(0)
    trend = 0.5 * t
    season = 10.0 * np.sin(2 * np.pi * t / 12) if seasonal else 0.0
    y = (trend + season + rng.normal(scale=0.5, size=n)).astype("float64")
    return pl.DataFrame({"id": np.arange(n), "date": t}), y


@pytest.mark.unit
def test_tuplify_and_unknown_kind() -> None:
    # list（YAML 由来）で fit まで通る＝order の list→tuple 変換の証拠。
    df, y = _series(60, seasonal=False)
    res = run_forecast(df, y, {"kind": "arima", "order": [1, 1, 1]}, order_by="date", horizon=6, seed=0, thresholds={})
    assert res.mask.sum() == 6
    with pytest.raises(ValueError, match="未知の時系列モデル"):
        build_ts_model({"kind": "nope"}, seed=0)


@pytest.mark.unit
def test_unknown_kind_hint_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    import harness.ds.forecast as fc

    monkeypatch.setattr(fc, "TS_MODELS", {})  # 登録空＝未導入を再現
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)  # statsmodels 不在を再現
    with pytest.raises(ValueError, match="uv sync --extra statsmodels"):
        fc.build_ts_model({"kind": "arima"}, seed=0)


@pytest.mark.unit
def test_backtest_folds_input_checks() -> None:
    df = pl.DataFrame({"id": np.arange(10), "date": np.arange(10)})
    with pytest.raises(ValueError, match="学習の頭が空"):
        cv.make_backtest_folds(df, order_by="date", horizon=5, n_windows=2)  # 5*2>=10
    dup = pl.DataFrame({"id": [0, 1, 2], "date": [0, 0, 1]})
    with pytest.raises(ValueError, match="重複"):
        cv.make_backtest_folds(dup, order_by="date", horizon=1, n_windows=1)


@pytest.mark.integration
def test_backtest_is_past_to_future() -> None:
    df, y = _series(120, seasonal=True)
    res = run_forecast(
        df,
        y,
        {"kind": "ets", "trend": "add", "seasonal": "add", "seasonal_periods": 12},
        order_by="date",
        horizon=12,
        n_windows=3,
        seed=0,
        thresholds={},
    )
    assert res.mask.sum() == 3 * 12  # 検証窓＝n_windows×horizon
    dates = df["date"].to_numpy()
    fold_ids = {r["id"]: r["fold"] for r in res.folds.to_dicts()}
    valid_dates = dates[res.mask]
    train_dates = dates[~res.mask]
    assert train_dates.min() < valid_dates.min()  # 学習専用の頭が最古
    assert sum(1 for f in fold_ids.values() if f == 0) == 120 - 36  # fold 0＝評価されない頭


@pytest.mark.integration
def test_seasonal_model_beats_naive() -> None:
    df, y = _series(180, seasonal=True)
    res = run_forecast(
        df,
        y,
        {"kind": "sarima", "order": [1, 1, 1], "seasonal_order": [0, 1, 1, 12]},
        order_by="date",
        horizon=24,
        n_windows=1,
        seed=0,
        thresholds={},
    )
    # 季節ナイーブ（y_{t-12} の繰り返し）の rmse を同じ窓で計算し、モデルが上回ることを確かめる。
    yv = y[-24:]
    naive = y[-36:-12]  # 12 期前
    naive_rmse = float(np.sqrt(np.mean((yv - naive) ** 2)))
    assert res.metrics["rmse"] < naive_rmse  # 季節構造を捉えれば素朴予測に勝つ（構成から）


@pytest.mark.integration
def test_forecast_is_deterministic() -> None:
    df, y = _series(80, seasonal=False)
    spec = {"kind": "arima", "order": [1, 1, 1]}
    a = run_forecast(df, y, spec, order_by="date", horizon=8, seed=0, thresholds={"rmse": 1e9})
    b = run_forecast(df, y, spec, order_by="date", horizon=8, seed=0, thresholds={"rmse": 1e9})
    assert np.allclose(a.preds, b.preds)  # 最尤推定は乱数なし
    assert (
        a.passed and not run_forecast(df, y, spec, order_by="date", horizon=8, seed=0, thresholds={"rmse": 0.0}).passed
    )


@pytest.mark.unit
def test_ts_models_registered() -> None:
    assert set(TS_MODELS) == {"arima", "sarima", "ets"}  # all-extras 環境
