"""特徴量作成の枠組み（BaseBlock の考え方・モデル非依存）。

- `FeatureBlock`：特徴量作成の1単位。polars 入→polars 出。sklearn 互換（BaseEstimator+TransformerMixin）
  なので `clone` でき、モデルと一緒に1本の `Pipeline` に入る。fold ごとに clone→train で fit されるので
  漏れ防止は構造で担保される（cv.run_cv 参照）。
- **個別の標準変換（StandardScaler・OneHotEncoder 等）はここに作らない**。それらは sklearn を直接
  Pipeline/ColumnTransformer に入れる。ここに書くのは「複数列から作る本物の特徴量ロジック」
  （交互作用・集約など、どのモデルにも効くモデル非依存の部分）だけ。
- `FeaturePipeline`：ブロックを横に束ねる薄い sklearn 互換 transformer。どのブロックが何列を出したかを
  `describe` で示す（人にもエージェントにも「特徴量の出所」が追える）。行数不変・出力列名の重複を検査する。
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import polars as pl
from numpy.typing import NDArray
from sklearn.base import BaseEstimator, TransformerMixin


class FeatureBlock(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """特徴量作成の1単位の基底。子クラスは `_transform` と `feature_names` を実装する。

    無状態なら fit は不要（既定で何もしない）。train の統計が要る有状態ブロックは fit を上書きし、
    学習した統計をこのインスタンスに持つ（transform はそれを使うだけ）。
    """

    def fit(self, x: pl.DataFrame, y: object = None) -> FeatureBlock:
        return self

    def transform(self, x: pl.DataFrame) -> pl.DataFrame:
        return self._transform(x)

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        raise NotImplementedError

    def feature_names(self) -> list[str]:
        """このブロックが出力する列名（データ無しで分かる＝設定から定まる）。"""
        raise NotImplementedError

    def get_feature_names_out(self, input_features: object = None) -> NDArray[np.object_]:
        """sklearn 互換の名前取得（Pipeline がこれを使う）。"""
        return np.asarray(self.feature_names(), dtype=object)


class Interactions(FeatureBlock):
    """指定した列ペアの積 `a_x_b` を作る（無状態）。複数列から作る本物の特徴量の例。"""

    def __init__(self, pairs: Sequence[tuple[str, str]]) -> None:
        self.pairs = pairs

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        return x.select([(pl.col(a) * pl.col(b)).alias(f"{a}_x_{b}") for a, b in self.pairs])

    def feature_names(self) -> list[str]:
        return [f"{a}_x_{b}" for a, b in self.pairs]


class Columns(FeatureBlock):
    """指定した列をそのまま通す（無状態）。baseline 変種の素通しに使う。"""

    def __init__(self, columns: Sequence[str]) -> None:
        self.columns = columns

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        return x.select(list(self.columns))

    def feature_names(self) -> list[str]:
        return list(self.columns)


class FeaturePipeline(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """複数の特徴量ブロックを横に束ねる薄い sklearn 互換 transformer。

    `estimator = Pipeline([("features", FeaturePipeline([...])), ("model", ...)])` の "features" 段に入れる。
    検査：各ブロックの出力行数＝入力行数／ブロック間で出力列名が重複しないこと。
    """

    def __init__(self, blocks: Sequence[tuple[str, FeatureBlock]]) -> None:
        self.blocks = blocks

    def fit(self, x: pl.DataFrame, y: object = None) -> FeaturePipeline:
        for _, block in self.blocks:
            block.fit(x, y)
        return self

    def transform(self, x: pl.DataFrame) -> pl.DataFrame:
        if not self.blocks:
            raise ValueError("ブロックが 1 つも無い（FeaturePipeline には少なくとも 1 つ足すこと）")
        combined: pl.DataFrame | None = None
        seen: set[str] = set()
        for name, block in self.blocks:
            out = block.transform(x)
            if out.height != x.height:
                raise ValueError(f"ブロック {name} の出力行数 {out.height} が入力 {x.height} と違う")
            duplicated = seen & set(out.columns)
            if duplicated:
                raise ValueError(f"ブロック {name} の出力列 {sorted(duplicated)} が他ブロックと重複している")
            seen |= set(out.columns)
            # 等高の横連結（heights は上で検査済み）。hstack は非推奨警告を出さない。
            combined = out if combined is None else combined.hstack(out)
        assert combined is not None
        return combined

    def feature_names(self) -> list[str]:
        names: list[str] = []
        for _, block in self.blocks:
            names.extend(block.feature_names())
        return names

    def get_feature_names_out(self, input_features: object = None) -> NDArray[np.object_]:
        return np.asarray(self.feature_names(), dtype=object)

    def describe(self) -> list[dict[str, object]]:
        """どのブロックが何列を出すかの一覧（人・エージェント向け）。"""
        return [{"block": name, "output_columns": block.feature_names()} for name, block in self.blocks]
