"""教師なし学習（目的変数なしの構造把握）：次元圧縮・クラスタリング・異常検知の探索用途 (A)。

- 第一の出力は構造化レポート（polars/dict）。図は marimo ビュー（notebooks/unsupervised.py）の中だけ（eda と同じ流儀）。
- モデルは sklearn を「使う」（自作ゼロ・DEC-0008）。工場は seed 配線と前処理前置（中央値埋め＋標準化）だけ焼く。
- 特徴量用途 (B)（クラスタ番号・異常スコア・圧縮成分を下流モデルの入力にする）は ENCODERS 側（fit-on-train は
  run_cv の clone-per-fold で担保）。ここ (A) は記述的で全データに当てる（結論を学習に戻さないこと）。
- CLUSTERERS/DIMRED/ANOMARY は config の種ではなく関数の method 引数＋CLI（`data cluster/embed/anomaly`）で選ぶ。
  ※ T-a では kmeans と cluster_summary のみ。gmm/hdbscan・embed_2d・anomaly は後続タスクで足す。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
import polars.selectors as cs
from numpy.typing import NDArray
from sklearn.base import BaseEstimator, TransformerMixin

ClustererFactory = Callable[..., Any]


# --- (B) 特徴量用途の薄い包み（sklearn に無い隙間だけ・DEC-0008 の「作る」側） ---
# 工場（_cluster/_anomaly_score）は他のエンコーダと同じく pipeline.py に置き、この 2 クラスだけを import する。
# fit-on-train は run_cv の clone-per-fold が構造で担保する（この包みは漏れ対策の分岐を持たない）。


class ClusterLabel(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """クラスタ番号を 1 列で出す薄い包み（predict を transform として出す口が sklearn に無い隙間だけ埋める）。

    KMeans.transform（各中心への距離・素通し）の方が情報量は多い。番号そのものを木モデルに渡したいとき用。
    出力は整数 1 列。カテゴリ扱いにしたければ後段に OneHot を載せず木モデルへ直接渡すのが既定。
    """

    def __init__(self, estimator: Any) -> None:  # noqa: ANN401  KMeans 等の推定器
        self.estimator = estimator

    def fit(self, x: Any, y: object = None) -> ClusterLabel:  # noqa: ANN401
        self.estimator.fit(x)
        self.fitted_ = True  # 末尾 _ の学習済みマーカー（Pipeline の check_is_fitted が見る）
        return self

    def transform(self, x: Any) -> NDArray[Any]:  # noqa: ANN401
        return np.asarray(self.estimator.predict(x)).reshape(-1, 1)

    def get_feature_names_out(self, input_features: object = None) -> NDArray[np.object_]:
        return np.asarray(["cluster_label"], dtype=object)


class AnomalyScore(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """異常スコアを 1 列で出す薄い包み（score_samples を「大きいほど異常」に符号反転して transform で出す）。

    sklearn の score_samples は「大きいほど正常」なので符号を反転するだけ（閾値・等級化はしない＝事実の報告）。
    IsolationForest 等の score_samples を持つ推定器を包む。出力はスコア 1 列。
    """

    def __init__(self, estimator: Any) -> None:  # noqa: ANN401  IsolationForest 等の推定器
        self.estimator = estimator

    def fit(self, x: Any, y: object = None) -> AnomalyScore:  # noqa: ANN401
        self.estimator.fit(x)
        self.fitted_ = True  # 末尾 _ の学習済みマーカー（Pipeline の check_is_fitted が見る）
        return self

    def transform(self, x: Any) -> NDArray[Any]:  # noqa: ANN401
        return (-np.asarray(self.estimator.score_samples(x))).reshape(-1, 1)

    def get_feature_names_out(self, input_features: object = None) -> NDArray[np.object_]:
        return np.asarray(["anomaly_score"], dtype=object)


def _kmeans(seed: int, *, n_clusters: int, **params: Any) -> Any:  # noqa: ANN401  sklearn へ素通し
    """KMeans（球状クラスタ・(A) 探索と (B) 特徴の両用）。n_clusters 必須（既定 8 を黙って使わせない）。

    中央値埋め＋標準化を前置（NaN で落ちない・距離ベースなのでスケールを揃える）。random_state=seed で決定的。
    """
    from sklearn.cluster import KMeans
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("cluster", KMeans(n_clusters=n_clusters, random_state=seed, **params)),
        ]
    )


# method 名 → クラスタリングの工場（前処理前置＋seed）。gmm/hdbscan は T-c で足す。
CLUSTERERS: dict[str, ClustererFactory] = {
    "kmeans": _kmeans,
}


@dataclass(frozen=True)
class ClusterReport:
    """クラスタリングの構造化レポート。labels は n 行（marimo の色付け・(B) 特徴に使える）・to_dict は数表だけ。"""

    labels: pl.Series  # n 行のクラスタ番号（hdbscan の雑音は -1）
    sizes: pl.DataFrame  # cluster, count, ratio
    silhouette: float | None  # クラスタが 1 つ/全部雑音なら None（落とさない）
    profile_by_cluster: pl.DataFrame  # cluster × 数値列の mean/median（クラスタの「顔」）

    def to_dict(self) -> dict[str, Any]:
        return {
            "sizes": self.sizes.to_dicts(),
            "silhouette": self.silhouette,
            "profile_by_cluster": self.profile_by_cluster.to_dicts(),
        }


def cluster_summary(
    df: pl.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    method: str = "kmeans",
    seed: int,
    **params: Any,
) -> ClusterReport:
    """クラスタリングして構造化レポートを返す（クラスタの大きさ・シルエット・クラスタ別の数表）。

    columns 省略時は数値列すべて。全データに当てる探索用途（結論を学習に戻さないこと）。最良 k は自動選択しない
    （k_scan は目安の表・選ぶのは実験側）。カテゴリ列の深掘りは eda.category_target_summary に labels を渡せばよい。
    """
    if method not in CLUSTERERS:
        raise ValueError(f"未知のクラスタリング method '{method}'（{sorted(CLUSTERERS)} のいずれか）")
    cols = list(columns) if columns is not None else df.select(cs.numeric()).columns
    x = df.select(cols).to_numpy()
    model = CLUSTERERS[method](seed, **params)
    labels = np.asarray(model.fit_predict(x))

    n = len(labels)
    vc = pl.Series("cluster", labels).value_counts(sort=True).rename({"cluster": "cluster", "count": "count"})
    sizes = vc.with_columns(ratio=pl.col("count") / n).sort("cluster")

    transformed = model[:-1].transform(x)  # 前処理後の空間でシルエットを測る
    uniq = set(labels.tolist()) - {-1}  # hdbscan の雑音 -1 は除く
    silhouette = None
    if len(uniq) >= 2 and len(uniq) < n:
        from sklearn.metrics import silhouette_score

        silhouette = float(silhouette_score(transformed, labels))

    profile = (
        df.select(cols)
        .with_columns(cluster=pl.Series("cluster", labels))
        .group_by("cluster")
        .agg(
            [pl.col(c).mean().alias(f"{c}_mean") for c in cols]
            + [pl.col(c).median().alias(f"{c}_median") for c in cols]
        )
        .sort("cluster")
    )
    return ClusterReport(
        labels=pl.Series("cluster", labels), sizes=sizes, silhouette=silhouette, profile_by_cluster=profile
    )
