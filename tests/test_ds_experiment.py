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


def _estimator() -> Pipeline:
    return Pipeline(
        [
            ("features", FeaturePipeline([("cols", Columns(["x1", "x2"]))])),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )


def test_run_experiment_end_to_end() -> None:
    df = data.generate_synthetic(n=200, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    result = run_experiment(df, y, _estimator(), n_folds=5, seed=1, thresholds={"roc_auc": 0.80}, stratify_by="y")

    assert result.folds.height == 200  # 全行に fold が付く
    assert result.cv.oof_mask.all()  # OOF は全行埋まる
    # 学習可能な合成データなので AUC は 0.8 を超え、passed になる（構成から言える）。
    assert result.metrics["roc_auc"] > 0.8
    assert result.passed


def test_decision_threshold_renamed_and_reaches_eval() -> None:
    # decision_threshold=0.0 → proba >= 0.0 で全行が陽性ラベル → recall はデータの中身によらず 1.0
    # （本当の陽性を全部拾う＝構成から導ける）。値が eval まで届いている証拠。
    df = data.generate_synthetic(n=120, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    result = run_experiment(
        df, y, _estimator(), n_folds=3, seed=1, thresholds={}, stratify_by="y", decision_threshold=0.0
    )
    assert result.metrics["recall"] == 1.0
    # 旧 threshold= は残さない（改名の証拠＝TypeError で使えない）。
    with pytest.raises(TypeError):
        run_experiment(
            df,
            y,
            _estimator(),
            n_folds=3,
            seed=1,
            thresholds={},
            stratify_by="y",
            threshold=0.4,  # type: ignore[call-arg]
        )
