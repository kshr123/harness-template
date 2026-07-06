"""古典時系列（ARIMA/SARIMA/ETS）の別バックボーン経路。

sklearn 背骨（pipeline/cv/experiment）とは別経路。**run_cv・clone・build_estimator に載せない**（DEC-0007）。
理由：古典時系列は fit(y)→forecast(h)（単変量・構築時に y を抱く）で、clone(get_params 前提)・predict_proba に
載らない。だから別レジストリ `TS_MODELS`＋薄い翻訳層（_StatsmodelsForecaster 1 つ）＋バックテスト（run_forecast）で
閉じる。評価（eval.METRICS/passes）・fold 表（cv.make_backtest_folds）・保存（store）は流用のみ（二重化しない）。
モデル本体は statsmodels を「使う」（自作ゼロ・DEC-0008）。statsmodels 未導入でもこのモジュールは import できる
（工場内で遅延 import・TS_MODELS は条件登録で空になる）。
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np
import polars as pl
from numpy.typing import NDArray

from harness.ds.cv import make_backtest_folds
from harness.ds.eval import evaluate_regression, passes
from harness.registry import Entry, Registry


@runtime_checkable
class ForecastLike(Protocol):
    """古典時系列の最小契約。fit は系列全体（過去）を受け、forecast は先の h 点を返す。exog は持たない。"""

    def fit(self, y: NDArray[np.float64]) -> ForecastLike: ...
    def forecast(self, h: int) -> NDArray[np.float64]: ...


def _tuplify(params: Mapping[str, Any]) -> dict[str, Any]:
    """order / seasonal_order を YAML の list → tuple に直す（statsmodels は tuple を要求）。他のキーは触らない。"""
    out = dict(params)
    for key in ("order", "seasonal_order"):
        if isinstance(out.get(key), list):
            out[key] = tuple(out[key])
    return out


@dataclass
class _StatsmodelsForecaster:
    """statsmodels の薄い包み（翻訳層は最小＝これ 1 クラスだけ）。構築時に y を抱く（sklearn と逆順）ので、
    build（y → 未学習モデル）を持ち、fit(y) で構築＋最尤推定、forecast(h) で結果の forecast を呼ぶだけ。"""

    build: Callable[[NDArray[np.float64]], Any]
    fit_kwargs: dict[str, Any] = field(default_factory=dict)
    _result: Any = field(default=None, init=False, repr=False)

    def fit(self, y: NDArray[np.float64]) -> _StatsmodelsForecaster:
        self._result = self.build(np.asarray(y, dtype=np.float64)).fit(**self.fit_kwargs)
        return self

    def forecast(self, h: int) -> NDArray[np.float64]:
        return np.asarray(self._result.forecast(h), dtype=np.float64)


def _arima(seed: int, **params: Any) -> ForecastLike:  # noqa: ANN401  seed は受けて捨てる（乱数なし・決定的）
    """ARIMA（自己回帰＋差分＋移動平均・単変量・非季節）。order: [p, d, q] 必須。task: timeseries。

    等間隔の系列前提（order_by は並べ替えにだけ使う）。季節性があるデータは sarima を。乱数なし・決定的。
    収束警告が出たら order を見直すか maxiter を params で増やす。
    """
    from statsmodels.tsa.arima.model import ARIMA

    kwargs = _tuplify(params)
    return _StatsmodelsForecaster(lambda y: ARIMA(y, **kwargs))


def _sarima(seed: int, **params: Any) -> ForecastLike:  # noqa: ANN401
    """SARIMA（季節つき ARIMA）。order: [p,d,q]・seasonal_order: [P,D,Q,s]（s＝季節周期）必須。task: timeseries。

    等間隔・単変量前提。乱数なし・決定的（最適化ログは disp=False で出さない）。収束警告は次数の見直しを。
    """
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    kwargs = _tuplify(params)
    return _StatsmodelsForecaster(lambda y: SARIMAX(y, **kwargs), fit_kwargs={"disp": False})


def _ets(seed: int, **params: Any) -> ForecastLike:  # noqa: ANN401
    """指数平滑（ETS・Holt-Winters）。trend・seasonal・seasonal_periods・damped_trend を params で。task: timeseries。

    季節つきは seasonal="add"/"mul"＋seasonal_periods=周期。等間隔・単変量前提。乱数なし・決定的。
    """
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    return _StatsmodelsForecaster(lambda y: ExponentialSmoothing(y, **params))


# 条件登録：statsmodels が入っている環境でだけ TS_MODELS に足す（`data models` は使える語彙だけを見せる）。
TS_MODELS: Registry[Entry] = Registry(
    "時系列モデル",
    catalog="data models",
    extras_hint={"arima": "statsmodels", "sarima": "statsmodels", "ets": "statsmodels"},
)
if importlib.util.find_spec("statsmodels") is not None:
    TS_MODELS.register("arima", _arima, task="timeseries")
    TS_MODELS.register("sarima", _sarima, task="timeseries")
    TS_MODELS.register("ets", _ets, task="timeseries")


def build_ts_model(spec: Mapping[str, Any], *, seed: int) -> ForecastLike:
    """config の model 節（{kind, ...params}）から 1 つの時系列モデルを作る（build_model と同型・別レジストリ）。

    未知 kind のエラーには statsmodels 未導入時の導入ヒントを添える。params は素通し（order/seasonal_order だけ
    list→tuple）。再学習は「窓ごとに build_ts_model で新品を作り直す」（statsmodels は構築時に y を抱く＝clone 不可）。
    """
    # TS_MODELS は Mapping としてだけ読む（テストが未導入再現のため plain dict に monkeypatch で差し替える）。
    kind = spec.get("kind")
    if not isinstance(kind, str) or kind not in TS_MODELS:
        absent = importlib.util.find_spec("statsmodels") is None
        hint = "。時系列モデルは `uv sync --extra statsmodels` で使えるようになる" if absent else ""
        raise ValueError(f"未知の時系列モデル '{kind}'（{sorted(TS_MODELS)} のいずれか）{hint}")
    params = {k: v for k, v in spec.items() if k != "kind"}
    model: ForecastLike = TS_MODELS[kind].factory(seed, **params)
    return model


@dataclass(frozen=True)
class ForecastResult:
    """バックテスト 1 回ぶんの結果。CVResult / ExperimentResult と同じ骨格（保存・results の作法を変えない）。"""

    folds: pl.DataFrame  # (id, fold)。0=学習専用の頭・1..n_windows=検証窓
    preds: NDArray[np.float64]  # 全行の器（df の行順）。mask が True の行（検証窓）だけ予測が入る
    mask: NDArray[np.bool_]  # 部分カバーを黙認しない規律（CVResult.oof_mask と同じ）
    window_metrics: list[dict[str, float]]  # 窓ごとの回帰指標
    metrics: dict[str, float]  # 全検証窓を連結した回帰指標（合否判定の正本）
    passed: bool
    fitted: list[ForecastLike]  # 窓ごとの学習済み（配布用は全期間で学習し直す＝雛形の作法）


def run_forecast(
    df: pl.DataFrame,
    y: NDArray[np.float64],
    spec: Mapping[str, Any],
    *,
    order_by: str,
    horizon: int,
    n_windows: int = 1,
    seed: int,
    thresholds: Mapping[str, float],
    metrics: Sequence[str] | None = None,
    id_column: str = "id",
) -> ForecastResult:
    """時間順バックテスト：窓 k ごとに「過去で fit → horizon 点を forecast → 実測と比較」。

    指標は eval.evaluate_regression（rmse/mae/mape）・合否は eval.passes・fold 表は cv.make_backtest_folds
    （評価・合否・分割の正本を二重化しない）。run_cv・clone・predict_proba には触れない（DEC-0007）。
    リーク防止は構造：train は常に検証窓より前の行だけ・forecast(h) は先の h 点しか返せない（未来が学習に入らない）。
    """
    folds = make_backtest_folds(df, order_by=order_by, horizon=horizon, n_windows=n_windows, id_column=id_column)
    # 時間順に並べた系列で計算する（statsmodels は連続した過去の数列を要求）。preds/mask は df の元の行順へ戻す。
    sort_idx = df.with_row_index("__row__").sort(order_by)["__row__"].to_numpy()
    y_sorted = np.asarray(y, dtype=np.float64)[sort_idx]
    n = len(y_sorted)

    preds_sorted = np.zeros(n, dtype=np.float64)
    mask_sorted = np.zeros(n, dtype=np.bool_)
    window_metrics: list[dict[str, float]] = []
    fitted: list[ForecastLike] = []
    for w in range(n_windows):
        start = n - (n_windows - w) * horizon  # 古い窓ほど前（make_backtest_folds と同じ切り方）
        model = build_ts_model(spec, seed=seed).fit(y_sorted[:start])  # 過去だけで学習（窓ごとに新品）
        fc = model.forecast(horizon)
        preds_sorted[start : start + horizon] = fc
        mask_sorted[start : start + horizon] = True
        window_metrics.append(evaluate_regression(y_sorted[start : start + horizon], fc, metrics=metrics))
        fitted.append(model)

    overall = evaluate_regression(y_sorted[mask_sorted], preds_sorted[mask_sorted], metrics=metrics)
    preds = np.zeros(n, dtype=np.float64)
    mask = np.zeros(n, dtype=np.bool_)
    preds[sort_idx] = preds_sorted  # 元の行順へ戻す
    mask[sort_idx] = mask_sorted
    return ForecastResult(
        folds=folds,
        preds=preds,
        mask=mask,
        window_metrics=window_metrics,
        metrics=overall,
        passed=passes(overall, dict(thresholds)),
        fitted=fitted,
    )
