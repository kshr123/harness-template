"""ハイパラ探索の継ぎ目（*SearchCV でモデルを包む＝sklearn 素通し・DEC-0006）。

- SearchCV を **model 段**に被せるだけ：`cv.run_cv` が fold ごとに clone→fit する既存構造がそのまま
  **nested CV**（外側=run_cv の fold・内側=SearchCV の cv）になり、リークなしのチューニングが追加コード無しで手に入る。
- *SearchCV は `refit=True` で best_estimator_ を持ち、`predict`/`predict_proba`/`classes_` を委譲する
  （`cv._predict` がそのまま使える）。
- param 名は**モデル自身のパラメタ名**（例 "C"・"max_depth"）。model を素で包むので step 接頭辞（model__C）は不要。
- 入り口は config の model 節に `tune:` を足すだけ（`pipeline.build_model` が `build_tuned` で包む）。
- optuna は optional：入っている環境でだけ TUNERS に登録（lightgbm/skops と同じ条件登録・import は遅延）。
"""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from typing import Any

from sklearn.experimental import enable_halving_search_cv  # noqa: F401  HalvingRandomSearchCV の有効化に必須
from sklearn.model_selection import (
    GridSearchCV,
    HalvingRandomSearchCV,
    RandomizedSearchCV,
    StratifiedKFold,
)

from harness.ds.cv import SklearnLike
from harness.registry import Entry, Registry


def _random(seed: int, *, estimator: SklearnLike, params: Any, cv: Any, **extra: Any) -> SklearnLike:  # noqa: ANN401
    """RandomizedSearchCV（候補から n_iter 個を無作為に試す・既定のチューナー）。分布も候補リストも渡せる。"""
    search: SklearnLike = RandomizedSearchCV(estimator, params, cv=cv, refit=True, random_state=seed, **extra)
    return search


def _grid(seed: int, *, estimator: SklearnLike, params: Any, cv: Any, **extra: Any) -> SklearnLike:  # noqa: ANN401
    """GridSearchCV（候補の全組合せを試す・少数候補向け）。探索順に乱数なし（seed は受けて捨てる）。"""
    search: SklearnLike = GridSearchCV(estimator, params, cv=cv, refit=True, **extra)
    return search


def _halving(seed: int, *, estimator: SklearnLike, params: Any, cv: Any, **extra: Any) -> SklearnLike:  # noqa: ANN401
    """HalvingRandomSearchCV（少量データで粗く絞り勝ち残りに資源を集める・候補が多いとき速い）。"""
    search: SklearnLike = HalvingRandomSearchCV(estimator, params, cv=cv, refit=True, random_state=seed, **extra)
    return search


def _optuna_search_cls() -> Any:  # noqa: ANN401
    """OptunaSearchCV を新旧どちらの配置からでも取り出す。

    optuna>=4 で本体から分離され別配布物 `optuna-integration`（module `optuna_integration`）へ移った。
    optuna<4 は `optuna.integration`。両方試し、無ければ導入案内つきで大声で落とす（黙って壊れない）。
    """
    for mod in ("optuna_integration", "optuna.integration"):
        try:
            return importlib.import_module(mod).OptunaSearchCV
        except ModuleNotFoundError, AttributeError:
            continue
    raise ModuleNotFoundError(
        "OptunaSearchCV が見つからない（optuna>=4 は optuna-integration も要る：uv add optuna optuna-integration）"
    )


def _optuna(seed: int, *, estimator: SklearnLike, params: Any, cv: Any, **extra: Any) -> SklearnLike:  # noqa: ANN401
    """OptunaSearchCV（optuna の TPE で探索・optional）。params は optuna の分布（IntDistribution 等）。"""
    # 遅延 import（条件登録済みでも import コストは使う時まで。新旧どちらの配置でも動く）。
    search: SklearnLike = _optuna_search_cls()(estimator, params, cv=cv, refit=True, random_state=seed, **extra)
    return search


def _optuna_available() -> bool:
    """OptunaSearchCV が新旧どちらかの配置で実際に見つかるときだけ True（find_spec("optuna") だけでは不十分）。"""
    for mod in ("optuna_integration", "optuna.integration"):
        try:
            if importlib.util.find_spec(mod) is not None:
                return True
        except ModuleNotFoundError:  # 親（optuna）が無い等でサブモジュール探索が失敗
            continue
    return False


# config の tuner → *SearchCV の工場（sklearn 素通し・DEC-0006）。足したら 1 行。
# 説明文は工場の docstring 1 行目から自動で載る（無ければ登録時に失敗＝DEC-0009）。
TUNERS: Registry[Entry] = Registry(
    "チューナー", catalog="data tuners", extras_hint={"optuna": "optuna optuna-integration"}
)
TUNERS.register("random", _random)
TUNERS.register("grid", _grid)
TUNERS.register("halving", _halving)

# 条件登録：OptunaSearchCV が実際に見つかる環境でだけ TUNERS に足す（find_spec("optuna") だけだと optuna>=4 で
# optuna-integration 未導入時に「登録されるのに使えない」罠になる＝lightgbm と同じく使える語彙だけ見せる）。
if _optuna_available():
    TUNERS.register("optuna", _optuna)


def build_tuned(model: SklearnLike, tune_spec: Mapping[str, Any], *, seed: int, inner_cv: int = 3) -> SklearnLike:
    """config の tune 節から model を *SearchCV で包んで返す（run_cv に渡せばそのまま nested CV）。

    tune_spec = {"tuner": "random"（既定）,
                 "param_grid" か "param_distributions": {パラメタ名: 候補},   # どちらか必須（両方は誤り）
                 ...残りは SearchCV へ素通し（n_iter・scoring 等）}
    内側 cv は `StratifiedKFold(n_splits=inner_cv, shuffle=True, random_state=seed)`＝seed 付きで決定的。
    当面は**分類前提**（回帰でチューニングが要るときは KFold を渡す枝を足す＝拡張点）。
    param 名はモデル自身のパラメタ名（例 "C"）。model を素で包むので step 接頭辞（model__C）は不要。
    """
    spec = dict(tune_spec)
    entry = TUNERS.resolve(spec.pop("tuner", "random"))  # 未知 tuner の ValueError（候補列挙）は resolve の 1 か所
    grid = spec.pop("param_grid", None)
    dist = spec.pop("param_distributions", None)
    if (grid is None) == (dist is None):  # 両方 or どちらも無し
        raise ValueError("tune 節には param_grid か param_distributions のどちらか一方が必要（{パラメタ名: 候補}）")
    inner = StratifiedKFold(n_splits=inner_cv, shuffle=True, random_state=seed)
    tuned: SklearnLike = entry.factory(seed, estimator=model, params=grid if dist is None else dist, cv=inner, **spec)
    return tuned
