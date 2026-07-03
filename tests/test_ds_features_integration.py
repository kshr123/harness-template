"""特徴量枠組みが sklearn Pipeline に入り、run_cv で一気通貫に回ることの結線テスト。

FeaturePipeline を "features" 段に入れた estimator を run_cv に通し、fold ごとに clone→train で fit され、
OOF が全行埋まり、学習可能な合成データで妥当な AUC が出ることを確かめる（枠組みが背骨に載る証拠）。
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness.ds import cv, data
from harness.ds.features import Columns, FeaturePipeline, Interactions

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
