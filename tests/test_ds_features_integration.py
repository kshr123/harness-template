"""特徴量枠組みが sklearn Pipeline に入り、run_cv で一気通貫に回ることの結線テスト。

FeaturePipeline を "features" 段に入れた estimator を run_cv に通し、fold ごとに clone→train で fit され、
OOF が全行埋まり、学習可能な合成データで妥当な AUC が出ることを確かめる（枠組みが背骨に載る証拠）。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness.ds import cv, data
from harness.ds.features import Columns, CountEncode, FeaturePipeline, GroupAggregate, Interactions, TargetAggregate

pytestmark = pytest.mark.integration


def test_feature_pipeline_runs_through_cv() -> None:
    df = data.generate_synthetic(n=200, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    x = df.select("x1", "x2")
    folds = cv.make_folds(df, n_folds=5, seed=1, stratify_by="y")
    splits = cv.fold_indices(df, folds)

    estimator = Pipeline(
        [
            (
                "features",
                FeaturePipeline([("base", Columns(["x1", "x2"])), ("inter", Interactions([("x1", "x2")]))]),
            ),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )
    result = cv.run_cv(estimator, x, y, splits, predict="proba")

    assert result.oof_mask.all()  # OOF は全行埋まる
    assert len(result.estimators) == 5
    # 合成データは 1.5*x1 - 2*x2 + 雑音(std 0.5) の符号でラベルが決まる（信号:雑音が大きい）。
    # 線形モデルなら OOF の AUC は 0.8 を下回らない（データ構成から言える下限）。
    assert result.oof_metrics["roc_auc"] > 0.8


def test_group_aggregate_fits_on_train_fold_only() -> None:
    # train fold（行 0:4・v=0）と valid fold（行 4:8・v=100）で分布をずらす。
    x = pl.DataFrame({"g": ["A"] * 8, "v": [0.0] * 4 + [100.0] * 4})
    y = np.array([0, 1] * 4, dtype=np.float64)
    est = Pipeline(
        [("features", FeaturePipeline([("agg", GroupAggregate("g", ["v"], ["mean"]))])), ("m", DummyClassifier())]
    )
    result = cv.run_cv(est, x, y, cv.holdout_indices(4, 4), predict="proba")
    agg = result.estimators[0].named_steps["features"].blocks[0][1]  # type: ignore[attr-defined]
    # train fold だけで学習 → group A の mean は 0（valid の 100 が混ざれば 50 になる）。
    assert agg.stats_.filter(pl.col("g") == "A")["v_mean_by_g"].to_list() == [0.0]


def test_count_encode_fits_on_train_fold_only() -> None:
    # train fold（行 0:4＝A2,B2）と全データ（A6,B2）で度数が変わるよう設計。
    x = pl.DataFrame({"c": ["A", "A", "B", "B", "A", "A", "A", "A"]})
    y = np.array([0, 1] * 4, dtype=np.float64)
    est = Pipeline([("features", FeaturePipeline([("cnt", CountEncode(["c"]))])), ("m", DummyClassifier())])
    result = cv.run_cv(est, x, y, cv.holdout_indices(4, 4), predict="proba")
    cnt = result.estimators[0].named_steps["features"].blocks[0][1]  # type: ignore[attr-defined]
    counts = cnt.counts_["c"]
    # train fold（0:4）は A2・B2。漏れていれば A は 6 になる。
    assert counts.filter(pl.col("c") == "A")["c_count"].to_list() == [2]


def test_target_aggregate_fits_on_train_fold_only() -> None:
    # target 系の外側の漏れ検知：run_cv の clone-per-fold で統計が fold の train でだけ学習される。
    # train fold（0:4・y=[0,1,0,1]）と全データ（y に 10 が混ざる）で group 統計が変わる設計。
    g = pl.DataFrame({"g": ["A"] * 8})
    y = np.array([0.0, 1.0, 0.0, 1.0, 10.0, 10.0, 10.0, 10.0])
    est = Pipeline(
        [
            ("features", FeaturePipeline([("ta", TargetAggregate(["g"], ["std"], cv=2, seed=0))])),
            ("m", DummyClassifier(strategy="prior")),
        ]
    )
    result = cv.run_cv(est, g, y, cv.holdout_indices(4, 4), predict="proba")
    ta = result.estimators[0].named_steps["features"].blocks[0][1]  # type: ignore[attr-defined]
    # train fold の y[0:4]=[0,1,0,1] だけで学習 → std は約 0.577（valid の 10 が混ざれば大きくなる）。
    assert ta.stats_.filter(pl.col("g") == "A")["target_std_by_g"].to_list() == pytest.approx(
        [float(np.std([0, 1, 0, 1], ddof=1))]
    )
