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

import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any

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


# config の kind → モデルの工場（seed 配線・安全既定つき）。LightGBM 等を足すときはここに 1 行（DEC-0006）。
MODELS: dict[str, ModelFactory] = {
    "logreg": _logreg,
}


def build_model(spec: Mapping[str, Any], *, seed: int) -> SklearnLike:
    """config の model 節（{kind, ...params}）から 1 つのモデル（推定器）を作る。

    kind は `uv run data models` の一覧から。params はそのまま sklearn クラスへ渡す（写経しない）。
    build_estimator に model として渡すと features→encode→model の 1 本の Pipeline になる。
    """
    kind = spec.get("kind")
    if kind not in MODELS:
        raise ValueError(f"未知のモデル '{kind}'（{sorted(MODELS)} のいずれか）")
    params = {k: v for k, v in spec.items() if k != "kind"}
    return MODELS[kind](seed, **params)


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

    steps.append(("model", model))
    return Pipeline(steps)
