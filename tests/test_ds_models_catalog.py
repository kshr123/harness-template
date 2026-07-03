"""追加モデル（sklearn）の結線テスト：期待値はデータの構成（線形分離不能・分位・L1）から導出する。"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
import pytest

from harness.ds import eval as ev
from harness.ds.pipeline import build_estimator, build_model

pytestmark = pytest.mark.integration


def _xor(n: int, seed: int) -> tuple[pl.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    x1, x2 = rng.normal(size=n), rng.normal(size=n)
    y = ((x1 > 0) ^ (x2 > 0)).astype("int64")  # XOR＝線形分離不能
    return pl.DataFrame({"x1": x1, "x2": x2}), y


def _auc(kind: str) -> float:
    xtr, ytr = _xor(400, 0)
    xte, yte = _xor(400, 1)
    est = build_estimator(
        {"features": [{"kind": "columns", "columns": ["x1", "x2"]}]}, build_model({"kind": kind}, seed=0), seed=0
    )
    est.fit(xtr, ytr)
    return ev.roc_auc(yte, est.predict_proba(xte)[:, 1])


def test_nonlinear_models_beat_linear_on_xor() -> None:
    assert _auc("logreg") <= 0.65  # 線形は XOR をほぼ当てられない（構成上ほぼ 0.5）
    assert _auc("random_forest") >= 0.85  # 非線形は当てられる
    assert _auc("hist_gb") >= 0.85


def test_quantile_objective_shifts_predictions() -> None:
    # 目的関数（loss=quantile）の変更が効く：0.9 分位の予測は 0.1 分位より高い（分位の定義から）。
    rng = np.random.default_rng(0)
    x1 = rng.normal(size=400)
    x = pl.DataFrame({"x1": x1})
    y = (x1 + rng.normal(scale=1.0, size=400)).astype("float64")  # 対称な雑音
    spec = {"features": [{"kind": "columns", "columns": ["x1"]}]}
    hi = build_estimator(
        spec, build_model({"kind": "hist_gb_reg", "loss": "quantile", "quantile": 0.9}, seed=0), seed=0
    )
    lo = build_estimator(
        spec, build_model({"kind": "hist_gb_reg", "loss": "quantile", "quantile": 0.1}, seed=0), seed=0
    )
    hi.fit(x, y)
    lo.fit(x, y)
    assert hi.predict(x).mean() > lo.predict(x).mean()


def test_lasso_l1_zeroes_coefficients_as_alpha_grows() -> None:
    # L1 正則化：alpha を大きくすると非ゼロ係数が減る（L1 の定義から）。
    rng = np.random.default_rng(0)
    n = 300
    x = rng.normal(size=(n, 8))
    y = (2.0 * x[:, 0] + rng.normal(scale=0.1, size=n)).astype("float64")  # 効くのは 1 列だけ
    # coef_ は SklearnLike に無い属性なので Any で受ける（具体クラス Lasso の係数を見るテスト）。
    weak: Any = build_model({"kind": "lasso", "alpha": 0.001}, seed=0, task="regression")
    strong: Any = build_model({"kind": "lasso", "alpha": 1.0}, seed=0, task="regression")
    weak.fit(x, y)
    strong.fit(x, y)
    n_weak = int(np.sum(np.abs(weak.coef_) > 1e-8))
    n_strong = int(np.sum(np.abs(strong.coef_) > 1e-8))
    assert n_strong < n_weak  # 強い正則化ほど非ゼロが少ない
