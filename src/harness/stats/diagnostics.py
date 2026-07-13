"""収束診断のレジストリ（`BAYES_DIAGNOSTICS`）と、既存の value_threshold での収束判定。

新しい gate kind は作らない：`r_hat <= 1.01`・`ess_bulk >= 400`・`divergences <= 0` はどれも「指標 × 閾値 ×
向き」で、既存の `harness.gates.value_threshold` の spec がそのまま書ける（新 kind は二重化）。stats に要るのは
指標を計算するレジストリと、その向き（higher_is_better）の表だけ。向きを解決して `GateContext` に渡し、
`gates.evaluate` に判定させる（中核はプロファイルのレジストリを import しない＝解決済みで届く既存の作法）。
gates は fail closed：測っていない指標・非有限（発散）は不合格になる（`not_measured`/`not_finite`）。
arviz は関数内で遅延 import する（`import harness.stats.diagnostics` は未導入でも成功する）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from harness import gates
from harness.registry import Entry, Registry


@dataclass(frozen=True, kw_only=True)
class DiagnosticEntry(Entry):
    """収束診断の 1 項目。higher_is_better は value_threshold の向き（r_hat・divergences は小さいほど良い）。"""

    higher_is_better: bool


def _all_values(dataset: Any) -> np.ndarray:  # noqa: ANN401  arviz/xarray Dataset(Tree)
    """全変数の値を 1 本の配列に連結する（ベクトルパラメータの各成分も含む）。空なら NaN 1 個を返す。

    **NaN を落とさない**のが肝：xarray の `.max()/.min()` は既定 skipna=True で、停止した（分散 0 の）成分の
    NaN を黙って捨てる。それを worst-case 集約の前で捨てると、未収束のパラメータが緑で通る（gates の not_finite が
    働く前に非有限が消える）。生の値を numpy で畳めば NaN・inf が伝播し、既存の not_finite 判定に落とせる。
    """
    parts = [np.asarray(dataset[var].values, dtype=float).ravel() for var in dataset.data_vars]
    return np.concatenate(parts) if parts else np.array([float("nan")])


def _rhat_max(idata: Any) -> float:  # noqa: ANN401  arviz.InferenceData
    """全変数（各成分）の r_hat の最大（1 に近いほど収束）。1 成分でも非有限なら NaN を伝播＝not_finite で不合格。"""
    import arviz as az

    return float(np.max(_all_values(az.rhat(idata))))  # np.max は NaN/inf を伝播する（skipna しない）


def _ess_bulk_min(idata: Any) -> float:  # noqa: ANN401  arviz.InferenceData
    """全変数（各成分）の bulk 有効標本数の最小（小さいほど信頼できない）。非有限は NaN を伝播＝not_finite で不合格。"""
    import arviz as az

    return float(np.min(_all_values(az.ess(idata, method="bulk"))))  # np.min も NaN/inf を伝播する


def _divergences(idata: Any) -> float:  # noqa: ANN401  arviz.InferenceData
    """NUTS の発散の総数（幾何が難しく踏み外した回数・0 が理想。多いと事後がバイアスする）。"""
    return float(idata.sample_stats["diverging"].sum())


# kind → 収束診断（InferenceData → スカラー）＋向き。sklearn の指標と契約が違う（idata を受ける）ので
# Registry.build は使わず resolve して直接呼ぶ。説明文は関数の docstring 1 行目から。
BAYES_DIAGNOSTICS: Registry[DiagnosticEntry] = Registry("収束診断", catalog="stats diagnostics")
BAYES_DIAGNOSTICS.register("r_hat", _rhat_max, entry_cls=DiagnosticEntry, higher_is_better=False)
BAYES_DIAGNOSTICS.register("ess_bulk", _ess_bulk_min, entry_cls=DiagnosticEntry, higher_is_better=True)
BAYES_DIAGNOSTICS.register("divergences", _divergences, entry_cls=DiagnosticEntry, higher_is_better=False)


def compute_diagnostics(idata: Any) -> dict[str, float]:  # noqa: ANN401  arviz.InferenceData
    """登録済みの全診断を計算して指標→値の対応を返す（対象集合はレジストリから導出＝住人を足せば自動で増える）。"""
    return {kind: BAYES_DIAGNOSTICS[kind].factory(idata) for kind in sorted(BAYES_DIAGNOSTICS)}


def diagnostic_directions() -> dict[str, bool]:
    """診断名 → higher_is_better の表（value_threshold の向きの正本。gates へ解決済みで渡すため）。"""
    return {kind: BAYES_DIAGNOSTICS[kind].higher_is_better for kind in BAYES_DIAGNOSTICS}


def assess_convergence(idata: Any, thresholds: dict[str, float]) -> gates.PromotionDecision:  # noqa: ANN401
    """収束を判定する：診断を計算し、既存の value_threshold の並びで合否を出す（新 gate kind なし）。

    thresholds は診断名→閾値（例 {"r_hat": 1.01, "ess_bulk": 400, "divergences": 0}）。向きは
    diagnostic_directions から解決して GateContext に渡す。fail closed：閾値を書いた指標を測っていない・
    発散して非有限なら不合格（gates.value_threshold の not_measured/not_finite）。全件評価してから合否を返す。
    """
    diagnostics = compute_diagnostics(idata)
    ctx = gates.GateContext(candidate=diagnostics, baseline=None, directions=diagnostic_directions())
    return gates.evaluate(ctx, gates.value_threshold_specs(thresholds))
