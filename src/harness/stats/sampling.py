"""サンプラーのレジストリ（`SAMPLERS`）と推論の一巡（`run_inference`）。

`SAMPLERS` は kind → 「pm.Model をサンプリングして InferenceData を返す関数」。既定は nutpie（PyMC 公式が
推奨。速さの主張は未実測なので根拠は「公式推奨」）。ただし **nutpie は離散潜在変数を含むモデルを引けない**
（compound step が要る）ので、離散潜在があれば PyMC 既定サンプラーへ**フォールバックする**（黙って失敗
させない）。決定性はサンプラーの seed 引数で担保。pymc/nutpie は関数内で遅延 import する（`import
harness.stats.sampling` は未導入でも成功する）。
"""

from __future__ import annotations

import warnings
from typing import Any

from harness.registry import Entry, Registry


def _sample_nutpie(model: Any, *, draws: int, tune: int, chains: int, seed: int) -> Any:  # noqa: ANN401
    """nutpie（Rust 実装の NUTS）でサンプリングして InferenceData を返す。連続潜在のみ対応（既定サンプラー）。"""
    import nutpie

    compiled = nutpie.compile_pymc_model(model)
    return nutpie.sample(compiled, draws=draws, tune=tune, chains=chains, seed=seed)


def _sample_pymc(model: Any, *, draws: int, tune: int, chains: int, seed: int) -> Any:  # noqa: ANN401
    """PyMC 既定サンプラーでサンプリングして InferenceData を返す。離散潜在（compound step）も引ける。"""
    import pymc as pm

    with model:
        return pm.sample(draws=draws, tune=tune, chains=chains, random_seed=seed, progressbar=False)


# kind → サンプリング関数（model → InferenceData）。契約が seed でなく model なので Registry.build は使わず
# resolve して直接呼ぶ。既定は nutpie（PyMC 公式推奨）。説明文は関数の docstring 1 行目から。
SAMPLERS: Registry[Entry] = Registry("サンプラー", catalog="stats samplers")
SAMPLERS.register("nutpie", _sample_nutpie)
SAMPLERS.register("pymc", _sample_pymc)

DEFAULT_SAMPLER = "nutpie"


def _has_discrete_latents(model: Any) -> bool:  # noqa: ANN401  pm.Model
    """モデルに離散の自由変数（整数 dtype の潜在）があるか。nutpie が引けない条件（compound step が要る）。"""
    return any(str(rv.dtype).startswith(("int", "uint")) for rv in model.free_RVs)


def resolve_sampler(requested: str, model: Any) -> str:  # noqa: ANN401  pm.Model
    """要求サンプラーを、モデルの性質を見て確定する。nutpie×離散潜在は PyMC へフォールバック（fail closed）。

    nutpie を要求したが離散潜在があれば pymc を返す（警告つき＝黙って壊れない・黙って別物を返さない）。
    要求が pymc・その他ならそのまま返す（未知 kind の ValueError は run_inference の resolve で出す）。
    """
    if requested == "nutpie" and _has_discrete_latents(model):
        warnings.warn(
            "nutpie は離散潜在変数を引けない（compound step が要る）→ PyMC 既定サンプラーにフォールバックする",
            stacklevel=2,
        )
        return "pymc"
    return requested


def run_inference(
    model: Any,  # noqa: ANN401  pm.Model
    *,
    sampler: str = DEFAULT_SAMPLER,
    draws: int = 1000,
    tune: int = 1000,
    chains: int = 4,
    seed: int,
) -> Any:  # noqa: ANN401  arviz.InferenceData
    """モデルを 1 回サンプリングして InferenceData を返す（宣言→推論の一巡）。

    sampler は SAMPLERS の kind（既定 nutpie）。離散潜在があれば pymc へ自動フォールバック（resolve_sampler）。
    決定性は seed（同じ (model, seed, sampler) なら同じ事後）。draws/tune/chains は少なめの --test 用に上書きする。
    未知 sampler の ValueError は Registry.resolve の 1 か所。
    """
    resolved = resolve_sampler(sampler, model)
    entry = SAMPLERS.resolve(resolved)
    return entry.factory(model, draws=draws, tune=tune, chains=chains, seed=seed)
