"""OOF 予測の深掘り（analysis）の単体テスト：期待値はデータ構成から導出する。"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import analysis

pytestmark = pytest.mark.unit


def test_segment_metrics_classification() -> None:
    seg = pl.Series("s", ["A", "A", "B", "B"])
    y = np.array([1, 1, 0, 0], dtype="int64")
    score = np.array([0.9, 0.9, 0.9, 0.9], dtype="float64")  # 全部 pred=1（閾値0.5）
    out = {r["segment"]: r for r in analysis.segment_metrics(seg, y, score).to_dicts()}
    assert out["A"]["accuracy"] == 1.0  # A は y==1 で当たり
    assert out["B"]["accuracy"] == 0.0  # B は y==0 で全外し
    assert out["A"]["count"] == 2


def test_segment_metrics_regression_residual_mean() -> None:
    seg = pl.Series("s", ["A", "A", "B", "B"])
    yt = np.array([2.0, 3.0, 5.0, 6.0])
    yp = np.array([1.0, 2.0, 6.0, 7.0])  # A の残差 +1 固定・B の残差 −1 固定
    out = {r["segment"]: r for r in analysis.segment_metrics(seg, yt, yp, task="regression").to_dicts()}
    assert out["A"]["residual_mean"] == pytest.approx(1.0)
    assert out["B"]["residual_mean"] == pytest.approx(-1.0)


def test_worst_rows_orders_by_error() -> None:
    df = pl.DataFrame({"id": [0, 1, 2, 3]})
    y = np.array([0, 0, 1, 1], dtype="int64")
    score = np.array([0.0, 0.1, 0.2, 1.0], dtype="float64")  # error=|y-score|: 0, .1, .8, 0
    top = analysis.worst_rows(df, y, score, n=2)
    assert top["id"].to_list()[0] == 2  # 最大誤差の行
    assert top.height == 2
    assert "error" in top.columns


def test_residual_summary_from_construction() -> None:
    r = analysis.residual_summary(np.array([0.0, 0.0]), np.array([3.0, 4.0]))  # 残差 -3, -4
    assert r["mean"] == pytest.approx(-3.5)
    assert r["min"] == pytest.approx(-4.0)
    assert r["max"] == pytest.approx(-3.0)
