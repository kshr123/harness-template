"""config から特徴量→エンコード→モデルの sklearn Pipeline を組み立てる（sklearn エンコーダを用意しておく口）。

- 特徴量段（features）：我々の `FeatureBlock`（`BLOCKS`）を横に束ねる。**生のカテゴリ/テキスト列も Columns で通す**
  （Pipeline は逐次で、後段の encode は features の出力しか見えないため）。
- エンコード段（encode）：sklearn のエンコーダ（`ENCODERS`）を `ColumnTransformer` に入れる。**再発明しない**
  が「必要なときに確実に使える」よう、**落ちない・漏れない・決定的**に関わる既定だけ焼き込む：
  OneHot は未知カテゴリでエラーを出さない・Ordinal は未知/欠損を -1・TargetEncoder は非推奨 shuffle/random_state を
  使わず分類=StratifiedKFold(seed)・回帰=KFold(seed) で決定的な OOF（task は model から知る＝is_classifier）・
  KBins/PCA は NaN で落ちるので中央値埋めを前置・Tfidf は null を空文字に。
  性能の好み（分割数・語彙サイズ等）は焼かず sklearn 既定のまま（config の params で上書き）。工場は「既定 | params →
  sklearn クラスにそのまま渡す」薄さで、パラメタを写経しない（再発明でない）。
  例外的に OneHot の `sparse_output=False`・KBins の `encode="ordinal"` は「表現の既定」（列名を追いやすく・下流の
  モデルを問わず合成しやすくするため。安全3要件ではない）。どちらも config の params で上書きできる。
- 漏れ防止は `cv.run_cv` の clone-per-fold（encode の学習も fold の train でだけ起きる）＋ TargetEncoder 内部の OOF。
"""

from __future__ import annotations

import importlib.util
import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import polars as pl
from sklearn.base import is_classifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.decomposition import PCA, TruncatedSVD
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import (
    SelectFromModel,
    SelectKBest,
    VarianceThreshold,
    f_classif,
    f_regression,
    mutual_info_classif,
    mutual_info_regression,
)
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    FunctionTransformer,
    KBinsDiscretizer,
    OneHotEncoder,
    OrdinalEncoder,
    StandardScaler,
    TargetEncoder,
)

from harness.ds.cv import SklearnLike
from harness.ds.features import BLOCKS, FeatureBlock, FeaturePipeline
from harness.registry import Entry, Registry

if TYPE_CHECKING:  # 型注釈だけで使う（実体は _cluster/_anomaly_score が関数内で遅延 import＝循環を避ける）
    from harness.ds.unsupervised import UnsupervisedEntry


def _onehot(seed: int, **params: Any) -> object:  # noqa: ANN401  sklearn へ素通し
    """OneHotEncoder。未知カテゴリで落ちない既定。encode 項目の columns はリスト。"""
    # 落ちない：未知カテゴリでエラーにしない（min_frequency 設定時は稀束ね先へ・無ければ全 0）。
    defaults: dict[str, Any] = {"handle_unknown": "infrequent_if_exist", "sparse_output": False}
    return OneHotEncoder(**{**defaults, **params})


def _ordinal(seed: int, **params: Any) -> object:  # noqa: ANN401
    """OrdinalEncoder。未知・欠損を -1 にする既定。columns はリスト。順序のあるカテゴリ向け。"""
    # 落ちない：未知も欠損も -1（カテゴリは 0..n-1 なので重ならない）。
    defaults: dict[str, Any] = {"handle_unknown": "use_encoded_value", "unknown_value": -1, "encoded_missing_value": -1}
    return OrdinalEncoder(**{**defaults, **params})


def _target(seed: int, *, cv: int = 5, task: str | None = None, **params: Any) -> object:  # noqa: ANN401
    """TargetEncoder（平滑化平均・高カーディナリティ向け）。内部 OOF を分類=StratifiedKFold・回帰=KFold(seed) で決定化。

    task は build_estimator が model から注入する（is_classifier・config に二重に書かせない）。分類は層化＝
    不均衡でも内側の各 fold がクラス比を保つ（sklearn の cv=int 既定と同じ振る舞いを seed で決定化したもの）。
    未指定（None）は従来どおり KFold（連続 y でも落ちない側に倒す・ENCODERS.build を直接使う経路の互換）。
    """
    # 漏れない＋決定的：内部 cross-fitting(OOF) の分割を seed で固定（shuffle/random_state は 1.9 非推奨）。
    if task in ("binary", "multiclass", "classification"):
        inner: KFold | StratifiedKFold = StratifiedKFold(n_splits=cv, shuffle=True, random_state=seed)
    elif task is None or task == "regression":
        inner = KFold(n_splits=cv, shuffle=True, random_state=seed)
    else:  # typo を黙って非層化に落とさない（fail-loud）
        raise ValueError(f"未知の task '{task}'（binary | multiclass | classification | regression のいずれか）")
    return TargetEncoder(cv=inner, **params)


def _bins(seed: int, **params: Any) -> object:  # noqa: ANN401
    """KBinsDiscretizer（分位ビン化・順序値）。NaN で落ちないよう中央値埋めを前置。columns はリスト。"""
    # 落ちない：KBins は NaN で ValueError → train で学習する中央値埋めを前置。決定的：subsample の random_state。
    defaults: dict[str, Any] = {"encode": "ordinal", "random_state": seed}
    return Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("bins", KBinsDiscretizer(**{**defaults, **params}))]
    )


def _pca(seed: int, *, n_components: int, **params: Any) -> object:  # noqa: ANN401  n_components は必須
    """PCA（次元削減）。標準化と中央値埋めを前置。n_components 必須。columns は数値列のリスト。"""
    # 落ちない：PCA は NaN で ValueError → 中央値埋め。統計的必須：標準化を前置。
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("pca", PCA(n_components=n_components, random_state=seed, **params)),
        ]
    )


def _svd(seed: int, *, n_components: int, **params: Any) -> object:  # noqa: ANN401  n_components は必須
    """TruncatedSVD（疎対応の次元圧縮・tfidf の後段や疎な高次元向け）。n_components 必須。columns はリスト。

    PCA と違い scipy 疎行列を**密化せず**受ける（中心化しない＝疎構造を保つ・大語彙 tfidf でも OOM しない）。
    impute/scale は前置しない（前置すると疎が密化される。tfidf/onehot の出力に NaN は無い。NaN があり得る
    数値列なら pca か impute 併記を使う）。encode 節の書き方：{kind: svd, columns: [...], n_components: k}。
    tfidf→svd の直列は encode 段（ColumnTransformer＝並列）では書けないので、Python で
    Pipeline([tfidf, svd, model]) を組む（両方 ENCODERS.build で作れる）。決定的：random_state=seed。
    """
    return TruncatedSVD(n_components=n_components, random_state=seed, **params)


def _reject_non_inductive(registry: Registry[UnsupervisedEntry], method: str, *, encoder: str) -> UnsupervisedEntry:
    """(B) 特徴経路のエンコーダが method を受けたとき、登録情報で inductive を確かめて Entry を返す。

    inductive=False（新規行を変換・採点できない手法）を (B) に繋ぐと、run_cv が fold の train で fit した後に
    valid の未知行を通す段で実行時に黙って壊れる。それを実行前に kind を名指しした `ValueError` で止める
    （fail closed）。使える kind の一覧（inductive=True だけ）を案内に載せる。
    """
    entry = registry.resolve(method)  # 未知 method の ValueError は Registry.resolve の 1 か所
    if not entry.inductive:
        usable = sorted(k for k in registry if registry[k].inductive)
        raise ValueError(
            f"{encoder} エンコーダに method '{method}' は使えない（inductive=False＝学習後に新規行を"
            f"変換・採点できない）。(B) 特徴経路は fold ごとに fit → 未知行を通すため。使えるのは {usable}"
        )
    return entry


def _cluster(seed: int, *, method: str = "kmeans", output: str = "distance", **params: Any) -> object:  # noqa: ANN401
    """クラスタリングをエンコーダに（(B) 特徴量）。method で CLUSTERERS から工場を引く（直書きしない）。

    output="distance"（既定）＝各中心への距離を列に（method の推定器が transform を持つとき＝kmeans。距離が
    定義できない手法は fail closed）。output="label"＝クラスタ番号 1 列（ClusterLabel の薄い包み・predict を使う）。
    method 未指定は kmeans（既存 config 互換）。inductive=False の method（hdbscan 等）は実行前に ValueError。
    クラスタ数の指定は method の工場に依る（kmeans=n_clusters・gmm=n_components を params で渡す）。
    fit-on-train は run_cv の clone-per-fold で担保。決定的：seed は工場に配線される。
    """
    from harness.ds.unsupervised import CLUSTERERS, ClusterLabel

    entry = _reject_non_inductive(CLUSTERERS, method, encoder="cluster")
    estimator = entry.factory(seed, **params)  # 前処理前置＋seed 済みの Pipeline（unsupervised.py が正本）
    if output == "label":
        return ClusterLabel(estimator)  # transform=predict（新規行のクラスタ番号 1 列）
    if output == "distance":
        if not hasattr(estimator, "transform"):  # 中心への距離は transform を持つ手法のみ（kmeans 系）
            raise ValueError(
                f"cluster output='distance' は method '{method}' で使えない（transform を持たない＝"
                "中心への距離が定義できない）。output='label' にするか、距離を持つ method を使う"
            )
        return estimator
    raise ValueError(f"未知の cluster output '{output}'（distance か label）")


def _anomaly_score(seed: int, *, method: str = "iforest", **params: Any) -> object:  # noqa: ANN401
    """異常スコアを 1 列出すエンコーダ（(B) 特徴量・大きいほど異常）。method で ANOMALY から工場を引く。

    符号を「大きいほど異常」に揃えるのは工場ではなく採点する側：(A) は anomaly_scores・(B) はこの
    AnomalyScore の包み（工場は sklearn の生の向きの推定器を返すだけ）。向きの契約は
    test_anomaly_sign_contract が全 kind に強制する。多変量の外れ（各列は普通でも組み合わせが変な行）
    を拾う。1 列ずつの
    Tukey 柵（eda.profile の n_outliers）とは役割が違う。method 未指定は iforest（既存 config 互換）。
    inductive=False の method（lof の novelty=False 等）は実行前に ValueError。決定的：seed は工場に配線される。
    """
    from harness.ds.unsupervised import ANOMALY, AnomalyScore

    entry = _reject_non_inductive(ANOMALY, method, encoder="anomaly_score")
    estimator = entry.factory(seed, **params)  # 前処理前置＋seed 済みの Pipeline（unsupervised.py が正本）
    return AnomalyScore(estimator)  # transform=符号を揃えた score_samples（新規行の異常スコア 1 列）


def _fill_text(s: pl.Series) -> pl.Series:  # モジュール関数（lambda は pickle 不可）
    return s.fill_null("")


def _to_numpy(x: Any) -> Any:  # noqa: ANN401  polars/pandas/scipy 疎行列/numpy を受ける
    """特徴量段の出力を numpy 配列に揃える（model 直前の唯一の numpy⇔polars 境界・DESIGN の方針）。

    列名を落とすので、名前付き入力で feature_names_in_ を設定できないモデル（LightGBM 等）でも Pipeline が壊れない。
    scipy 疎行列（tfidf 等の出力）は**疎のまま通す**：logreg・木・RF・LightGBM は疎を直接受けるし、toarray で密化すると
    大語彙 tfidf（例 50k 語 × 50 万行）で OOM になる。疎に列名は付かないので、この関数の目的（列名を落とす）も疎には
    元々不要。疎を受けないモデル（HistGradientBoosting）は工場側で直前に密化する（_dense_model）＝密化を必要な所へ寄せる。
    """
    if hasattr(x, "toarray"):  # scipy 疎行列（.to_numpy は無い）→ 密化せずそのまま
        return x
    return x.to_numpy() if hasattr(x, "to_numpy") else np.asarray(x)


def _densify(x: Any) -> Any:  # noqa: ANN401  疎行列だけ密化（それ以外は素通し）
    return x.toarray() if hasattr(x, "toarray") else x


def _dense_model(model: SklearnLike) -> SklearnLike:
    """疎を受けないモデル（HistGradientBoosting）の直前に密化段を挟む薄い包み。

    _to_numpy が疎を素通しするようになったため、疎非対応モデルは工場側で密化する（tfidf 等との組合せを壊さない）。
    密化は「疎を受けないモデル」だけに寄せる＝疎対応モデルは大語彙でも OOM しないまま。
    """
    dense: SklearnLike = Pipeline([("densify", FunctionTransformer(_densify, accept_sparse=True)), ("model", model)])
    return dense


def _tfidf(seed: int, **params: Any) -> object:  # noqa: ANN401
    """TfidfVectorizer（テキスト特徴量）。null を空文字に埋めて前置。columns は文字列 1 本（リストにしない）。"""
    # 落ちない：null テキストで TfidfVectorizer は落ちる → 空文字埋めを前置。
    return Pipeline(
        [
            ("fill", FunctionTransformer(_fill_text, feature_names_out="one-to-one")),
            ("tfidf", TfidfVectorizer(**params)),
        ]
    )


def _scale(seed: int, **params: Any) -> object:  # noqa: ANN401  seed は受けて捨てる（決定的な変換＝乱数なし）
    """数値を欠損補完（中央値）してから標準化（kNN・線形の NaN 穴を塞ぐ）。columns は数値列のリスト。"""
    # 落ちない：StandardScaler は NaN を通すが下流の kNN・線形が落ちる → 中央値埋めを前置。params は scale へ素通し。
    return Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler(**params))])


def _impute(seed: int, **params: Any) -> object:  # noqa: ANN401  seed は受けて捨てる（決定的な変換＝乱数なし）
    """数値の欠損を補完（既定=中央値）。埋めるだけが要るとき。strategy は params で選べる。columns はリスト。"""
    defaults: dict[str, Any] = {"strategy": "median"}
    return SimpleImputer(**{**defaults, **params})


def _missing_flags(seed: int, **params: Any) -> object:  # noqa: ANN401  seed は受けて捨てる（決定的な変換＝乱数なし）
    """欠損の有無を 0/1 特徴にする（欠損自体が予測に効く場合）。columns は数値列のリスト。

    features="all" を既定に焼く：欠損の無い列でも 0 の列を出す＝出力列数が入力列数と一致して安定
    （既定の "missing-only" は train の欠損状況で列数が変わり ColumnTransformer で扱いにくい）。
    注意：ColumnTransformer では指定列は flag 列に**置き換わる**（元の値は model に届かない）。値も残すなら
    同じ列に `impute`（か `scale`）を併記する（補完値＋欠損フラグの両方が特徴になる）。
    """
    defaults: dict[str, Any] = {"features": "all"}
    return MissingIndicator(**{**defaults, **params})


# config の kind → sklearn エンコーダの工場（落ちない・漏れない・決定的の既定つき）。足したら 1 行。
# 説明文は工場の docstring 1 行目から自動で載る（無ければ登録時に失敗）。
ENCODERS: Registry[Entry] = Registry("エンコーダ", catalog="data encoders")
ENCODERS.register("onehot", _onehot)
ENCODERS.register("ordinal", _ordinal)
ENCODERS.register("target", _target)
ENCODERS.register("bins", _bins)
ENCODERS.register("pca", _pca)
ENCODERS.register("svd", _svd)  # 疎対応の次元圧縮（tfidf の後段＝テキスト経路の穴埋め・T-0081）
ENCODERS.register("tfidf", _tfidf)
ENCODERS.register("cluster", _cluster)  # (B) クラスタとの距離/番号を特徴に（教師なし・DESIGN §4）
ENCODERS.register("anomaly_score", _anomaly_score)  # (B) 多変量の異常スコアを特徴に（教師なし・DESIGN §5）
ENCODERS.register("scale", _scale)  # 数値前処理の標準入口（T-0054・kNN・線形の NaN 穴を塞ぐ）
ENCODERS.register("impute", _impute)
ENCODERS.register("missing_flags", _missing_flags)


# --- 特徴選択（select 節・to_numpy と model の間の 1 段・T-0064） ---
def _variance_threshold(seed: int, **params: Any) -> object:  # noqa: ANN401  seed は受けて捨てる（決定的・教師なし）
    """分散が閾値以下の列を落とす（定数列など）。教師なし・y 不要。既定 threshold=0.0（sklearn 既定のまま）。"""
    return VarianceThreshold(**params)


# score_func の文字列 → sklearn 関数の写像（config は文字列で選ぶ・関数を直接書かせない）。
_SCORE_FUNCS: dict[str, Any] = {
    "f_classif": f_classif,
    "f_regression": f_regression,
    "mutual_info_classif": mutual_info_classif,
    "mutual_info_regression": mutual_info_regression,
}


def _selectkbest(seed: int, *, score_func: str = "f_classif", k: int = 10, **params: Any) -> object:  # noqa: ANN401
    """単変量スコア上位 k 列を選ぶ（SelectKBest）。score_func は f_classif（既定）/f_regression/mutual_info_*。

    score_func は文字列で選ぶ：分類＝"f_classif"/"mutual_info_classif"・回帰＝"f_regression"/"mutual_info_regression"。
    y を使うが Pipeline が fit(y) を伝えるので追加配線は不要（run_cv が fold の train の y を渡す＝リークなし）。
    mutual_info_* は乱数を使うので seed を配線して決定化（f_classif/f_regression は決定的＝seed 不使用）。
    注意：k（既定 10）が特徴数より多いと sklearn は警告のみで全列を返す（no-op）＝特徴数に合わせて k を決める。
    """
    if score_func not in _SCORE_FUNCS:
        raise ValueError(f"未知の score_func '{score_func}'（{sorted(_SCORE_FUNCS)} のいずれか）")
    fn = _SCORE_FUNCS[score_func]
    if score_func in (
        "mutual_info_classif",
        "mutual_info_regression",
    ):  # 決定的：乱数を使う score_func だけ seed を焼く
        from functools import partial

        fn = partial(fn, random_state=seed)
    return SelectKBest(score_func=fn, k=k, **params)


def _from_model(seed: int, *, estimator: Any | None = None, **params: Any) -> object:  # noqa: ANN401
    """モデルの重要度でしきい選択（SelectFromModel）。estimator は model spec（{kind,...}）で分類/回帰を選べる。

    estimator に model 節の dict（例 {"kind": "ridge"}）を渡すと build_model で作る＝config(YAML) から回帰選択器も
    組める。既定は LogisticRegression（分類）＝回帰 y には分類器が fit で落ちるので estimator に回帰モデルを指定する。
    y を使うが Pipeline が fit(y) を伝える（run_cv が fold の train の y を渡す＝リークなし）。
    """
    if estimator is None:
        base: SklearnLike = LogisticRegression(random_state=seed, max_iter=1000)
    elif isinstance(estimator, Mapping):  # config 由来の model spec（{kind,...}）を build_model で解決
        base = build_model(estimator, seed=seed)
    else:  # 既に sklearn 推定器オブジェクト（Python から直接呼ぶ場合）
        base = estimator
    return SelectFromModel(base, **params)


# config の select 節の kind → 特徴選択の工場（sklearn 素通し）。足したら 1 行。
SELECTORS: Registry[Entry] = Registry("特徴選択", catalog="data selectors")
SELECTORS.register("variance_threshold", _variance_threshold)
SELECTORS.register("selectkbest", _selectkbest)
SELECTORS.register("from_model", _from_model)


def _logreg(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401  sklearn へ素通し
    """ロジスティック回帰（線形・二値分類の既定モデル）。config の model 節に kind: logreg。"""
    # 決定的：random_state=seed。落ちない：収束しないと警告になるので max_iter を厚めに既定化（params で上書き可）。
    defaults: dict[str, Any] = {"random_state": seed, "max_iter": 1000}
    model: SklearnLike = LogisticRegression(**{**defaults, **params})  # sklearn は型なし＝Any を明示的に受ける
    return model


def _ridge(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401  sklearn へ素通し
    """リッジ回帰（線形・回帰の既定モデル）。config の model 節に kind: ridge・task: regression と併せて使う。"""
    from sklearn.linear_model import Ridge

    model: SklearnLike = Ridge(**{"random_state": seed, **params})  # sklearn は型なし＝Any を明示的に受ける
    return model


def _dummy(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """多数派の事前確率を返すだけの分類ベースライン（学習が効いているかの基準）。task: classification。

    既定 strategy="prior"（predict_proba がクラス比率を返す）。"most_frequent"/"stratified"/"uniform"/"constant" に
    params で上書き可。学習モデルはまずこの基準を上回って初めて「効いている」と言える。
    決定的：random_state=seed を配線する（prior/most_frequent には無害・stratified/uniform の再現に効く）。
    """
    model: SklearnLike = DummyClassifier(**{"strategy": "prior", "random_state": seed, **params})
    return model


def _dummy_reg(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401  seed は受けて捨てる（決定的モデル）
    """平均を返すだけの回帰ベースライン。task: regression。

    既定 strategy="mean"。"median"/"quantile"（quantile= 併記）/"constant"（constant= 併記）に params で上書き可。
    回帰モデルの baseline（この基準を上回る改善が無いなら学習が効いていない）。
    """
    model: SklearnLike = DummyRegressor(**{"strategy": "mean", **params})
    return model


# --- 分類（追加） ---
def _knn(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401  seed は受けて捨てる（距離ベース＝乱数なし）
    """k 近傍分類（距離ベース・非線形の素直なベースライン）。task: classification。

    主なハイパラ：n_neighbors・weights（uniform/distance）・metric。目的関数は無し（距離を metric で変える）。
    ※スケールの違う数値列は encode 段で標準化してから使う（距離が歪むため）。
    """
    from sklearn.neighbors import KNeighborsClassifier

    model: SklearnLike = KNeighborsClassifier(**params)
    return model


def _tree(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """決定木分類（説明しやすい非線形・過学習しやすい）。task: classification。

    主なハイパラ：max_depth・min_samples_leaf・class_weight（不均衡は "balanced"）。
    目的関数：criterion="gini"（既定）/"entropy"/"log_loss"。params はそのまま sklearn へ。
    """
    from sklearn.tree import DecisionTreeClassifier

    model: SklearnLike = DecisionTreeClassifier(**{"random_state": seed, **params})
    return model


def _random_forest(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """ランダムフォレスト分類（非線形・交互作用に強い定番）。task: classification。

    主なハイパラ：n_estimators・max_depth・max_features・class_weight（不均衡は "balanced"）。
    目的関数：criterion="gini"（既定）/"entropy"/"log_loss"。params はそのまま sklearn へ。
    """
    from sklearn.ensemble import RandomForestClassifier

    model: SklearnLike = RandomForestClassifier(**{"random_state": seed, **params})
    return model


def _hist_gb(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """勾配ブースティング分類（sklearn HistGradientBoosting・表形式の第一候補）。task: classification。

    主なハイパラ：learning_rate・max_iter・max_depth・l2_regularization・class_weight。NaN をそのまま扱える
    （穴埋め前処理が不要）。目的関数は log_loss 固定（sklearn の仕様）。params はそのまま sklearn へ。
    """
    from sklearn.ensemble import HistGradientBoostingClassifier

    model: SklearnLike = HistGradientBoostingClassifier(**{"random_state": seed, **params})
    return _dense_model(model)  # HistGradientBoosting は疎を受けない＝直前で密化（tfidf 等との組合せを守る）


# --- 回帰（追加） ---
def _lasso(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """Lasso 回帰（L1 正則化＝不要な係数を 0 にして特徴選択を兼ねる）。task: regression。

    主なハイパラ：alpha（大きいほど係数が減る）・max_iter。目的関数は二乗誤差固定（正則化が L1）。
    収束警告が出たら alpha か max_iter を動かす。params はそのまま sklearn へ。
    """
    from sklearn.linear_model import Lasso

    model: SklearnLike = Lasso(**{"random_state": seed, **params})
    return model


def _elasticnet(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """ElasticNet 回帰（L1/L2 混合・相関の強い特徴群に強い）。task: regression。

    主なハイパラ：alpha・l1_ratio（0=Ridge 寄り・1=Lasso 寄り）。目的関数は二乗誤差固定（L1/L2 混合）。
    params はそのまま sklearn へ。
    """
    from sklearn.linear_model import ElasticNet

    model: SklearnLike = ElasticNet(**{"random_state": seed, **params})
    return model


def _random_forest_reg(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """ランダムフォレスト回帰（非線形・交互作用に強い定番）。task: regression。

    主なハイパラ：n_estimators・max_depth・max_features。
    目的関数：criterion="squared_error"（既定）/"absolute_error"（外れ値に強い）/"poisson"。
    """
    from sklearn.ensemble import RandomForestRegressor

    model: SklearnLike = RandomForestRegressor(**{"random_state": seed, **params})
    return model


def _hist_gb_reg(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """勾配ブースティング回帰（sklearn HistGradientBoosting・表形式の第一候補）。task: regression。

    主なハイパラ：learning_rate・max_iter・max_depth・l2_regularization。NaN をそのまま扱える。
    目的関数：loss="squared_error"（既定）/"absolute_error"/"poisson"/"gamma"/"quantile"（quantile=0.9 等を併記）。
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    model: SklearnLike = HistGradientBoostingRegressor(**{"random_state": seed, **params})
    return _dense_model(model)  # HistGradientBoosting は疎を受けない＝直前で密化（tfidf 等との組合せを守る）


def _poisson_reg(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401  seed は受けて捨てる（lbfgs＝決定的）
    """ポアソン回帰（件数・頻度など非負ターゲットの線形基準・対数リンクの GLM）。task: regression。

    config の model 節に kind: poisson_reg。主なハイパラ：alpha（L2 正則化・sklearn 既定 1.0）・max_iter。
    y は非負が前提（負値は fit で落ちる）・予測は常に正（exp リンク）。木側の対抗は hist_gb_reg の
    loss="poisson"（重複を避け、こちらは線形の基準として使う）。params はそのまま sklearn へ。
    """
    from sklearn.linear_model import PoissonRegressor

    model: SklearnLike = PoissonRegressor(**params)
    return model


def _quantile_reg(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401  seed は受けて捨てる（線形計画＝決定的）
    """分位点回帰（中央値や上位分位を直接当てる線形モデル・pinball 損失）。task: regression。

    config の model 節に kind: quantile_reg・quantile: 0.9 など（既定 0.5＝中央値）。**alpha は L1 正則化**
    （sklearn の語彙・分位ではない。既定 1.0 は強めなので alpha: 0.0 から調整が無難）。評価は eval の
    pinball 系指標と分位を揃える。木側の対抗は hist_gb_reg の loss="quantile"。params はそのまま sklearn へ。
    """
    from sklearn.linear_model import QuantileRegressor

    model: SklearnLike = QuantileRegressor(**params)
    return model


# --- LightGBM（optional extra `lightgbm`・末尾で条件登録） ---
def _lightgbm(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """LightGBM 分類（大規模・カテゴリ多めで hist_gb より速く強いことが多い）。task: classification。

    主なハイパラ：n_estimators・num_leaves・learning_rate・scale_pos_weight（不均衡）。
    目的関数：objective="binary"（既定）等の文字列。導入は `uv sync --extra lightgbm`。verbosity=-1 を既定に焼く。
    """
    from lightgbm import LGBMClassifier  # 遅延 import（未導入でもモジュールは壊れない）

    model: SklearnLike = LGBMClassifier(**{"random_state": seed, "verbosity": -1, **params})
    return model


def _lightgbm_reg(seed: int, **params: Any) -> SklearnLike:  # noqa: ANN401
    """LightGBM 回帰（表形式の大規模データで強い）。task: regression。

    主なハイパラ：n_estimators・num_leaves・learning_rate。目的関数：objective="regression"（既定）/
    "regression_l1"（MAE）/"huber"/"quantile"（alpha=）/"poisson"/"tweedie"。導入は `uv sync --extra lightgbm`。
    """
    from lightgbm import LGBMRegressor

    model: SklearnLike = LGBMRegressor(**{"random_state": seed, "verbosity": -1, **params})
    return model


# 実験の課題語彙（multiclass を含む）。MODELS の task 属性は classification|regression のまま
# （多クラスかどうかはモデル種でなく fit 時のラベルのクラス数で決まる＝build_model が正規化して突き合わせる）。
ModelTask = Literal["classification", "multiclass", "regression"]

# optional 依存の kind → 導入すべき extra 名（未導入で使われたときのヒント）。
OPTIONAL_MODEL_EXTRAS: dict[str, str] = {"lightgbm": "lightgbm", "lightgbm_reg": "lightgbm"}

# config の kind → モデルの登録（工場＋task）。sklearn を足すときはここに 1 行。
# task は Entry.task に持ち、build_model が config の task と突き合わせる（回帰モデル×分類 task を実行前に止める）。
# 説明文は factory の docstring 1 行目（`uv run data models` に載る・test_catalog が必須検査）。
# optional 依存（lightgbm 等）のモデルはファイル末尾で「入っていれば登録」する（§5 条件登録）。
MODELS: Registry[Entry] = Registry("モデル", catalog="data models", extras_hint=OPTIONAL_MODEL_EXTRAS)
# 分類
MODELS.register("dummy", _dummy, task="classification")  # 何も学習しない baseline（比較の基準・T-0062）
MODELS.register("logreg", _logreg, task="classification")
MODELS.register("knn", _knn, task="classification")
MODELS.register("tree", _tree, task="classification")
MODELS.register("random_forest", _random_forest, task="classification")
MODELS.register("hist_gb", _hist_gb, task="classification")
# 回帰
MODELS.register("dummy_reg", _dummy_reg, task="regression")  # 何も学習しない baseline（比較の基準・T-0062）
MODELS.register("ridge", _ridge, task="regression")
MODELS.register("lasso", _lasso, task="regression")
MODELS.register("elasticnet", _elasticnet, task="regression")
MODELS.register("random_forest_reg", _random_forest_reg, task="regression")
MODELS.register("hist_gb_reg", _hist_gb_reg, task="regression")
MODELS.register("poisson_reg", _poisson_reg, task="regression")  # 件数・頻度の線形基準（T-0081）
MODELS.register("quantile_reg", _quantile_reg, task="regression")  # 分位ターゲットの線形基準（T-0081）

# 条件登録：ライブラリが入っている環境でだけ MODELS に足す（`data models` は使える語彙だけを見せる）。
# import コストゼロの存在確認（find_spec）で登録を切り替える。工場本体は関数内 import なので未導入でも壊れない。
if importlib.util.find_spec("lightgbm") is not None:
    MODELS.register("lightgbm", _lightgbm, task="classification")
    MODELS.register("lightgbm_reg", _lightgbm_reg, task="regression")


def build_calibrated(model: SklearnLike, calibrate_spec: Mapping[str, Any], *, seed: int) -> SklearnLike:
    """config の calibrate 節から model を CalibratedClassifierCV で包んで返す（確率の較正・tune と同じ流儀）。

    calibrate_spec = {"method": "sigmoid"（既定）| "isotonic", "cv": 3（既定）, ...残りは CalibratedClassifierCV へ}。
    内側 cv は `StratifiedKFold(shuffle=True, random_state=seed)`＝seed 付きで決定的（分類前提・build_tuned と同じ）。
    model 段に被せるので run_cv の clone-per-fold で較正も fold の train でだけ起きる（リークなし）。
    method/cv 以外のキー（ensemble 等）は CalibratedClassifierCV へ素通し＝**未知キー/typo は TypeError で即死**
    （build_tuned と対称・黙って既定に落とさない＝fail-loud）。
    """
    spec = dict(calibrate_spec)
    inner = StratifiedKFold(n_splits=spec.pop("cv", 3), shuffle=True, random_state=seed)
    method = spec.pop("method", "sigmoid")
    calibrated: SklearnLike = CalibratedClassifierCV(model, method=method, cv=inner, **spec)
    return calibrated


# target_transform の語彙 → (func, inverse_func)。**モジュール関数**（np.log1p/np.expm1）に限る＝pickle が
# 名前参照で往復できる（lambda・クロージャは save/load を壊すので登録しない）。足すときはここに 1 行。
_TARGET_TRANSFORMS: dict[str, tuple[Callable[..., Any], Callable[..., Any]]] = {"log1p": (np.log1p, np.expm1)}


def build_model(spec: Mapping[str, Any], *, seed: int, task: ModelTask | None = None) -> SklearnLike:
    """config の model 節（{kind, ...params}）から 1 つのモデル（推定器）を作る。

    kind は `uv run data models` の一覧から。params はそのまま sklearn クラスへ渡す（写経しない・目的関数も
    loss/criterion/objective の文字列 params で変える）。task を渡すとモデル種との整合を検査する（task=None は互換）。
    build_estimator に model として渡すと features→encode→model の 1 本の Pipeline になる。
    spec に `tune:` があれば model を *SearchCV で包んで返す（`tune.build_tuned`＝run_cv でそのまま nested CV）。
    spec に `calibrate:` があれば CalibratedClassifierCV で包む（`build_calibrated`・tune 併用時は tuned を包む）。
    spec に `target_transform: log1p` があれば TransformedTargetRegressor(func=np.log1p, inverse_func=np.expm1)
    で包む（回帰のみ・歪んだ y を変換空間で学習し、予測は逆変換済み＝rmse 等を原スケールで測れる。
    tune 併用時は tuned を包む＝param 名は素のまま・内側 CV の選抜は変換後スケール）。
    """
    # MODELS は Mapping としてだけ読む（テストが未導入再現のため plain dict に monkeypatch で差し替える）。
    kind = spec.get("kind")
    if not isinstance(kind, str) or kind not in MODELS:
        extra = OPTIONAL_MODEL_EXTRAS.get(kind) if isinstance(kind, str) else None
        hint = f"。'{kind}' は `uv sync --extra {extra}` で使えるようになる" if extra else ""
        raise ValueError(f"未知のモデル '{kind}'（{sorted(MODELS)} のいずれか）{hint}")
    entry = MODELS[kind]
    # 多クラスもモデル種は classification（クラス数は fit 時のラベルで決まる）＝ MODELS の語彙へ正規化して照合。
    model_task = "classification" if task == "multiclass" else task
    if model_task is not None and entry.task != model_task:
        raise ValueError(f"モデル '{kind}' は {entry.task} 用（この実験は task: {task}）")
    params = {k: v for k, v in spec.items() if k not in ("kind", "tune", "calibrate", "target_transform")}
    model: SklearnLike = entry.factory(seed, **params)
    tune = spec.get("tune")
    if tune is not None:  # tune 無しは従来どおり素の model（既存挙動は不変）
        from harness.ds.tune import build_tuned  # 遅延 import（tune.py は pipeline を import しない＝循環なし）

        model = build_tuned(model, tune, seed=seed)
    target_transform = spec.get("target_transform")
    if target_transform is not None:  # 無しは従来どおり（既存挙動は不変）
        if entry.task != "regression":  # y の変換＋逆変換で測る仕組み＝回帰のみ（fit まで待たず config 段で止める）
            raise ValueError(f"target_transform は回帰のみ（モデル '{kind}' は {entry.task}）")
        if target_transform not in _TARGET_TRANSFORMS:  # typo を黙って素通ししない（fail-loud）
            raise ValueError(f"未知の target_transform '{target_transform}'（{sorted(_TARGET_TRANSFORMS)} のいずれか）")
        func, inverse_func = _TARGET_TRANSFORMS[target_transform]
        # tuned を包む（TTR が最外）＝param_grid のキーは素の名前のまま書ける（regressor__ 前置は不要）。
        model = TransformedTargetRegressor(regressor=model, func=func, inverse_func=inverse_func)
    calibrate = spec.get("calibrate")
    if calibrate is not None:  # calibrate 無しは従来どおり。併用時は tuned を包む（tune→calibrate の順）
        if entry.task == "regression":  # 確率較正は predict_proba が要る＝分類のみ（fit まで待たず config 段で止める）
            raise ValueError(f"calibrate は分類のみ（モデル '{kind}' は回帰）")
        return build_calibrated(model, calibrate, seed=seed)
    return model


def _build_block(spec: Mapping[str, Any], seed: int) -> FeatureBlock:
    cls = BLOCKS.resolve(spec.get("kind")).factory  # 未知 kind の ValueError は Registry.resolve の 1 か所
    params = {k: v for k, v in spec.items() if k not in ("kind", "name")}
    # seed 引数を持つブロック（TargetAggregate 等）には、config 未指定なら seed を注入する（二重に書かせない）。
    if "seed" in inspect.signature(cls.__init__).parameters and "seed" not in params:
        params["seed"] = seed
    block: FeatureBlock = cls(**params)
    return block


def build_estimator(spec: Mapping[str, Any], model: SklearnLike, *, seed: int) -> Pipeline:
    """config（features / encode 節）から 2〜3 段の sklearn Pipeline を組む。

    spec = {"features": [{kind, name?, ...params}, ...],            # 必須・1 つ以上
            "encode":   [{kind, name?, columns, ...params}, ...],   # 任意（無ければ 2 段）
            "select":   {kind, ...params}}                          # 任意・1 個の dict（SELECTORS・T-0064）
    encode の columns は ColumnTransformer の対象列（Tfidf だけ文字列 1 本・他はリスト）。生のカテゴリ列は
    features 段の columns ブロックで通しておくこと（encode がそれを受ける）。
    encode 段の task（分類/回帰）は model から知る（is_classifier）＝config に二重に書かせない。task 引数を持つ
    工場（target 等）にだけ注入する（_build_block の seed 注入と同じ流儀・encode 節に task を明示すればそれが優先）。
    select があれば to_numpy と model の間に選択段を挿す（無ければ steps は従来どおり）。選択の fit も
    run_cv の clone-per-fold で fold の train でだけ起きる＝リークなし（encode と同じ構造的担保）。
    """
    features: Sequence[Mapping[str, Any]] = spec.get("features", [])
    if not features:
        raise ValueError("features は 1 つ以上必要")
    blocks = [(f.get("name", f["kind"]), _build_block(f, seed)) for f in features]
    steps: list[tuple[str, object]] = [("features", FeaturePipeline(blocks))]

    encode: Sequence[Mapping[str, Any]] = spec.get("encode", [])
    if encode:
        names = [e.get("name", e["kind"]) for e in encode]
        dups = sorted({n for n in names if names.count(n) > 1})
        if dups:
            raise ValueError(f"encode の name が重複: {dups}（同じ kind を複数使うときは name を明示）")
        task = "classification" if is_classifier(model) else "regression"
        transformers = []
        for e in encode:
            # task 引数を持つ工場（target 等）にだけ model 由来の task を注入する（明示指定があればそれが優先）。
            enc_spec: Mapping[str, Any] = e
            if "task" in inspect.signature(ENCODERS.resolve(e["kind"]).factory).parameters and "task" not in e:
                enc_spec = {**e, "task": task}
            # kind/name/columns 以外の params を工場へ素通し（Registry.build の既定 drop と同じ配線キー）。
            transformers.append((e.get("name", e["kind"]), ENCODERS.build(enc_spec, seed=seed), e["columns"]))
        steps.append(
            ("encode", ColumnTransformer(transformers, remainder="passthrough", verbose_feature_names_out=False))
        )

    # model 直前で numpy に揃える（名前付き入力を扱えないモデルでも壊れない・境界を 1 点に固定）。
    steps.append(("to_numpy", FunctionTransformer(_to_numpy, feature_names_out="one-to-one")))
    select: Mapping[str, Any] | None = spec.get("select")
    if select is not None:  # select 無しは従来どおり（steps 不変＝回帰なし）
        # kind/name 以外を工場へ素通し（ENCODERS.build と同じ配線・Registry.build の既定 drop）。
        steps.append(("select", SELECTORS.build(select, seed=seed)))
    steps.append(("model", model))
    return Pipeline(steps)
