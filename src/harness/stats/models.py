"""ベイズモデルのレジストリ（`BAYES_MODELS`）。kind → 「データから pm.Model を組む工場」。

sklearn の `MODELS`（seed→推定器）とは契約が違う：ベイズモデルは**構築時に観測データを抱く**（pymc の
`observed=`）ので、工場は `(data, **params) → pm.Model` の形。data は列名→配列の対応（例 linear は
`{"X": (n, p), "y": (n,)}`）。事前分布（PRIORS）や分布族（FAMILIES）は軸にしない＝モデル宣言のパラメータで
あって「名前→工場」の解決点が無い（正本は pymc の名前空間）。pymc は工場の関数内で遅延 import する
（`import harness.stats.models` は pymc 未導入でも成功する）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import NDArray

from harness.registry import Entry, Registry


def _normal_mean(data: Mapping[str, NDArray[Any]], **params: Any) -> Any:  # noqa: ANN401  pm.Model を返す
    """観測ベクトル y の平均・標準偏差を推定する最小モデル（正規モデル）。data={"y": (n,)}。

    mu ~ Normal(0, 10)・sigma ~ HalfNormal(10)・y ~ Normal(mu, sigma, observed=y)。事前分布の広さは params で
    上書きできる（mu_sd・sigma_sd）。構造把握のための最小の一巡（walking skeleton）に使う。
    """
    import pymc as pm

    y = np.asarray(data["y"], dtype=np.float64)
    mu_sd = float(params.get("mu_sd", 10.0))
    sigma_sd = float(params.get("sigma_sd", 10.0))
    with pm.Model() as model:
        mu = pm.Normal("mu", 0.0, mu_sd)
        sigma = pm.HalfNormal("sigma", sigma_sd)
        pm.Normal("obs", mu, sigma, observed=y)
    return model


def _linear(data: Mapping[str, NDArray[Any]], **params: Any) -> Any:  # noqa: ANN401  pm.Model を返す
    """ベイズ線形回帰。data={"X": (n, p), "y": (n,)}。alpha＋X@beta を平均に、sigma を観測ノイズに置く。

    alpha ~ Normal(0, 10)・beta ~ Normal(0, 10, shape=p)・sigma ~ HalfNormal(5)・
    y ~ Normal(alpha + X@beta, sigma, observed=y)。事前の広さは params（coef_sd・sigma_sd）で上書きできる。
    """
    import pymc as pm

    x = np.asarray(data["X"], dtype=np.float64)
    y = np.asarray(data["y"], dtype=np.float64)
    if x.ndim != 2:
        raise ValueError(f"linear の X は 2 次元 (n, p) が必要（渡されたのは {x.ndim} 次元）")
    coef_sd = float(params.get("coef_sd", 10.0))
    sigma_sd = float(params.get("sigma_sd", 5.0))
    with pm.Model() as model:
        alpha = pm.Normal("alpha", 0.0, coef_sd)
        beta = pm.Normal("beta", 0.0, coef_sd, shape=x.shape[1])
        sigma = pm.HalfNormal("sigma", sigma_sd)
        pm.Normal("obs", alpha + pm.math.dot(x, beta), sigma, observed=y)
    return model


# kind → ベイズモデルの工場（data → pm.Model）。sklearn の MODELS とは契約が違う（seed でなく data を受ける）
# ので Registry.build（seed 前提）は使わず、resolve して直接呼ぶ。説明文は工場の docstring 1 行目から。
BAYES_MODELS: Registry[Entry] = Registry("ベイズモデル", catalog="stats models")
BAYES_MODELS.register("normal_mean", _normal_mean)
BAYES_MODELS.register("linear", _linear)


def build_bayes_model(spec: Mapping[str, Any], data: Mapping[str, NDArray[Any]]) -> Any:  # noqa: ANN401  pm.Model
    """config の model 節（{kind, ...params}）と観測データから 1 つの pm.Model を組む（build_model と同型）。

    kind は `uv run stats models` の一覧から。params はそのまま工場へ渡す（事前の広さ等）。未知 kind の
    ValueError は Registry.resolve の 1 か所（候補一覧＋カタログ案内）。data は列名→配列（linear は X・y）。
    """
    kind = spec.get("kind")
    entry = BAYES_MODELS.resolve(kind)
    factory_params = {k: v for k, v in spec.items() if k != "kind"}
    return entry.factory(data, **factory_params)
