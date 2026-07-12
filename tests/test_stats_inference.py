"""stats の推論の一巡（walking skeleton）の検査（T-0213）。

期待値はデータの構成から導く：既知の係数・平均で観測を作り、事後平均がその近傍に入ることを言う（実装出力の
写経でない・許容幅は少 draw と観測ノイズから）。MCMC は小さく回す（draws/tune 少・chains=2＝verify に載る速さ）。
stats を使わない複製（profiles=[]・素の uv sync）では importorskip で skip（optional 依存の欠如）。
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pymc")
pytest.importorskip("nutpie")

from harness.stats import models, sampling  # noqa: E402  importorskip の後で読む

pytestmark = pytest.mark.integration

_DRAWS = 150
_TUNE = 150
_CHAINS = 2


def _posterior_mean(idata: object, var: str) -> np.ndarray:
    return np.asarray(idata.posterior[var].mean(dim=("chain", "draw")))  # type: ignore[attr-defined]


def test_linear_recovers_known_coefficients() -> None:
    """既知の係数（alpha=0.5・beta=[1.5,-2.0]）で作った観測を、線形モデルの事後平均が近傍で当てる。"""
    rng = np.random.default_rng(0)
    x = rng.normal(size=(80, 2))
    true_beta = np.array([1.5, -2.0])
    true_alpha = 0.5
    y = true_alpha + x @ true_beta + rng.normal(scale=0.3, size=80)
    model = models.build_bayes_model({"kind": "linear"}, {"X": x, "y": y})
    idata = sampling.run_inference(model, sampler="nutpie", draws=_DRAWS, tune=_TUNE, chains=_CHAINS, seed=0)
    beta_hat = _posterior_mean(idata, "beta")
    alpha_hat = float(_posterior_mean(idata, "alpha"))
    # 許容幅は観測ノイズ 0.3・n=80・少 draw から緩めに取る（構成した真値の近傍＝当てている）。
    assert np.allclose(beta_hat, true_beta, atol=0.3)
    assert abs(alpha_hat - true_alpha) < 0.3


def test_normal_mean_recovers_mean() -> None:
    """既知の平均（=3.0）の観測を、正規モデルの事後平均が近傍で当てる。"""
    rng = np.random.default_rng(1)
    y = rng.normal(3.0, 1.0, size=120)
    model = models.build_bayes_model({"kind": "normal_mean"}, {"y": y})
    idata = sampling.run_inference(model, sampler="nutpie", draws=_DRAWS, tune=_TUNE, chains=_CHAINS, seed=0)
    mu_hat = float(_posterior_mean(idata, "mu"))
    assert abs(mu_hat - float(y.mean())) < 0.2  # 事後平均は標本平均の近く（弱情報事前＝ほぼデータ主導）


def test_inference_is_deterministic() -> None:
    """同じ (model, seed, sampler) なら同じ事後（決定性）。事後平均の一致で確かめる。"""
    rng = np.random.default_rng(2)
    x = rng.normal(size=(60, 2))
    y = x @ np.array([1.0, -1.0]) + rng.normal(scale=0.3, size=60)
    m1 = models.build_bayes_model({"kind": "linear"}, {"X": x, "y": y})
    m2 = models.build_bayes_model({"kind": "linear"}, {"X": x, "y": y})
    i1 = sampling.run_inference(m1, sampler="nutpie", draws=_DRAWS, tune=_TUNE, chains=_CHAINS, seed=7)
    i2 = sampling.run_inference(m2, sampler="nutpie", draws=_DRAWS, tune=_TUNE, chains=_CHAINS, seed=7)
    assert np.allclose(_posterior_mean(i1, "beta"), _posterior_mean(i2, "beta"))


def test_nutpie_falls_back_to_pymc_for_discrete_latents() -> None:
    """離散潜在（Bernoulli）を含むモデルに nutpie を要求すると PyMC へフォールバック（警告つき）＝黙って壊れない。"""
    import pymc as pm

    with pm.Model() as model:
        p = pm.Beta("p", 1.0, 1.0)
        pm.Bernoulli("k", p)  # 離散潜在＝nutpie が引けない
        pm.Normal("obs", 0.0, 1.0, observed=np.array([0.1, -0.2, 0.3]))
    assert sampling.resolve_sampler("nutpie", model) == "pymc"  # 自動フォールバックの判定
    with pytest.warns(UserWarning, match="nutpie|フォールバック"):
        idata = sampling.run_inference(model, sampler="nutpie", draws=50, tune=50, chains=2, seed=0)
    assert "p" in idata.posterior  # pymc がフォールバックで実際にサンプリングできた


def test_build_bayes_model_unknown_kind() -> None:
    """未知 kind は候補一覧つきの ValueError（Registry.resolve の 1 か所）。"""
    with pytest.raises(ValueError, match="ベイズモデル|nope"):
        models.build_bayes_model({"kind": "nope"}, {"y": np.array([1.0, 2.0])})


def test_registries_are_populated() -> None:
    """all-extras 環境では BAYES_MODELS・SAMPLERS に住人が居る（カタログの土台）。"""
    assert {"normal_mean", "linear"} <= set(models.BAYES_MODELS)
    assert {"nutpie", "pymc"} <= set(sampling.SAMPLERS)
