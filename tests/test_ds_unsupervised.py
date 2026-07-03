"""教師なし学習（探索用途）のテスト：期待値はデータの構成（離れた塊）から導出する。

正本は構造化レポート（クラスタの大きさ・シルエット・クラスタ別の数表）。図は marimo ビューの中だけ。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.metrics import adjusted_rand_score

from harness.ds import unsupervised

pytestmark = pytest.mark.integration


def _two_blobs(n: int, seed: int) -> tuple[pl.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    a = rng.normal(loc=[0.0, 0.0], scale=0.3, size=(n, 2))
    b = rng.normal(loc=[10.0, 10.0], scale=0.3, size=(n, 2))  # 中心距離 ≫ ばらつき
    x = np.vstack([a, b])
    true = np.array([0] * n + [1] * n)
    df = pl.DataFrame({"x1": x[:, 0], "x2": x[:, 1]})
    return df, true


def test_kmeans_recovers_two_blobs() -> None:
    df, true = _two_blobs(100, seed=0)
    report = unsupervised.cluster_summary(df, method="kmeans", seed=0, n_clusters=2)
    labels = report.labels.to_numpy()
    assert adjusted_rand_score(true, labels) == pytest.approx(1.0)  # 完全分離を当てる（構成から）
    sizes = {r["cluster"]: r["count"] for r in report.sizes.to_dicts()}
    assert set(sizes.values()) == {100}  # 各クラスタ 100 行
    assert report.silhouette is not None and report.silhouette > 0.9  # よく分離＝高シルエット


def test_cluster_summary_to_dict_serializable() -> None:
    import yaml

    df, _ = _two_blobs(30, seed=0)
    d = unsupervised.cluster_summary(df, method="kmeans", seed=0, n_clusters=2).to_dict()
    assert set(d) == {"sizes", "silhouette", "profile_by_cluster"}
    assert "silhouette" in yaml.safe_dump(d, allow_unicode=True)


def test_cluster_summary_unknown_method() -> None:
    df, _ = _two_blobs(10, seed=0)
    with pytest.raises(ValueError, match="未知のクラスタリング|method"):
        unsupervised.cluster_summary(df, method="nope", seed=0, n_clusters=2)
