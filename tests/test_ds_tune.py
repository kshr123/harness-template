"""tune.py（*SearchCV の継ぎ目）のテスト。期待値はテストデータの構成から導出（金メッキ禁止）。

「良い側を選ぶ」の構成：特徴 1 本の線形分離データ（class0 は x∈[-3,-1]・class1 は x∈[1,3]・マージン 2）。
logreg は C=100（ほぼ無正則化）なら急な境界で正解側に確信度の高い確率＝log loss が小さい。
C=0.001 は L2 罰則が支配して係数がほぼ 0 → 確率が 0.5 近傍 → log loss ≈ ln2 ≈ 0.69。
よって scoring="neg_log_loss" では **C=100 が必ず勝つ**（実装出力の写経でなく構成から導ける）。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from numpy.typing import NDArray
from sklearn.experimental import enable_halving_search_cv  # noqa: F401  HalvingRandomSearchCV の有効化に必須
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, HalvingRandomSearchCV, RandomizedSearchCV, StratifiedKFold

from harness.ds import cv
from harness.ds.pipeline import build_model
from harness.ds.tune import TUNERS, build_tuned


def _separable() -> tuple[pl.DataFrame, NDArray[np.float64]]:
    """特徴 1 本の線形分離データ（各クラス 30 行・マージン 2・決定的）。"""
    x = pl.DataFrame({"f": np.concatenate([np.linspace(-3.0, -1.0, 30), np.linspace(1.0, 3.0, 30)])})
    y = np.array([0.0] * 30 + [1.0] * 30, dtype=np.float64)
    return x, y


# C の 2 候補：0.001（正則化が支配＝確率 0.5 近傍で log loss 大）と 100（分離データを素直に学習）。
_TUNE = {"tuner": "random", "param_grid": {"C": [0.001, 100.0]}, "n_iter": 2, "scoring": "neg_log_loss"}


@pytest.mark.unit
def test_search_picks_good_side() -> None:
    # n_iter=2 で候補 2 つ＝両方を必ず評価 → 構成から良い側（C=100）が選ばれる。
    x, y = _separable()
    search = build_tuned(build_model({"kind": "logreg"}, seed=0), _TUNE, seed=0)
    assert isinstance(search, RandomizedSearchCV)  # tuner: random → sklearn へ素通し
    search.fit(x, y)
    assert search.best_params_["C"] == 100.0
    proba = search.predict_proba(x)  # refit=True → best_estimator_ へ委譲して予測できる
    assert proba.shape == (60, 2)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0)


@pytest.mark.unit
def test_search_is_deterministic_with_seed() -> None:
    # 候補 5 つから n_iter=3 の部分サンプル → 同 seed なら同じ候補・同じ内側分割＝同じ best_params_。
    x, y = _separable()
    spec = {"param_grid": {"C": [0.001, 0.01, 0.1, 1.0, 100.0]}, "n_iter": 3, "scoring": "neg_log_loss"}
    a = build_tuned(build_model({"kind": "logreg"}, seed=0), spec, seed=7)
    b = build_tuned(build_model({"kind": "logreg"}, seed=0), spec, seed=7)
    assert isinstance(a, RandomizedSearchCV) and isinstance(b, RandomizedSearchCV)
    a.fit(x, y)
    b.fit(x, y)
    assert a.best_params_ == b.best_params_


@pytest.mark.integration
def test_nested_cv_seam_with_run_cv() -> None:
    # SearchCV を model 段のまま run_cv へ → 外=run_cv fold・内=SearchCV cv の nested CV が既存構造で成立。
    x, y = _separable()
    tuned = build_tuned(build_model({"kind": "logreg"}, seed=0), _TUNE, seed=0)
    splits = list(StratifiedKFold(n_splits=3, shuffle=True, random_state=0).split(np.zeros(len(y)), y))
    result = cv.run_cv(tuned, x, y, splits)
    assert result.oof_mask.all()
    # 各 fold の内側探索も良い側を選ぶ（構成から導出）＋分離データなので oof も全問正解。
    assert all(est.best_params_["C"] == 100.0 for est in result.estimators)  # type: ignore[attr-defined]
    assert result.oof_metrics["accuracy"] == 1.0
    # cv._predict がそのまま使える＝SearchCV が classes_ / predict_proba を best_estimator_ へ委譲している。
    fitted = result.estimators[0]
    assert np.array_equal(np.asarray(fitted.classes_), np.array([0.0, 1.0]))  # type: ignore[attr-defined]
    pred = cv._predict(fitted, x, "proba")
    assert pred.shape == (60,)  # 二値 → 陽性（ラベル 1）の確率 1 列
    assert ((0.0 <= pred) & (pred <= 1.0)).all()


@pytest.mark.unit
def test_build_model_without_tune_is_unchanged() -> None:
    # tune 無しの spec は従来どおり素の model（SearchCV に包まれない＝既存挙動は不変）。
    model = build_model({"kind": "logreg"}, seed=0)
    assert type(model) is LogisticRegression


@pytest.mark.unit
def test_build_model_with_tune_wraps_and_wires_seed() -> None:
    # build_model の配線：tune 節があれば model を SearchCV で包む。内側 cv は seed 付き StratifiedKFold。
    m = build_model({"kind": "logreg", "tune": {"param_grid": {"C": [0.1, 1.0]}}}, seed=5)
    assert isinstance(m, RandomizedSearchCV)  # tuner 省略 → 既定 random
    assert type(m.estimator) is LogisticRegression
    assert m.estimator.get_params()["random_state"] == 5  # "tune" は model の params に混ざらない
    assert m.random_state == 5
    inner = m.cv
    assert isinstance(inner, StratifiedKFold)
    assert (inner.n_splits, inner.shuffle, inner.random_state) == (3, True, 5)


@pytest.mark.unit
def test_grid_and_halving_tuners() -> None:
    model = build_model({"kind": "logreg"}, seed=0)
    grid = build_tuned(model, {"tuner": "grid", "param_grid": {"C": [0.1, 1.0]}}, seed=0)
    assert isinstance(grid, GridSearchCV)
    halving = build_tuned(model, {"tuner": "halving", "param_grid": {"C": [0.1, 1.0]}}, seed=0)
    assert isinstance(halving, HalvingRandomSearchCV)
    assert halving.random_state == 0


@pytest.mark.unit
def test_unknown_tuner_and_missing_params_raise() -> None:
    model = build_model({"kind": "logreg"}, seed=0)
    with pytest.raises(ValueError, match="未知のチューナー 'nope'.*random"):  # 候補列挙つき
        build_tuned(model, {"tuner": "nope", "param_grid": {"C": [1.0]}}, seed=0)
    with pytest.raises(ValueError, match="param_grid か param_distributions"):
        build_tuned(model, {"tuner": "random"}, seed=0)  # どちらも無し
    with pytest.raises(ValueError, match="どちらか一方"):
        build_tuned(model, {"param_grid": {"C": [1.0]}, "param_distributions": {"C": [1.0]}}, seed=0)  # 両方


@pytest.mark.unit
def test_tuners_have_docstrings() -> None:
    # カタログ規約（DEC-0009）：全チューナーに説明文（sklearn 3 種は常時・optuna は入っていれば条件登録）。
    assert {"random", "grid", "halving"} <= set(TUNERS)
    for kind, entry in TUNERS.items():
        assert entry.description, f"TUNERS['{kind}'] に説明文が無い（カタログに載れない）"
