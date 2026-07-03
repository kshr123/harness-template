"""(B) 特徴量経路：ENCODERS の "cluster"/"anomaly_score" が build_estimator→run_cv を通ることの結線テスト。

期待値はデータの構成（離れた 2 塊＋原点から遠い外れ行）から導出する。fit-on-train は run_cv の clone-per-fold が
構造で担保する（このテストは「落ちない・列名が追える・決定的」を確かめる。漏れ対策そのものは既存 pca と同一経路）。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.linear_model import LogisticRegression

from harness.ds import cv
from harness.ds.pipeline import build_estimator

pytestmark = pytest.mark.integration


def _model() -> LogisticRegression:
    return LogisticRegression(random_state=0, max_iter=1000)


def _blobs_with_outliers() -> tuple[pl.DataFrame, np.ndarray]:
    # 2 塊（0 付近と 10 付近）＝下流の y を決める構造。末尾に原点から大きく離した外れ行を混ぜる。
    rng = np.random.default_rng(0)
    a = rng.normal(loc=[0.0, 0.0], scale=0.3, size=(30, 2))
    b = rng.normal(loc=[10.0, 10.0], scale=0.3, size=(30, 2))
    out = np.array([[50.0, -50.0], [-40.0, 60.0]])  # 多変量の外れ 2 行
    x = np.vstack([a, b, out])
    y = np.array([0] * 30 + [1] * 30 + [0, 1], dtype=np.float64)
    df = pl.DataFrame({"id": range(len(x)), "x1": x[:, 0], "x2": x[:, 1], "y": y})
    return df, y


def test_cluster_distance_runs_through_cv() -> None:
    df, y = _blobs_with_outliers()
    spec = {
        "features": [{"kind": "columns", "columns": ["x1", "x2"]}],
        "encode": [{"kind": "cluster", "columns": ["x1", "x2"], "n_clusters": 3}],
    }
    est = build_estimator(spec, _model(), seed=0)
    result = cv.run_cv(est, df, y, cv.holdout_indices(50, 12), predict="proba")
    assert result.oof_mask.sum() == 12
    assert bool(np.isfinite(result.oof[result.oof_mask]).all())  # 中央値埋め既定で NaN なく通る
    est.fit(df, y)
    names = list(est[:-1].get_feature_names_out())
    # KMeans.transform は各中心への距離＝n_clusters 列（distance が既定）。
    assert sum(n.startswith("kmeans") for n in names) == 3


def test_cluster_label_single_column() -> None:
    df, y = _blobs_with_outliers()
    spec = {
        "features": [{"kind": "columns", "columns": ["x1", "x2"]}],
        "encode": [{"kind": "cluster", "columns": ["x1", "x2"], "n_clusters": 2, "output": "label"}],
    }
    est = build_estimator(spec, _model(), seed=0).fit(df, y)
    names = list(est[:-1].get_feature_names_out())
    assert "cluster_label" in names  # 番号 1 列
    transformed = est[:-1].transform(df)
    assert transformed.shape[1] == 1  # ちょうど 1 列
    assert set(np.unique(transformed).tolist()) <= {0.0, 1.0}  # n_clusters=2 の整数番号


def test_cluster_encoder_unknown_output() -> None:
    df, y = _blobs_with_outliers()
    spec = {
        "features": [{"kind": "columns", "columns": ["x1", "x2"]}],
        "encode": [{"kind": "cluster", "columns": ["x1", "x2"], "n_clusters": 2, "output": "nope"}],
    }
    with pytest.raises(ValueError, match="output|distance|label"):
        build_estimator(spec, _model(), seed=0).fit(df, y)


def test_anomaly_score_runs_through_cv() -> None:
    df, y = _blobs_with_outliers()
    spec = {
        "features": [{"kind": "columns", "columns": ["x1", "x2"]}],
        "encode": [{"kind": "anomaly_score", "columns": ["x1", "x2"]}],
    }
    est = build_estimator(spec, _model(), seed=0)
    result = cv.run_cv(est, df, y, cv.holdout_indices(50, 12), predict="proba")
    assert result.oof_mask.sum() == 12
    assert bool(np.isfinite(result.oof[result.oof_mask]).all())
    est.fit(df, y)
    names = list(est[:-1].get_feature_names_out())
    assert "anomaly_score" in names  # スコア 1 列
    scores = est[:-1].transform(df)
    assert scores.shape[1] == 1
    # 「大きいほど異常」：仕込んだ外れ 2 行のスコアが塊の中央値より大きい。
    outlier_scores = scores[-2:, 0]
    assert outlier_scores.min() > float(np.median(scores[:-2, 0]))


def test_cluster_and_anomaly_deterministic() -> None:
    df, y = _blobs_with_outliers()
    for enc in (
        {"kind": "cluster", "columns": ["x1", "x2"], "n_clusters": 3},
        {"kind": "anomaly_score", "columns": ["x1", "x2"]},
    ):
        spec = {"features": [{"kind": "columns", "columns": ["x1", "x2"]}], "encode": [enc]}
        a = build_estimator(spec, _model(), seed=0)[:-1].fit_transform(df, y)
        b = build_estimator(spec, _model(), seed=0)[:-1].fit_transform(df, y)
        np.testing.assert_allclose(np.asarray(a), np.asarray(b))  # 同 spec・同 seed で決定的
