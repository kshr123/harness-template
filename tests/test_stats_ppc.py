"""事前・事後予測検査の検査（T-0216）。

期待値は構成から：正しく指定した線形モデルを自分の生成データに当てると、事後予測の 90% 区間は観測を
おおむね覆う（被覆率 ~0.9）。閾値は「較正の常識的な線」（>=0.8）から置く（実装出力の写経でない）。MCMC は
小さく回す（verify に載る速さ）。stats を使わない複製では importorskip で skip。
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pymc")
pytest.importorskip("nutpie")

from harness.stats import models, ppc, sampling  # noqa: E402

pytestmark = pytest.mark.integration


def _fit() -> tuple[object, object]:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(80, 2))
    y = 0.5 + x @ np.array([1.5, -2.0]) + rng.normal(scale=0.3, size=80)
    model = models.build_bayes_model({"kind": "linear"}, {"X": x, "y": y})
    idata = sampling.run_inference(model, sampler="nutpie", draws=200, tune=200, chains=2, seed=0)
    return model, idata


def test_ppc_directions_declared() -> None:
    assert ppc.ppc_directions() == {"coverage_90": True}  # 被覆率は大きいほど良い（下限で判定）


def test_coverage_near_nominal_for_correct_model() -> None:
    """正しいモデルを自分のデータに当てると、90% 区間の被覆率は 0.9 近傍（構成から・許容幅つき）。"""
    model, idata = _fit()
    ppc.sample_posterior_predictive(model, idata, seed=0)
    values = ppc.compute_ppc(idata)
    assert set(values) == set(ppc.PPC_CHECKS)
    assert 0.8 <= values["coverage_90"] <= 1.0  # 較正が良い＝観測をおおむね覆う


def test_assess_ppc_passes_reasonable_threshold() -> None:
    model, idata = _fit()
    ppc.sample_posterior_predictive(model, idata, seed=0)
    decision = ppc.assess_ppc(idata, {"coverage_90": 0.8})
    assert decision.approved and all(r.passed for r in decision.results)


def test_assess_ppc_fails_impossible_threshold() -> None:
    """届かない被覆率（>=0.999）は不合格（threshold_not_met）＝閾値が効いている（緑の飾りでない）。"""
    model, idata = _fit()
    ppc.sample_posterior_predictive(model, idata, seed=0)
    decision = ppc.assess_ppc(idata, {"coverage_90": 0.999})
    assert not decision.approved
    assert any(r.reason == "threshold_not_met" for r in decision.results)


def test_compute_ppc_without_posterior_predictive_raises() -> None:
    """posterior_predictive 群を作らずに検査すると、明示的な ValueError（先に生成する）。"""
    _, idata = _fit()  # sample_posterior_predictive を呼んでいない
    with pytest.raises(ValueError, match="posterior_predictive"):
        ppc.compute_ppc(idata)


def test_prior_predictive_generates_group() -> None:
    """事前予測が prior_predictive 群を生む（事前が観測変数の予測を出せる）。"""
    model, _ = _fit()
    prior = ppc.sample_prior_predictive(model, draws=100, seed=0)
    assert "obs" in prior.prior_predictive
