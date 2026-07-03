"""experiment.run_experiment の結線テスト（統合）。一気通貫（fold→CV→合否）を確かめる。"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness.ds import data
from harness.ds.experiment import run_experiment
from harness.ds.features import Columns, FeaturePipeline

pytestmark = pytest.mark.integration


def test_run_experiment_end_to_end() -> None:
    df = data.generate_synthetic(n=200, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    estimator = Pipeline(
        [
            ("features", FeaturePipeline([("cols", Columns(["x1", "x2"]))])),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )
    result = run_experiment(df, y, estimator, n_folds=5, seed=1, thresholds={"roc_auc": 0.80}, stratify_by="y")

    assert result.folds.height == 200  # 全行に fold が付く
    assert result.cv.oof_mask.all()  # OOF は全行埋まる
    # 学習可能な合成データなので AUC は 0.8 を超え、passed になる（構成から言える）。
    assert result.metrics["roc_auc"] > 0.8
    assert result.passed
