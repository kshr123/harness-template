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

from collections.abc import Callable, Sequence

import numpy as np
import polars as pl
from numpy.typing import NDArray
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted


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


# --- 具体ブロック（複数列から作るモデル非依存の特徴量。sklearn が綺麗に持たないものだけ） ---
# 個別の標準変換（OneHot/Ordinal/TargetEncoder/KBinsDiscretizer/PCA/Tfidf 等）はここに作らず、
# sklearn を直接 Pipeline/ColumnTransformer に入れる（DEC-0006/0007）。


class Ratios(FeatureBlock):
    """指定した列ペアの比 `a_div_b` を作る（無状態）。分母が 0 か null なら null（inf を作らない）。"""

    def __init__(self, pairs: Sequence[tuple[str, str]]) -> None:
        self.pairs = pairs

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        return x.select(
            pl.when(pl.col(b) != 0).then(pl.col(a) / pl.col(b)).otherwise(None).alias(f"{a}_div_{b}")
            for a, b in self.pairs
        )

    def feature_names(self) -> list[str]:
        return [f"{a}_div_{b}" for a, b in self.pairs]


class Differences(FeatureBlock):
    """指定した列ペアの差 `a_minus_b` を作る（無状態）。null は伝播する。"""

    def __init__(self, pairs: Sequence[tuple[str, str]]) -> None:
        self.pairs = pairs

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        return x.select((pl.col(a) - pl.col(b)).alias(f"{a}_minus_{b}") for a, b in self.pairs)

    def feature_names(self) -> list[str]:
        return [f"{a}_minus_{b}" for a, b in self.pairs]


# グループ別集約の式（この辞書以外の集約名は fit で失敗にする。拡張点はここ 1 か所）。
_AGG_EXPRS: dict[str, Callable[[str], pl.Expr]] = {
    "mean": lambda c: pl.col(c).mean(),
    "std": lambda c: pl.col(c).std(),
    "min": lambda c: pl.col(c).min(),
    "max": lambda c: pl.col(c).max(),
    "median": lambda c: pl.col(c).median(),
    "sum": lambda c: pl.col(c).sum(),
    "n_unique": lambda c: pl.col(c).n_unique(),
}
_DERIVED = ("ratio", "diff")


class GroupAggregate(FeatureBlock):
    """グループ別の集約統計を train で学習し、行ごとに引き当てる（有状態）。

    fit(train) でグループ別統計 stats_ と全体統計 global_ を学習。transform は左結合で引き当て、
    train に無いグループは全体統計で埋める。derived＝ratio（元値/統計）・diff（元値−統計）を足せる。
    漏れ防止は run_cv の clone-per-fold が担う（統計は fold の train でだけ計算される）。
    注：埋めは「未知グループ」だけでなく「既知だが統計が null（例：単一要素グループの std）」にも効く
    （どちらも全体統計で埋まる。null を残したい場合はその集約を使わない）。
    """

    def __init__(
        self,
        group_by: str,
        columns: Sequence[str],
        aggs: Sequence[str],
        derived: Sequence[str] = (),
    ) -> None:
        self.group_by = group_by
        self.columns = columns
        self.aggs = aggs
        self.derived = derived

    def _stat_name(self, column: str, agg: str) -> str:
        return f"{column}_{agg}_by_{self.group_by}"

    def _agg_exprs(self) -> list[pl.Expr]:
        return [_AGG_EXPRS[a](c).alias(self._stat_name(c, a)) for c in self.columns for a in self.aggs]

    def fit(self, x: pl.DataFrame, y: object = None) -> GroupAggregate:
        for a in self.aggs:
            if a not in _AGG_EXPRS:
                raise ValueError(f"未対応の集約 '{a}'（{sorted(_AGG_EXPRS)} のいずれか）")
        for d in self.derived:
            if d not in _DERIVED:
                raise ValueError(f"未対応の derived '{d}'（{list(_DERIVED)} のいずれか）")
        exprs = self._agg_exprs()
        self.stats_ = x.group_by(self.group_by).agg(exprs)
        self.global_ = x.select(exprs).row(0, named=True)  # 未知グループの埋め値（train 全体の同じ統計）
        return self

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        check_is_fitted(self, "stats_")
        joined = x.join(self.stats_, on=self.group_by, how="left", nulls_equal=True)
        out: list[pl.Expr] = []
        derived: list[pl.Expr] = []
        for c in self.columns:
            for a in self.aggs:
                base = self._stat_name(c, a)
                filled = pl.coalesce(pl.col(base), pl.lit(self.global_[base]))
                out.append(filled.alias(base))
                for d in self.derived:
                    if d == "ratio":
                        derived.append(
                            pl.when(filled != 0).then(pl.col(c) / filled).otherwise(None).alias(f"{base}_ratio")
                        )
                    else:  # diff
                        derived.append((pl.col(c) - filled).alias(f"{base}_diff"))
        return joined.select(out + derived)

    def feature_names(self) -> list[str]:
        base = [self._stat_name(c, a) for c in self.columns for a in self.aggs]
        return base + [f"{n}_{d}" for n in base for d in self.derived]


class CountEncode(FeatureBlock):
    """カテゴリの出現回数（頻度）を train で数え、行ごとに引き当てる（有状態）。

    未知カテゴリは 0。null も 1 つのカテゴリとして数える。normalize=True で train 行数で割った割合。
    """

    def __init__(self, columns: Sequence[str], normalize: bool = False) -> None:
        self.columns = columns
        self.normalize = normalize

    def _name(self, column: str) -> str:
        return f"{column}_freq" if self.normalize else f"{column}_count"

    def fit(self, x: pl.DataFrame, y: object = None) -> CountEncode:
        self.counts_ = {c: x.group_by(c).agg(pl.len().alias(self._name(c))) for c in self.columns}
        self.n_rows_ = x.height
        return self

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        check_is_fitted(self, "counts_")
        combined: pl.DataFrame | None = None
        for c in self.columns:
            name = self._name(c)
            joined = x.select(c).join(self.counts_[c], on=c, how="left", nulls_equal=True)
            expr = pl.col(name).fill_null(0)
            if self.normalize:
                expr = expr / self.n_rows_
            part = joined.select(expr.alias(name))
            combined = part if combined is None else combined.hstack(part)
        assert combined is not None
        return combined

    def feature_names(self) -> list[str]:
        return [self._name(c) for c in self.columns]


# config の kind 文字列 → ブロックのクラス。config から特徴量を組む唯一の表（足したら 1 行足す）。
BLOCKS: dict[str, type[FeatureBlock]] = {
    "columns": Columns,
    "interactions": Interactions,
    "ratios": Ratios,
    "differences": Differences,
    "group_aggregate": GroupAggregate,
    "count_encode": CountEncode,
}
