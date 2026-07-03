"""回帰経路の結線テスト：run_experiment(task="regression") が端まで通り、残差分析まで届く。

指標の死蔵を防ぐ（回帰指標が config から選べても実験経路が無ければ「入口の無い部品」・DEC-0009）。
期待値は信号:雑音から導出（y=2·x1＋雑音(std 0.1) なら ridge の OOF rmse は 0.2 以下・残差の偏りは小さい）。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import analysis
from harness.ds.experiment import run_experiment
from harness.ds.pipeline import build_estimator, build_model

pytestmark = pytest.mark.integration


def test_regression_path_runs_and_passes() -> None:
    rng = np.random.default_rng(0)
    n = 300
    x1 = rng.normal(size=n)
    df = pl.DataFrame({"id": np.arange(n), "x1": x1})
    y = (2.0 * x1 + rng.normal(scale=0.1, size=n)).astype("float64")  # 信号 2·x1 ＋ 小さい雑音
    est = build_estimator(
        {"features": [{"kind": "columns", "columns": ["x1"]}]}, build_model({"kind": "ridge"}, seed=0), seed=0
    )
    result = run_experiment(df, y, est, n_folds=5, seed=0, thresholds={"rmse": 0.2}, task="regression")

    assert result.passed  # rmse <= 0.2（小さいほど良い・passes が向きで判定）
    assert result.metrics["rmse"] <= 0.2
    assert result.cv.oof_mask.all()  # 全行が OOF に入る

    # エラー分析（残差）まで端で通す：系統的な偏りは小さい。
    resid = analysis.residual_summary(y[result.cv.oof_mask], result.cv.oof[result.cv.oof_mask])
    assert abs(resid["mean"]) <= 0.1
