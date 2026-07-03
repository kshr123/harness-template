"""並べ替え重要度（analysis）の結線テスト：構造上使われない列は重要度 0（構成から厳密）。"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import analysis, cv
from harness.ds.pipeline import build_estimator, build_model

pytestmark = pytest.mark.integration


def _fitted_on_x1_only() -> tuple[object, pl.DataFrame, np.ndarray]:
    rng = np.random.default_rng(0)
    x1 = rng.normal(size=200)
    x = pl.DataFrame({"x1": x1, "x2": rng.normal(size=200)})  # x2 はノイズ
    y = (x1 > 0).astype("int64")  # x1 だけで決まる
    est = build_estimator(
        {"features": [{"kind": "columns", "columns": ["x1"]}]}, build_model({"kind": "logreg"}, seed=0), seed=0
    )
    est.fit(x, y)
    return est, x, y


def test_permutation_importance_zero_for_unused_column() -> None:
    est, x, y = _fitted_on_x1_only()
    imp = analysis.permutation_importance(est, x, y, metric="roc_auc", seed=0, columns=["x1", "x2"])
    d = {r["column"]: r["importance_mean"] for r in imp.to_dicts()}
    assert d["x2"] == 0.0  # 特徴に入らない列を混ぜても予測不変＝重要度 0（構造上厳密）
    assert d["x1"] > 0.0  # 効く列を混ぜると悪化


def test_cv_permutation_importance_runs_over_folds() -> None:
    est_spec = {"features": [{"kind": "columns", "columns": ["x1"]}]}
    rng = np.random.default_rng(0)
    x1 = rng.normal(size=200)
    x = pl.DataFrame({"id": np.arange(200), "x1": x1})
    y = (x1 > 0).astype("int64")
    folds = cv.make_folds(x, n_folds=4, seed=0, stratify_by=None)
    splits = cv.fold_indices(x, folds)
    est = build_estimator(est_spec, build_model({"kind": "logreg"}, seed=0), seed=0)
    result = cv.run_cv(est, x.select("x1"), y.astype("float64"), splits, predict="proba")
    imp = analysis.cv_permutation_importance(
        result, x.select("x1"), y, splits, metric="roc_auc", seed=0, columns=["x1"]
    )
    assert imp.height == 1  # x1 の 1 行
    assert imp["importance_mean"].to_list()[0] > 0.0  # OOF valid 上で効いている
