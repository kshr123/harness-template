"""収束診断と、既存 value_threshold での収束判定の検査（T-0214）。

期待値は「よく収束した小モデル」の構成から導く：弱情報事前＋十分なデータ＋そこそこの draw なら r_hat は 1 近傍・
ess は正・divergences は 0。閾値は実装出力の写経でなく「収束の常識的な線」（r_hat<=1.1・ess>=50 等）から置く。
fail closed（非有限＝発散は不合格）は、診断が inf のときの gate の挙動で確かめる（実際の発散を強制せずに）。
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pymc")
pytest.importorskip("nutpie")

from harness import gates  # noqa: E402
from harness.stats import diagnostics, models, sampling  # noqa: E402

pytestmark = pytest.mark.integration


def _fit_linear() -> object:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(80, 2))
    y = 0.5 + x @ np.array([1.5, -2.0]) + rng.normal(scale=0.3, size=80)
    model = models.build_bayes_model({"kind": "linear"}, {"X": x, "y": y})
    return sampling.run_inference(model, sampler="nutpie", draws=200, tune=200, chains=2, seed=0)


def test_diagnostic_directions_are_declared() -> None:
    """向きの表：r_hat・divergences は小さいほど良い（False）・ess_bulk は大きいほど良い（True）。"""
    assert diagnostics.diagnostic_directions() == {"r_hat": False, "ess_bulk": True, "divergences": False}


def test_compute_diagnostics_covers_all_registered() -> None:
    """compute_diagnostics はレジストリの全 kind を計算する（住人を足せば自動で増える）。"""
    idata = _fit_linear()
    diag = diagnostics.compute_diagnostics(idata)
    assert set(diag) == set(diagnostics.BAYES_DIAGNOSTICS)
    assert diag["r_hat"] < 1.1  # よく収束（構成から：弱情報事前＋n=80＋200 draw）
    assert diag["ess_bulk"] > 50.0  # 実効標本は十分に正
    assert diag["divergences"] == 0.0  # この易しい事後では発散しない


def test_converged_model_passes_reasonable_thresholds() -> None:
    """収束したモデルは常識的な収束閾値を満たす（value_threshold の並びで合格・新 gate kind なし）。"""
    idata = _fit_linear()
    decision = diagnostics.assess_convergence(idata, {"r_hat": 1.1, "ess_bulk": 50.0, "divergences": 0.0})
    assert decision.approved
    assert all(r.passed for r in decision.results)


def test_impossible_ess_threshold_fails_threshold_not_met() -> None:
    """届かない ess 閾値（1e9）は不合格（threshold_not_met）＝閾値が効いている（緑の飾りでない）。"""
    idata = _fit_linear()
    decision = diagnostics.assess_convergence(idata, {"ess_bulk": 1e9})
    assert not decision.approved
    assert any(r.reason == "threshold_not_met" for r in decision.results)


def test_nonfinite_diagnostic_is_rejected_fail_closed() -> None:
    """診断が非有限（発散した版で r_hat=inf 等）なら不合格（not_finite）＝発散を昇格させない。

    実際の発散を安定に強制するのは難しいので、stats の向きの表＋既存 gate に inf を渡して、収束判定が
    fail closed で落ちることを確かめる（比較 inf>=1.01 は True で通ってしまうのを有限性の条件が止める）。
    """
    ctx = gates.GateContext(
        candidate={"r_hat": float("inf")}, baseline=None, directions=diagnostics.diagnostic_directions()
    )
    decision = gates.evaluate(ctx, gates.value_threshold_specs({"r_hat": 1.01}))
    assert not decision.approved
    assert any(r.reason == "not_finite" for r in decision.results)
