"""教師なし学習（目的変数なしの構造把握）：次元圧縮・クラスタリング・異常検知の探索用途 (A)。

- 第一の出力は構造化レポート（polars/dict）。図は marimo ビュー（notebooks/unsupervised.py）の中だけ（eda と同じ流儀）。
- モデルは sklearn を「使う」（自作ゼロ）。工場は seed 配線と前処理前置（中央値埋め＋標準化）だけ焼く。
- 特徴量用途 (B)（クラスタ番号・異常スコア・圧縮成分を下流モデルの入力にする）は ENCODERS 側（fit-on-train は
  run_cv の clone-per-fold で担保）。ここ (A) は記述的で全データに当てる（結論を学習に戻さないこと）。
- CLUSTERERS/DIMRED/ANOMALY は (A) 探索では関数の method 引数＋CLI（`data cluster/embed/anomaly`）で選ぶ。
  (B) 特徴経路では encode 節の method で `pipeline._cluster`／`_anomaly_score` が同じレジストリから引く。
- 新規行を変換・採点できるか（帰納的か）は `UnsupervisedEntry.inductive` に登録情報として持つ。非帰納の手法
  （t-SNE・HDBSCAN・LOF の novelty=False）を (B) に指定すると、実行前に登録情報から `ValueError` で止める
  （保証段階は (b)：構造で不可能にするのではなく、登録から導いた inductive を実行前に検査して落とす）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
import polars.selectors as cs
from numpy.typing import NDArray
from sklearn.base import BaseEstimator, TransformerMixin

from harness.registry import Entry, Registry


@dataclass(frozen=True, kw_only=True)
class UnsupervisedEntry(Entry):
    """教師なしレジストリ（CLUSTERERS/DIMRED/ANOMALY）の 1 項目。`inductive` を登録情報として持つ。

    inductive：学習後に「学習に使っていない新規行」を変換・採点できるか。(B) 特徴経路は cross-validation で
    fold ごとに fit → 未知行を transform/predict/score するので、inductive=False の手法（hdbscan・sklearn の
    tsne・lof の novelty=False）を (B) に繋ぐと実行時に黙って壊れる。この属性を持たせて接続を実行前に
    `ValueError` で止める（fail closed）。**属性の真偽は挙動で検証する**（帰納性テストが登録から導いた全
    inductive=True の kind に新規行を通す＝申告漏れも嘘の申告も住人が増えた瞬間に検査対象になる。L-021）。
    """

    inductive: bool


# --- (B) 特徴量用途の薄い包み（sklearn に無い隙間だけの「作る」側） ---
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


def _gmm(seed: int, *, n_components: int, **params: Any) -> Any:  # noqa: ANN401  sklearn へ素通し
    """混合ガウス（軟らかい所属・BIC で k を測れる・(A) 探索専用）。n_components 必須。

    中央値埋め＋標準化を前置。random_state=seed で決定的。predict は最尤クラスタ番号（fit_predict で使える）。
    """
    from sklearn.impute import SimpleImputer
    from sklearn.mixture import GaussianMixture
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("cluster", GaussianMixture(n_components=n_components, random_state=seed, **params)),
        ]
    )


def _hdbscan(seed: int, **params: Any) -> Any:  # noqa: ANN401  seed は受けて捨てる（密度ベース＝乱数なし）
    """HDBSCAN（密度クラスタ・k 不要・雑音を -1 に落とす・(A) 探索専用）。新規行に predict できず (B) 不可。

    中央値埋め＋標準化を前置。主なパラメタ：min_cluster_size（塊の最小行数）・min_samples。決定的（乱数なし）。
    """
    from sklearn.cluster import HDBSCAN
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("cluster", HDBSCAN(**params)),
        ]
    )


# method 名 → クラスタリングの工場（前処理前置＋seed）。inductive は新規行に predict できるか（(B) に載るか）。
# kmeans/gmm は predict を持つ＝帰納的。hdbscan は fit_predict のみ＝(A) 専用（(B) に繋ぐと黙って壊れる）。
CLUSTERERS: Registry[UnsupervisedEntry] = Registry("クラスタリング method", catalog="data unsupervised")
CLUSTERERS.register("kmeans", _kmeans, entry_cls=UnsupervisedEntry, inductive=True)
CLUSTERERS.register("gmm", _gmm, entry_cls=UnsupervisedEntry, inductive=True)
CLUSTERERS.register("hdbscan", _hdbscan, entry_cls=UnsupervisedEntry, inductive=False)

# クラスタ数を指定する手法だけの「--k → sklearn の引数名」対応（hdbscan は k 不要＝載せない）。
PARAM_FOR_K: dict[str, str] = {"kmeans": "n_clusters", "gmm": "n_components"}

# silhouette は O(n²)：これを超えたら sample_size で近似する保守的な上限（t-SNE の max_rows=5000 と同じ守り方）。
SILHOUETTE_MAX_ROWS: int = 10_000


def _silhouette(x: NDArray[Any], labels: NDArray[Any], *, seed: int) -> float | None:
    """前処理後の空間でシルエットを測る。SILHOUETTE_MAX_ROWS 超は sample_size で近似（random_state=seed で決定的）。

    sample_size=n（≤ 上限）のときは全件計算と同一（サンプリング未発動）。抽出後に片方クラスタが 0 件になり
    sklearn が ValueError を投げる端ケースは None にフォールバック（落とさない＝欠測表現に寄せる）。
    """
    from sklearn.metrics import silhouette_score

    try:
        return float(silhouette_score(x, labels, sample_size=min(len(labels), SILHOUETTE_MAX_ROWS), random_state=seed))
    except ValueError:  # 抽出後に単一ラベルへ縮退（極端に不均衡な塊）＝採点不能なので None に落とす
        return None


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
    label_column: str = "cluster",
    **params: Any,
) -> ClusterReport:
    """クラスタリングして構造化レポートを返す（クラスタの大きさ・シルエット・クラスタ別の数表）。

    columns 省略時は数値列すべて。全データに当てる探索用途（結論を学習に戻さないこと）。**df に正解ラベル・ID・
    目的変数など「特徴でない」数値列が入っていると、それも黙って距離計算に混ざる**（追加の実害。呼び手が
    columns を明示して除くこと）。最良 k は自動選択しない（k_scan は目安の表・選ぶのは実験側）。
    カテゴリ列の深掘りは eda.category_target_summary に labels を渡せばよい。
    silhouette は SILHOUETTE_MAX_ROWS 行を超えたら sample_size で近似（random_state=seed で決定的）。

    出力列名は label_column（既定 "cluster"）。**df に既に同名の列があれば ValueError**（fail closed。
    黙って上書き・改名しない）。正解ラベルを持つ df をそのまま渡すと、上書きにより正解の情報が
    profile_by_cluster から消えるため（衝突を検査せず通すと起きた実際の破損）。
    """
    if label_column in df.columns:
        raise ValueError(
            f"df に既に '{label_column}' 列がある（cluster_summary の出力列名と衝突する）。"
            "label_column で別名にするか、呼ぶ前に df から列を落とすこと（黙って上書きしない）"
        )
    factory = CLUSTERERS.resolve(method).factory  # 未知 method の ValueError は Registry.resolve の 1 か所
    cols = list(columns) if columns is not None else df.select(cs.numeric()).columns
    x = df.select(cols).to_numpy()
    model = factory(seed, **params)
    labels = np.asarray(model.fit_predict(x))

    n = len(labels)
    vc = pl.Series(label_column, labels).value_counts(sort=True)
    sizes = vc.with_columns(ratio=pl.col("count") / n).sort(label_column)

    transformed = model[:-1].transform(x)  # 前処理後の空間でシルエットを測る
    keep = labels != -1  # hdbscan の雑音 -1 はクラスタでないのでシルエット計算から外す（採点を歪めない）
    uniq = set(labels[keep].tolist())
    silhouette = None
    if len(uniq) >= 2 and int(keep.sum()) > len(uniq):
        silhouette = _silhouette(transformed[keep], labels[keep], seed=seed)

    profile = (
        df.select(cols)
        .with_columns(**{label_column: pl.Series(label_column, labels)})
        .group_by(label_column)
        .agg(
            [pl.col(c).mean().alias(f"{c}_mean") for c in cols]
            + [pl.col(c).median().alias(f"{c}_median") for c in cols]
        )
        .sort(label_column)
    )
    return ClusterReport(
        labels=pl.Series(label_column, labels), sizes=sizes, silhouette=silhouette, profile_by_cluster=profile
    )


def k_scan(
    df: pl.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    method: str = "kmeans",
    k_values: Sequence[int] = range(2, 11),
    seed: int,
) -> pl.DataFrame:
    """k を振って目安の指標表（k・silhouette＋kmeans は inertia・gmm は bic）を返す。**門番にしない**。

    最良 k を自動選択して返す関数は作らない（選ぶのは実験側の判断）。k を要する kmeans/gmm 専用
    （hdbscan は k 不要）。silhouette は大きいほど・inertia/bic は小さいほど良い（向きは呼ぶ側が知る）。
    silhouette は SILHOUETTE_MAX_ROWS 行を超えたら sample_size で近似（random_state=seed で決定的）。
    """
    if method not in PARAM_FOR_K:
        raise ValueError(f"k_scan は kmeans か gmm のみ（method '{method}' は k を取らない）")
    cols = list(columns) if columns is not None else df.select(cs.numeric()).columns
    x = df.select(cols).to_numpy()
    rows: list[dict[str, Any]] = []
    for k in k_values:
        model = CLUSTERERS[method].factory(seed, **{PARAM_FOR_K[method]: k})
        labels = np.asarray(model.fit_predict(x))
        transformed = model[:-1].transform(x)
        sil = _silhouette(transformed, labels, seed=seed) if len(set(labels.tolist())) >= 2 else None
        row: dict[str, Any] = {"k": int(k), "silhouette": sil}
        if method == "kmeans":
            row["inertia"] = float(model[-1].inertia_)
        else:  # gmm
            row["bic"] = float(model[-1].bic(transformed))
        rows.append(row)
    return pl.DataFrame(rows).sort("k")


# --- (A) 次元圧縮：2D 埋め込み（図は marimo・正本は寄与率などの要約） ---


def _pca_embed(seed: int, *, n_components: int = 2, **params: Any) -> Any:  # noqa: ANN401  sklearn へ素通し
    """PCA の 2D 埋め込み（線形・寄与率が出る）。中央値埋め＋標準化を前置。random_state=seed。"""
    from sklearn.decomposition import PCA
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("embed", PCA(n_components=n_components, random_state=seed, **params)),
        ]
    )


def _tsne(seed: int, *, n_components: int = 2, **params: Any) -> Any:  # noqa: ANN401  sklearn へ素通し
    """t-SNE の 2D 地図（非線形・新規行に落とせず (A) 専用）。init="pca" と random_state=seed で安定・決定的。"""
    from sklearn.impute import SimpleImputer
    from sklearn.manifold import TSNE
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    defaults: dict[str, Any] = {"init": "pca"}
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("embed", TSNE(n_components=n_components, random_state=seed, **{**defaults, **params})),
        ]
    )


# method 名 → 2D 埋め込みの工場。inductive は新規行を transform できるか。pca は帰納的・sklearn の tsne は
# transform を持たない＝(A) 専用（新規行を埋め込めない）。帰納的な非線形埋め込みは openTSNE/umap（T-0222）。
DIMRED: Registry[UnsupervisedEntry] = Registry("次元圧縮 method", catalog="data unsupervised")
DIMRED.register("pca", _pca_embed, entry_cls=UnsupervisedEntry, inductive=True)
DIMRED.register("tsne", _tsne, entry_cls=UnsupervisedEntry, inductive=False)


@dataclass(frozen=True)
class EmbedResult:
    """2D 埋め込みの結果。coords は marimo の散布図が使う n 行・to_dict は座標を含めない要約だけ。"""

    coords: pl.DataFrame  # dim1, dim2 の n 行（図の材料）
    method: str
    n_rows: int  # 埋め込んだ行数（抽出時は max_rows）
    columns: list[str]  # 使った列
    explained_variance_ratio: list[float] | None  # pca のみ（tsne は None）
    sampled: bool  # t-SNE で max_rows を超えて等確率抽出したか
    sample_rows: (
        list[int] | None
    )  # 抽出したときの元 df の行位置（marimo で labels/色を coords に揃える）。非抽出は None

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "n_rows": self.n_rows,
            "columns": self.columns,
            "explained_variance_ratio": self.explained_variance_ratio,
            "sampled": self.sampled,
        }


def embed_2d(
    df: pl.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    method: str = "pca",
    seed: int,
    max_rows: int = 5000,
    **params: Any,
) -> EmbedResult:
    """数値列を 2 次元に落として座標＋要約を返す（全データに当てる探索用途）。座標は marimo で見る。

    t-SNE は行数が大きいと遅いので max_rows（既定 5000）を超えたら seed 決定的に等確率抽出し sampled=True を残す
    （門番にせず事実を書く）。columns 省略時は数値列すべて。pca は寄与率を、tsne は None を返す。
    """
    factory = DIMRED.resolve(method).factory  # 未知 method の ValueError は Registry.resolve の 1 か所
    cols = list(columns) if columns is not None else df.select(cs.numeric()).columns
    x_full = df.select(cols).to_numpy()
    sample_rows: list[int] | None = None
    if x_full.shape[0] > max_rows:
        idx = np.sort(np.random.default_rng(seed).choice(x_full.shape[0], size=max_rows, replace=False))
        x = x_full[idx]
        sample_rows = [int(i) for i in idx]  # 元 df の行位置（marimo が labels/色を coords に揃えるため）
    else:
        x = x_full
    model = factory(seed, **params)
    emb = np.asarray(model.fit_transform(x))
    coords = pl.DataFrame({"dim1": emb[:, 0], "dim2": emb[:, 1]})
    evr = None
    if method == "pca":
        evr = [float(v) for v in model[-1].explained_variance_ratio_]
    return EmbedResult(coords, method, x.shape[0], list(cols), evr, sample_rows is not None, sample_rows)


# --- (A) 異常検知：多変量の外れ行（1 列ずつの Tukey 柵＝eda.profile とは役割が違う） ---


def _iforest(seed: int, **params: Any) -> Any:  # noqa: ANN401  sklearn へ素通し
    """IsolationForest（多変量の外れ・(A)(B) 両用）。木なので標準化不要・中央値埋めだけ前置。random_state=seed。"""
    from sklearn.ensemble import IsolationForest
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("anomaly", IsolationForest(random_state=seed, **params)),
        ]
    )


def _lof(seed: int, **params: Any) -> Any:  # noqa: ANN401  seed は受けて捨てる（近傍ベース＝乱数なし）
    """LocalOutlierFactor（局所密度の外れ・(A) 専用）。中央値埋め＋標準化を前置。novelty=False で全データに fit。"""
    from sklearn.impute import SimpleImputer
    from sklearn.neighbors import LocalOutlierFactor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("anomaly", LocalOutlierFactor(**params)),
        ]
    )


# method 名 → 異常検知の工場。inductive は新規行を score できるか。iforest は score_samples を持つ＝帰納的。
# lof は novelty=False＝学習データの外れ度しか出せない＝(A) 専用（帰納的な LOF は lof_novelty・T-0221）。
ANOMALY: Registry[UnsupervisedEntry] = Registry("異常検知 method", catalog="data unsupervised")
ANOMALY.register("iforest", _iforest, entry_cls=UnsupervisedEntry, inductive=True)
ANOMALY.register("lof", _lof, entry_cls=UnsupervisedEntry, inductive=False)


@dataclass(frozen=True)
class AnomalyReport:
    """異常検知の結果。scores は n 行（大きいほど異常）・to_dict は分位要約だけ（全スコアは anomaly_rows で見る）。"""

    scores: pl.Series  # n 行の異常スコア（大きいほど異常）
    method: str
    columns: list[str]
    quantiles: dict[str, float]  # q50/q90/q99/max

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "columns": self.columns, "quantiles": self.quantiles}


def anomaly_scores(
    df: pl.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    method: str = "iforest",
    seed: int,
    **params: Any,
) -> AnomalyReport:
    """多変量の異常スコア（大きいほど異常）を返す。各列は普通でも組み合わせが変な行を拾う。

    sklearn の score は「大きいほど正常」なので符号反転するだけ（閾値・等級化はしない＝事実の報告）。iforest は
    score_samples、lof（novelty=False）は negative_outlier_factor_ から取る。全データに当てる探索用途。
    """
    factory = ANOMALY.resolve(method).factory  # 未知 method の ValueError は Registry.resolve の 1 か所
    cols = list(columns) if columns is not None else df.select(cs.numeric()).columns
    x = df.select(cols).to_numpy()
    model = factory(seed, **params)
    model.fit(x)
    if hasattr(model, "score_samples"):  # iforest（Pipeline が最終段の score_samples を委譲）
        raw = np.asarray(model.score_samples(x))
    else:  # lof novelty=False は score_samples を持たない → 学習データの局所外れ度を読む
        raw = np.asarray(model[-1].negative_outlier_factor_)
    scores = -raw  # 大きいほど異常に揃える
    quantiles = {
        "q50": float(np.quantile(scores, 0.50)),
        "q90": float(np.quantile(scores, 0.90)),
        "q99": float(np.quantile(scores, 0.99)),
        "max": float(np.max(scores)),
    }
    return AnomalyReport(pl.Series("anomaly_score", scores), method, list(cols), quantiles)


def anomaly_rows(
    df: pl.DataFrame, scores: pl.Series | Sequence[float], *, n: int = 20, score_column: str = "anomaly_score"
) -> pl.DataFrame:
    """df の全列＋ score_column をスコア降順で上位 n（analysis.worst_rows と同じ読み方＝「浮いている行」）。

    出力列名は score_column（既定 "anomaly_score"）。**df に既に同名の列があれば ValueError**（fail closed。
    黙って置換しない）。
    """
    if score_column in df.columns:
        raise ValueError(
            f"df に既に '{score_column}' 列がある（anomaly_rows の出力列名と衝突する）。"
            "score_column で別名にするか、呼ぶ前に df から列を落とすこと（黙って置換しない）"
        )
    col = scores if isinstance(scores, pl.Series) else pl.Series(score_column, list(scores))
    return df.with_columns(**{score_column: col}).sort(score_column, descending=True).head(n)
