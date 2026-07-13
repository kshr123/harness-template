"""事前・事後予測検査（`PPC_CHECKS`）。指標 × 閾値 × 向きの形に落として既存の value_threshold で判定する。

事後予測検査は「モデルが実際に観測を再現できるか」を、事後から生成した予測（posterior predictive）と観測の
食い違いで測る。ここでは**被覆率（coverage）**を指標にする：観測の各点が事後予測の中央区間（90%）に入る割合。
較正が良ければ ~0.90。**下限の閾値**（例 >= 0.8）で「自信過剰なモデル（区間が狭すぎ）」を止める（higher_is_better）。
なお区間が広すぎる過分散は下限では捕まえられない（片側の限界・実需要が来たら別指標を足す）。診断（diagnostics）
と同じく新しい gate kind は作らず、向きを解決して `gates.value_threshold` に判定させる。pymc/arviz は関数内で
遅延 import する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from harness import gates
from harness.registry import Entry, Registry


@dataclass(frozen=True, kw_only=True)
class PPCEntry(Entry):
    """事後予測検査の 1 項目。higher_is_better は value_threshold の向き（coverage は大きいほど良い＝下限で判定）。"""

    higher_is_better: bool


def sample_posterior_predictive(model: Any, idata: Any, *, seed: int) -> Any:  # noqa: ANN401  pm.Model/InferenceData
    """事後から予測を生成し、idata に posterior_predictive 群を足して返す（既存の推論結果を拡張する）。決定的：seed。"""
    import pymc as pm

    with model:
        pm.sample_posterior_predictive(idata, random_seed=seed, progressbar=False, extend_inferencedata=True)
    return idata


def sample_prior_predictive(model: Any, *, draws: int = 500, seed: int) -> Any:  # noqa: ANN401  pm.Model
    """事前から予測を生成して InferenceData（prior・prior_predictive 群）を返す。事前の妥当性の確認に使う。"""
    import pymc as pm

    with model:
        return pm.sample_prior_predictive(draws=draws, random_seed=seed)


def _coverage(idata: Any, *, obs_name: str, lower: float, upper: float) -> float:  # noqa: ANN401
    """観測の各点が事後予測の [lower, upper] 分位区間に入る割合（被覆率）。posterior_predictive 群が要る。"""
    if not hasattr(idata, "posterior_predictive"):
        raise ValueError("posterior_predictive 群が無い（先に sample_posterior_predictive で生成する）")
    ppd = idata.posterior_predictive[obs_name]
    if ppd.ndim != 3:  # (chain, draw, obs) の 1 次元観測だけを扱う。多次元観測は別途（黙って別物を計算しない）
        raise ValueError(f"coverage は 1 次元観測（(chain, draw, n_obs)）のみ対応（実際の次元: {ppd.dims}）")
    samples = np.asarray(ppd.values).reshape(-1, ppd.shape[-1])  # (chain*draw, n_obs)
    obs = np.asarray(idata.observed_data[obs_name].values)  # (n_obs,)
    lo = np.quantile(samples, lower, axis=0)
    hi = np.quantile(samples, upper, axis=0)
    return float(np.mean((obs >= lo) & (obs <= hi)))


def _coverage_90(idata: Any, *, obs_name: str = "obs") -> float:  # noqa: ANN401
    """観測が事後予測の中央 90%（5–95 分位）区間に入る割合（較正が良ければ ~0.90・自信過剰だと低い）。"""
    return _coverage(idata, obs_name=obs_name, lower=0.05, upper=0.95)


# kind → 事後予測検査（idata → スカラー）＋向き。sklearn の指標と契約が違う（idata を受ける）ので Registry.build は
# 使わず resolve して直接呼ぶ。説明文は関数の docstring 1 行目から。
PPC_CHECKS: Registry[PPCEntry] = Registry("事後予測検査", catalog="stats ppc")
PPC_CHECKS.register("coverage_90", _coverage_90, entry_cls=PPCEntry, higher_is_better=True)


def compute_ppc(idata: Any, *, obs_name: str = "obs") -> dict[str, float]:  # noqa: ANN401
    """登録済みの全事後予測検査を計算して指標→値の対応を返す（対象集合はレジストリから導出）。"""
    return {kind: PPC_CHECKS[kind].factory(idata, obs_name=obs_name) for kind in sorted(PPC_CHECKS)}


def ppc_directions() -> dict[str, bool]:
    """事後予測検査名 → higher_is_better の表（value_threshold の向きの正本）。"""
    return {kind: PPC_CHECKS[kind].higher_is_better for kind in PPC_CHECKS}


def assess_ppc(
    idata: Any,  # noqa: ANN401  arviz.InferenceData
    thresholds: dict[str, float],
    *,
    obs_name: str = "obs",
) -> gates.PromotionDecision:
    """事後予測検査を既存の value_threshold の並びで判定する（新 gate kind なし・fail closed）。

    thresholds は検査名→閾値（例 {"coverage_90": 0.8}）。向きは ppc_directions から解決して GateContext に渡す。
    posterior_predictive 群が無ければ compute_ppc が ValueError（先に sample_posterior_predictive で生成する）。
    """
    values = compute_ppc(idata, obs_name=obs_name)
    ctx = gates.GateContext(candidate=values, baseline=None, directions=ppc_directions())
    return gates.evaluate(ctx, gates.value_threshold_specs(thresholds))
