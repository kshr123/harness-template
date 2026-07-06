"""T-0075：silhouette の sample_size（大データの O(n²) 回避）。期待値はデータの構成（離れた塊）から導出する。

- 小データ（n ≤ SILHOUETTE_MAX_ROWS）：サンプリング未発動＝sklearn の全件 silhouette と同一値。
- 大データ（n > SILHOUETTE_MAX_ROWS）：seed 固定で 2 回同一（決定的）・分離クラスタなら値が高い。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import unsupervised


def _blobs(n_per_cluster: int, *, seed: int, centers: tuple[float, ...] = (0.0, 10.0)) -> pl.DataFrame:
    """中心距離 ≫ ばらつき の分離クラスタ（silhouette が高くなることが構成から言える）。"""
    rng = np.random.default_rng(seed)
    parts = [rng.normal(loc=[c, c], scale=0.3, size=(n_per_cluster, 2)) for c in centers]
    x = np.vstack(parts)
    return pl.DataFrame({"x1": x[:, 0], "x2": x[:, 1]})


@pytest.mark.unit
def test_silhouette_max_rows_is_conservative_constant() -> None:
    # 定数で明示（受け入れ基準）。O(n²) を抑える保守的な上限＝1 万件。
    assert unsupervised.SILHOUETTE_MAX_ROWS == 10_000


@pytest.mark.unit
def test_cluster_summary_small_matches_full_silhouette() -> None:
    # n=200 ≤ N：sample_size=min(n, N)=n はサンプリング未発動＝全件計算と同一値。
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    df = _blobs(100, seed=0)
    report = unsupervised.cluster_summary(df, method="kmeans", seed=0, n_clusters=2)
    xs = StandardScaler().fit_transform(df.to_numpy())  # 欠損なし＝中央値埋めは恒等・前処理は標準化だけ
    expected = float(silhouette_score(xs, report.labels.to_numpy()))  # sample_size なしの従来値
    assert report.silhouette == pytest.approx(expected)


@pytest.mark.unit
def test_k_scan_small_matches_full_silhouette_at_true_k() -> None:
    # k_scan も同じ守り：小データでは従来（全件）と同一値。真の k=2 の行で照合する。
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    df = _blobs(100, seed=0)
    table = unsupervised.k_scan(df, method="kmeans", k_values=[2, 3], seed=0)
    xs = StandardScaler().fit_transform(df.to_numpy())
    labels = KMeans(n_clusters=2, random_state=0).fit_predict(xs)  # k_scan と同じ前処理・同じ seed
    expected = float(silhouette_score(xs, labels))
    got = table.filter(pl.col("k") == 2)["silhouette"][0]
    assert got == pytest.approx(expected)


@pytest.mark.integration
def test_cluster_summary_sampling_actually_fires(monkeypatch: pytest.MonkeyPatch) -> None:
    # 上限を 100 に縮めて発動を強制：抽出版の値は同データ全件 silhouette と「異なる」＝発動の実測証拠。
    # （sample_size/random_state を外す変異・min→max 変異はこの不一致で赤くなる。）
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    monkeypatch.setattr(unsupervised, "SILHOUETTE_MAX_ROWS", 100)
    df = _blobs(300, seed=0)  # n=600 > 100＝抽出発動
    r1 = unsupervised.cluster_summary(df, method="kmeans", seed=0, n_clusters=2)
    r2 = unsupervised.cluster_summary(df, method="kmeans", seed=0, n_clusters=2)
    assert r1.silhouette is not None
    assert r1.silhouette == r2.silhouette  # 抽出でも seed 固定＝決定的
    xs = StandardScaler().fit_transform(df.to_numpy())
    full = float(silhouette_score(xs, r1.labels.to_numpy()))  # 全件（サンプリングなし）
    assert r1.silhouette != full  # 100 件抽出は全 600 件と別の値＝発動している証拠


@pytest.mark.unit
def test_silhouette_falls_back_to_none_when_sample_loses_a_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    # 極端に不均衡（少数クラスタ 1 件 / 全 1000 件）で 5 件抽出＝少数側が漏れて単一ラベル → sklearn ValueError。
    # 「落とさない」原則どおり None にフォールバックし、seed 固定で決定的であることを検査。
    monkeypatch.setattr(unsupervised, "SILHOUETTE_MAX_ROWS", 5)
    rng = np.random.default_rng(0)
    x = rng.normal(size=(1000, 2))
    labels = np.zeros(1000, dtype=int)
    labels[0] = 1  # 少数クラスタは 1 件だけ（全体では uniq>=2 だが抽出後は縮退しうる）
    assert unsupervised._silhouette(x, labels, seed=0) is None  # ValueError を握って None
    assert unsupervised._silhouette(x, labels, seed=0) is None  # 2 回とも同じ（決定的）


@pytest.mark.integration
def test_cluster_summary_large_is_deterministic_and_high() -> None:
    # n=12_000 > N=10_000：サンプリング発動。random_state=seed で 2 回同一・分離クラスタなので高い。
    df = _blobs(6_000, seed=0)
    assert len(df) > unsupervised.SILHOUETTE_MAX_ROWS  # 前提の明示（サンプリングが発動する規模）
    r1 = unsupervised.cluster_summary(df, method="kmeans", seed=0, n_clusters=2)
    r2 = unsupervised.cluster_summary(df, method="kmeans", seed=0, n_clusters=2)
    assert r1.silhouette is not None and r2.silhouette is not None
    assert r1.silhouette == r2.silhouette  # seed 固定＝決定的（同一値）
    assert r1.silhouette > 0.9  # 中心距離 10 ≫ scale 0.3 の 2 塊＝ほぼ完全分離


@pytest.mark.integration
def test_k_scan_large_is_deterministic_per_k() -> None:
    # 大データでも k_scan は各 k で落ちず・silhouette は seed 固定で 2 回同一（サンプリングが決定的）。
    # inertia は sklearn のスレッド並列で最終桁が揺れる（本タスクの範囲外）＝比較しない。
    df = _blobs(6_000, seed=1)
    t1 = unsupervised.k_scan(df, method="kmeans", k_values=[2, 3], seed=0)
    t2 = unsupervised.k_scan(df, method="kmeans", k_values=[2, 3], seed=0)
    assert t1.select("k", "silhouette").equals(t2.select("k", "silhouette"))
    sil = {int(r["k"]): r["silhouette"] for r in t1.to_dicts()}
    assert sil[2] is not None and sil[2] > 0.9  # 真の k=2 で高い（構成から）
    assert sil[3] is not None and sil[2] > sil[3]  # 塊は 2 つ＝k=3 は割り過ぎで下がる
