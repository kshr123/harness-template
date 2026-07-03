"""config から特徴量→エンコード→モデルの sklearn Pipeline を組み立てる（sklearn エンコーダを用意しておく口）。

- 特徴量段（features）：我々の `FeatureBlock`（`BLOCKS`）を横に束ねる。**生のカテゴリ/テキスト列も Columns で通す**
  （Pipeline は逐次で、後段の encode は features の出力しか見えないため）。
- エンコード段（encode）：sklearn のエンコーダ（`ENCODERS`）を `ColumnTransformer` に入れる。**再発明しない**
  （DEC-0008）が「必要なときに確実に使える」よう、**落ちない・漏れない・決定的**に関わる既定だけ焼き込む：
  OneHot は未知カテゴリでエラーを出さない・Ordinal は未知/欠損を -1・TargetEncoder は非推奨 shuffle/random_state を
  使わず `cv=KFold(seed)` で決定的な OOF・KBins/PCA は NaN で落ちるので中央値埋めを前置・Tfidf は null を空文字に。
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
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import polars as pl
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
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

EncoderFactory = Callable[..., object]
ModelFactory = Callable[..., SklearnLike]


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


def _target(seed: int, *, cv: int = 5, **params: Any) -> object:  # noqa: ANN401
    """TargetEncoder（平滑化平均）。内部 cross-fitting(OOF) を cv=KFold(seed) で決定化。高カーディナリティ向け。"""
    # 漏れない＋決定的：内部 cross-fitting(OOF) を KFold(seed) で固定（shuffle/random_state は 1.9 非推奨）。
    return TargetEncoder(cv=KFold(n_splits=cv, shuffle=True, random_state=seed), **params)


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


def _fill_text(s: pl.Series) -> pl.Series:  # モジュール関数（lambda は pickle 不可）
    return s.fill_null("")


def _to_numpy(x: Any) -> Any:  # noqa: ANN401  polars/pandas/scipy 疎行列/numpy を受ける
    """特徴量段の出力を numpy 配列に揃える（model 直前の唯一の numpy⇔polars 境界・DESIGN の方針）。

    列名を落とすので、名前付き入力で feature_names_in_ を設定できないモデル（LightGBM 等）でも Pipeline が壊れない。
    scipy 疎行列（tfidf 等の出力）は toarray で密化する（np.asarray だと 0 次元 object になり壊れる）。
    """
    if hasattr(x, "toarray"):  # scipy 疎行列（.to_numpy は無い）
        return x.toarray()
    return x.to_numpy() if hasattr(x, "to_numpy") else np.asarray(x)


def _tfidf(seed: int, **params: Any) -> object:  # noqa: ANN401
    """TfidfVectorizer（テキスト特徴量）。null を空文字に埋めて前置。columns は文字列 1 本（リストにしない）。"""
    # 落ちない：null テキストで TfidfVectorizer は落ちる → 空文字埋めを前置。
    return Pipeline(
        [
            ("fill", FunctionTransformer(_fill_text, feature_names_out="one-to-one")),
            ("tfidf", TfidfVectorizer(**params)),
        ]
    )


# config の kind → sklearn エンコーダの工場（落ちない・漏れない・決定的の既定つき）。足したら 1 行。
ENCODERS: dict[str, EncoderFactory] = {
    "onehot": _onehot,
    "ordinal": _ordinal,
    "target": _target,
    "bins": _bins,
    "pca": _pca,
    "tfidf": _tfidf,
}


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
    return model


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


ModelTask = Literal["classification", "regression"]


@dataclass(frozen=True)
class ModelEntry:
    """モデル種 1 つの登録情報。factory は sklearn/LightGBM クラスの薄い包み（再発明しない）。

    task：このモデルが解ける課題。build_model が config の task と突き合わせて検査する（回帰モデル×分類 task を
    実行前に止める）。説明文は factory の docstring 1 行目（`uv run data models` に載る・test_catalog が必須検査）。
    """

    factory: ModelFactory
    task: ModelTask


# config の kind → モデルの登録（工場＋task）。sklearn を足すときはここに 1 行（DEC-0006）。
# optional 依存（lightgbm 等）のモデルはファイル末尾で「入っていれば登録」する（§5 条件登録）。
MODELS: dict[str, ModelEntry] = {
    # 分類
    "logreg": ModelEntry(_logreg, "classification"),
    "knn": ModelEntry(_knn, "classification"),
    "tree": ModelEntry(_tree, "classification"),
    "random_forest": ModelEntry(_random_forest, "classification"),
    "hist_gb": ModelEntry(_hist_gb, "classification"),
    # 回帰
    "ridge": ModelEntry(_ridge, "regression"),
    "lasso": ModelEntry(_lasso, "regression"),
    "elasticnet": ModelEntry(_elasticnet, "regression"),
    "random_forest_reg": ModelEntry(_random_forest_reg, "regression"),
    "hist_gb_reg": ModelEntry(_hist_gb_reg, "regression"),
}

# optional 依存の kind → 導入すべき extra 名（未導入で使われたときのヒント）。
OPTIONAL_MODEL_EXTRAS: dict[str, str] = {"lightgbm": "lightgbm", "lightgbm_reg": "lightgbm"}

# 条件登録：ライブラリが入っている環境でだけ MODELS に足す（`data models` は使える語彙だけを見せる）。
# import コストゼロの存在確認（find_spec）で登録を切り替える。工場本体は関数内 import なので未導入でも壊れない。
if importlib.util.find_spec("lightgbm") is not None:
    MODELS["lightgbm"] = ModelEntry(_lightgbm, "classification")
    MODELS["lightgbm_reg"] = ModelEntry(_lightgbm_reg, "regression")


def build_model(spec: Mapping[str, Any], *, seed: int, task: ModelTask | None = None) -> SklearnLike:
    """config の model 節（{kind, ...params}）から 1 つのモデル（推定器）を作る。

    kind は `uv run data models` の一覧から。params はそのまま sklearn クラスへ渡す（写経しない・目的関数も
    loss/criterion/objective の文字列 params で変える）。task を渡すとモデル種との整合を検査する（task=None は互換）。
    build_estimator に model として渡すと features→encode→model の 1 本の Pipeline になる。
    """
    kind = spec.get("kind")
    if kind not in MODELS:
        extra = OPTIONAL_MODEL_EXTRAS.get(kind) if isinstance(kind, str) else None
        hint = f"。'{kind}' は `uv sync --extra {extra}` で使えるようになる" if extra else ""
        raise ValueError(f"未知のモデル '{kind}'（{sorted(MODELS)} のいずれか）{hint}")
    entry = MODELS[kind]
    if task is not None and entry.task != task:
        raise ValueError(f"モデル '{kind}' は {entry.task} 用（この実験は task: {task}）")
    params = {k: v for k, v in spec.items() if k != "kind"}
    return entry.factory(seed, **params)


def _build_block(spec: Mapping[str, Any], seed: int) -> FeatureBlock:
    kind = spec["kind"]
    if kind not in BLOCKS:
        raise ValueError(f"未知の特徴量ブロック '{kind}'（{sorted(BLOCKS)} のいずれか）")
    cls = BLOCKS[kind]
    params = {k: v for k, v in spec.items() if k not in ("kind", "name")}
    # seed 引数を持つブロック（TargetAggregate 等）には、config 未指定なら seed を注入する（二重に書かせない）。
    if "seed" in inspect.signature(cls.__init__).parameters and "seed" not in params:
        params["seed"] = seed
    return cls(**params)


def build_estimator(spec: Mapping[str, Any], model: SklearnLike, *, seed: int) -> Pipeline:
    """config（features / encode 節）から 2〜3 段の sklearn Pipeline を組む。

    spec = {"features": [{kind, name?, ...params}, ...],            # 必須・1 つ以上
            "encode":   [{kind, name?, columns, ...params}, ...]}   # 任意（無ければ 2 段）
    encode の columns は ColumnTransformer の対象列（Tfidf だけ文字列 1 本・他はリスト）。生のカテゴリ列は
    features 段の columns ブロックで通しておくこと（encode がそれを受ける）。
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
        transformers = []
        for e in encode:
            if e["kind"] not in ENCODERS:
                raise ValueError(f"未知のエンコーダ '{e['kind']}'（{sorted(ENCODERS)} のいずれか）")
            params = {k: v for k, v in e.items() if k not in ("kind", "name", "columns")}
            transformers.append((e.get("name", e["kind"]), ENCODERS[e["kind"]](seed, **params), e["columns"]))
        steps.append(
            ("encode", ColumnTransformer(transformers, remainder="passthrough", verbose_feature_names_out=False))
        )

    # model 直前で numpy に揃える（名前付き入力を扱えないモデルでも壊れない・境界を 1 点に固定）。
    steps.append(("to_numpy", FunctionTransformer(_to_numpy, feature_names_out="one-to-one")))
    steps.append(("model", model))
    return Pipeline(steps)
