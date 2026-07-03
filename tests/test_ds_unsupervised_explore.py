"""(A) 探索用途の横展開：次元圧縮（embed_2d）・k_scan・gmm/hdbscan・異常検知（anomaly_scores/rows）。

期待値はデータの構成（塊の数・仕込んだ外れ行・相関の強い列）から導出する。正本は構造化レポート・図は marimo の中だけ。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.metrics import adjusted_rand_score

from harness.ds import unsupervised

pytestmark = pytest.mark.unit


def _blobs(centers: list[list[float]], n: int, seed: int, scale: float = 0.3) -> tuple[pl.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    parts = [rng.normal(loc=c, scale=scale, size=(n, 2)) for c in centers]
    x = np.vstack(parts)
    true = np.concatenate([[i] * n for i in range(len(centers))])
    df = pl.DataFrame({"x1": x[:, 0], "x2": x[:, 1]})
    return df, true


# --- クラスタリングの横展開（gmm/hdbscan・k_scan） ---


def test_k_scan_peaks_at_true_k() -> None:
    df, _ = _blobs([[0, 0], [10, 10], [0, 10]], n=40, seed=0)  # 3 塊
    table = unsupervised.k_scan(df, method="kmeans", k_values=range(2, 6), seed=0)
    assert table.columns[:2] == ["k", "silhouette"] or "silhouette" in table.columns
    best_k = table.sort("silhouette", descending=True)["k"][0]
    assert best_k == 3  # 構成どおり 3 塊でシルエット最大


def test_k_scan_only_kmeans_or_gmm() -> None:
    df, _ = _blobs([[0, 0], [10, 10]], n=20, seed=0)
    with pytest.raises(ValueError, match="k_scan|kmeans|gmm"):
        unsupervised.k_scan(df, method="hdbscan", k_values=range(2, 5), seed=0)


def test_gmm_recovers_two_blobs() -> None:
    df, true = _blobs([[0, 0], [10, 10]], n=60, seed=0)
    report = unsupervised.cluster_summary(df, method="gmm", seed=0, n_components=2)
    assert adjusted_rand_score(true, report.labels.to_numpy()) == pytest.approx(1.0)


def test_hdbscan_separates_blobs_and_marks_noise() -> None:
    df, _ = _blobs([[0, 0], [10, 10]], n=60, seed=0)
    # 遠く離れた雑音点を 3 つ足す（密度の低い孤立点＝hdbscan は -1 に落とす）。
    noise = pl.DataFrame({"x1": [40.0, -35.0, 45.0], "x2": [-40.0, 45.0, 40.0]})
    df = pl.concat([df, noise])
    report = unsupervised.cluster_summary(df, method="hdbscan", seed=0, min_cluster_size=15)
    labels = report.labels.to_numpy()
    assert (labels == -1).sum() >= 1  # 孤立点が雑音（-1）になる
    assert len(set(labels.tolist()) - {-1}) == 2  # 雑音を除けば 2 クラスタ
    # 雑音 -1 を採点から外した高いシルエット（雑音を混ぜると押し下げられる）。
    assert report.silhouette is not None and report.silhouette > 0.8


# --- 次元圧縮（embed_2d） ---


def test_pca_embed_first_component_captures_variance() -> None:
    rng = np.random.default_rng(0)
    x1 = rng.normal(size=200)
    df = pl.DataFrame({"x1": x1, "x2": x1 + rng.normal(scale=0.01, size=200)})  # ほぼ一直線
    result = unsupervised.embed_2d(df, method="pca", seed=0)
    assert result.coords.shape == (200, 2)
    assert bool(np.isfinite(result.coords.to_numpy()).all())
    assert result.explained_variance_ratio is not None
    assert result.explained_variance_ratio[0] > 0.9  # 相関が強い＝第1成分が分散の大半
    assert result.sampled is False
    assert result.sample_rows is None  # 非抽出時は coords と df が 1:1（整列口は不要）


def test_tsne_embed_shape_small_n() -> None:
    df, _ = _blobs([[0, 0], [10, 10]], n=50, seed=0)  # 100 行のスモーク
    result = unsupervised.embed_2d(df, method="tsne", seed=0)
    assert result.coords.shape == (100, 2)
    assert result.explained_variance_ratio is None  # tsne は寄与率なし


def test_tsne_embed_samples_when_over_max_rows() -> None:
    df, _ = _blobs([[0, 0], [10, 10]], n=200, seed=0)  # 400 行
    result = unsupervised.embed_2d(df, method="tsne", seed=0, max_rows=100)
    assert result.sampled is True
    assert result.coords.shape == (100, 2)  # max_rows に間引かれる
    assert result.n_rows == 100
    # sample_rows は元 df の行位置（昇順・max_rows 個・範囲内）＝marimo が色分け列を coords に揃える受け口。
    assert result.sample_rows is not None
    assert len(result.sample_rows) == 100
    assert result.sample_rows == sorted(result.sample_rows)
    assert max(result.sample_rows) < 400 and min(result.sample_rows) >= 0


def test_embed_2d_unknown_method() -> None:
    df, _ = _blobs([[0, 0], [10, 10]], n=10, seed=0)
    with pytest.raises(ValueError, match="次元圧縮|method"):
        unsupervised.embed_2d(df, method="nope", seed=0)


# --- 異常検知（anomaly_scores / anomaly_rows） ---


def _blobs_with_planted_outliers() -> pl.DataFrame:
    df, _ = _blobs([[0, 0], [10, 10]], n=50, seed=0)
    df = df.with_row_index("id").with_columns(pl.col("id").cast(pl.Int64))
    # 原点から大きく離した外れ 5 行（id 100..104）。
    out = pl.DataFrame(
        {
            "id": [100, 101, 102, 103, 104],
            "x1": [60.0, -55.0, 70.0, -65.0, 58.0],
            "x2": [-60.0, 55.0, 65.0, -70.0, 62.0],
        }
    )
    return pl.concat([df, out.select(df.columns)])


def test_iforest_ranks_planted_outliers_on_top() -> None:
    df = _blobs_with_planted_outliers()
    report = unsupervised.anomaly_scores(df.drop("id"), method="iforest", seed=0)
    top = unsupervised.anomaly_rows(df, report.scores, n=5)
    assert set(top["id"].to_list()) == {100, 101, 102, 103, 104}  # 仕込んだ 5 行が上位


def test_anomaly_score_direction_is_higher_more_anomalous() -> None:
    df = _blobs_with_planted_outliers()
    report = unsupervised.anomaly_scores(df.drop("id"), method="iforest", seed=0)
    scores = report.scores.to_numpy()
    assert scores[-5:].min() > float(np.median(scores[:-5]))  # 外れ行のスコア > 塊の中央値


def test_lof_scores_have_direction() -> None:
    df = _blobs_with_planted_outliers()
    report = unsupervised.anomaly_scores(df.drop("id"), method="lof", seed=0)
    scores = report.scores.to_numpy()
    assert scores[-5:].max() > float(np.median(scores[:-5]))  # lof でも大きいほど異常
    assert set(report.to_dict()) == {"method", "columns", "quantiles"}


def test_anomaly_unknown_method() -> None:
    df, _ = _blobs([[0, 0], [10, 10]], n=10, seed=0)
    with pytest.raises(ValueError, match="異常検知|method"):
        unsupervised.anomaly_scores(df, method="nope", seed=0)
