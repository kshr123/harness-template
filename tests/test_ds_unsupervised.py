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


def test_cluster_summary_rejects_colliding_label_column() -> None:
    """入力に既に 'cluster' 列（正解ラベル等）があれば ValueError（黙って上書きしない）。"""
    df, true = _two_blobs(20, seed=0)
    df = df.with_columns(cluster=pl.Series("cluster", true))  # 正解セグメントを 'cluster' 列で同乗
    with pytest.raises(ValueError, match="cluster"):
        unsupervised.cluster_summary(df, columns=["x1", "x2"], method="kmeans", seed=0, n_clusters=2)


def test_cluster_summary_label_column_renames_output_and_keeps_truth() -> None:
    """label_column を渡せば出力はその名前で出る。正解 'cluster' 列は特徴から外して残せる。

    正解列を明示的に profile 集計に含めれば、クラスタ別の正解ラベル平均が読める（=正解が消えない）。
    2 つの離れた塊なので予測は正解と 1:1 対応し、各クラスタの cluster_mean は 0.0 か 1.0（構成から導出）。
    """
    n = 20
    df, true = _two_blobs(n, seed=0)
    df = df.with_columns(cluster=pl.Series("cluster", true))  # 正解セグメント（前半 0・後半 1）
    report = unsupervised.cluster_summary(
        df, columns=["x1", "x2", "cluster"], method="kmeans", seed=0, label_column="pred", n_clusters=2
    )
    assert report.labels.name == "pred"
    assert "pred" in report.sizes.columns
    # 完全分離なので各予測クラスタは単一の正解ラベルだけを含む → cluster_mean は 0.0 か 1.0（純度 100%）。
    means = {r["pred"]: r["cluster_mean"] for r in report.profile_by_cluster.to_dicts()}
    assert set(means.keys()) == {0, 1}
    assert set(means.values()) == {0.0, 1.0}  # 予測クラスタ内で正解が混ざらない＝正解の情報が保たれる


def test_anomaly_rows_rejects_colliding_score_column() -> None:
    """入力に既に 'anomaly_score' 列があれば ValueError（黙って置換しない）。"""
    df = pl.DataFrame({"id": [1, 2, 3], "anomaly_score": [0.1, 0.2, 0.3]})
    with pytest.raises(ValueError, match="anomaly_score"):
        unsupervised.anomaly_rows(df, [0.5, 0.4, 0.9], n=2)


def test_anomaly_rows_score_column_renames_output() -> None:
    """score_column を渡せば出力列名がそれになり、降順で上位 n を返す（順位は入力スコアから導出）。"""
    df = pl.DataFrame({"id": [10, 11, 12], "anomaly_score": [0.0, 0.0, 0.0]})  # 同名列があっても別名なら通る
    out = unsupervised.anomaly_rows(df, [0.1, 0.9, 0.5], n=2, score_column="score2")
    assert "score2" in out.columns
    assert out["id"].to_list() == [11, 12]  # スコア 0.9(id11) > 0.5(id12) の順（構成から）
    assert out["score2"].to_list() == [0.9, 0.5]
