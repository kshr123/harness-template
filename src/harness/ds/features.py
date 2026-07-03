"""特徴量作成の枠組み（BaseBlock の考え方・モデル非依存）。

- `FeatureBlock`：特徴量作成の1単位。polars 入→polars 出。sklearn 互換（BaseEstimator+TransformerMixin）
  なので `clone` でき、モデルと一緒に1本の `Pipeline` に入る。fold ごとに clone→train で fit されるので
  漏れ防止は構造で担保される（cv.run_cv 参照）。
- **「作る/使う」の基準は sklearn が十分うまくやっているか**（データ依存かどうかではない・DEC-0008）。
  sklearn が良くやるもの（OneHot/Ordinal/TargetEncoder/KBins/PCA/Tfidf）は作らず ColumnTransformer に直接入れる。
  sklearn に無い隙間（list 列の multi-hot・target の mean 以外の統計・多キー結合）はデータ依存でもここに作る。
- `FeaturePipeline`：ブロックを横に束ねる薄い sklearn 互換 transformer。どのブロックが何列を出したかを
  `describe` で示す（人にもエージェントにも「特徴量の出所」が追える）。行数不変・出力列名の重複を検査する。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import polars as pl
from numpy.typing import NDArray
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.exceptions import NotFittedError
from sklearn.model_selection import KFold
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
        """このブロックが出力する列名。fit 後に呼べば必ず確定している。

        設定だけで列名が決まるブロックは fit 前でも返してよい。データ依存で fit で列（語彙など）を学習する
        ブロックは、fit 前は `check_is_fitted` で NotFittedError にする（sklearn の慣習と同じ）。
        """
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

    def _combine(self, x: pl.DataFrame, parts: list[tuple[str, pl.DataFrame]]) -> pl.DataFrame:
        """各ブロックの出力を横に連結する。行数不変・出力列名の重複を検査する（transform/fit_transform 共通）。"""
        if not parts:
            raise ValueError("ブロックが 1 つも無い（FeaturePipeline には少なくとも 1 つ足すこと）")
        combined: pl.DataFrame | None = None
        seen: set[str] = set()
        for name, out in parts:
            if out.height != x.height:
                raise ValueError(f"ブロック {name} の出力行数 {out.height} が入力 {x.height} と違う")
            duplicated = seen & set(out.columns)
            if duplicated:
                raise ValueError(f"ブロック {name} の出力列 {sorted(duplicated)} が他ブロックと重複している")
            seen |= set(out.columns)
            combined = out if combined is None else combined.hstack(out)  # 等高の横連結（heights は検査済み）
        assert combined is not None
        return combined

    def transform(self, x: pl.DataFrame) -> pl.DataFrame:
        return self._combine(x, [(name, block.transform(x)) for name, block in self.blocks])

    def fit_transform(self, x: pl.DataFrame, y: object = None, **fit_params: object) -> pl.DataFrame:
        """各ブロックの fit_transform を呼んで横連結する。

        OOF 型ブロック（TargetAggregate 等）は fit_transform で train 自身を漏れなく（cross-fitting で）
        エンコードする。ここで各ブロックの fit_transform を必ず通すことで、その OOF 経路が生きる
        （sklearn Pipeline → FeaturePipeline → 各ブロック、と fit_transform が端まで伝わる）。
        """
        return self._combine(x, [(name, block.fit_transform(x, y)) for name, block in self.blocks])

    def feature_names(self) -> list[str]:
        names: list[str] = []
        for _, block in self.blocks:
            names.extend(block.feature_names())
        return names

    def get_feature_names_out(self, input_features: object = None) -> NDArray[np.object_]:
        return np.asarray(self.feature_names(), dtype=object)

    def describe(self) -> list[dict[str, object]]:
        """どのブロックが何列を出すかの一覧（人・エージェント向け）。fit 前でも呼べる。"""
        out: list[dict[str, object]] = []
        for name, block in self.blocks:
            try:
                cols: object = block.feature_names()
            except NotFittedError:
                cols = "fit 後に確定（データ依存）"
            out.append({"block": name, "output_columns": cols})
        return out


# --- 具体ブロック ---
# 「作る/使う」の基準は **sklearn（最新）がそれを十分うまくやっているか**（データ依存かどうかではない・DEC-0008）。
# 使う（作らない）：OneHot/Ordinal/TargetEncoder(平滑化平均・OOF 内蔵)/KBins/PCA/Tfidf は sklearn を
#   ColumnTransformer に直接入れる（set_output(transform="polars") で polars 出力・再発明禁止 DEC-0006）。
# 作る（sklearn に無い隙間・データ依存でも）：MultiHot（list 列のタグ）・TargetAggregate（target の mean 以外の
#   統計・OOF 内蔵）・CombineKeys（多キーを sklearn TargetEncoder に渡す前段）。


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
        joined = x.join(self.stats_, on=self.group_by, how="left", nulls_equal=True, maintain_order="left")
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
            joined = x.select(c).join(self.counts_[c], on=c, how="left", nulls_equal=True, maintain_order="left")
            expr = pl.col(name).fill_null(0)
            if self.normalize:
                expr = expr / self.n_rows_
            part = joined.select(expr.alias(name))
            combined = part if combined is None else combined.hstack(part)
        assert combined is not None
        return combined

    def feature_names(self) -> list[str]:
        return [self._name(c) for c in self.columns]


class CombineKeys(FeatureBlock):
    """複数のカテゴリ列を 1 本のキー列に結合する（無状態）。

    多キーの target/count encoding の前段。出力列を sklearn TargetEncoder や CountEncode に渡せば、
    組み合わせキーの OOF・平滑化・度数は標準実装がやってくれる（多キーの漏れ対策を自作しない）。
    null は "<null>" にしてから結合する（(null,"a") と ("x",null) を別グループに保つ）。値に separator
    や文字列 "<null>" が含まれると別の組が衝突し得るので、その場合は separator を変える。
    """

    def __init__(self, groups: Sequence[Sequence[str]], separator: str = "__") -> None:
        self.groups = groups
        self.separator = separator

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        return x.select(
            pl.concat_str([pl.col(c).cast(pl.String).fill_null("<null>") for c in g], separator=self.separator).alias(
                self.separator.join(g)
            )
            for g in self.groups
        )

    def feature_names(self) -> list[str]:
        return [self.separator.join(g) for g in self.groups]


class MultiHot(FeatureBlock):
    """polars の list(str) 列（タグ）を 0/1 の列に展開する（有状態・データ依存）。

    fit(train) で語彙を学習する：train で min_count 行以上に現れたタグだけを名前順で採用。transform は
    各タグにつき「行の list に含まれるか」を 0/1 で出す。train に無い（または稀で落とした）タグは無視する
    （sklearn OneHotEncoder の handle_unknown="ignore" と同じ考え方）。null・空 list は全タグ 0。
    include_count=True で行のタグ数を 1 列足す。列名は sklearn 慣習の `列名_タグ値`。
    """

    def __init__(self, column: str, min_count: int = 1, include_count: bool = False) -> None:
        self.column = column
        self.min_count = min_count
        self.include_count = include_count

    def fit(self, x: pl.DataFrame, y: object = None) -> MultiHot:
        counts = (
            x.select(pl.col(self.column).list.unique())  # 同一行内の重複は 1 回と数える
            .filter(pl.col(self.column).list.len() > 0)  # 空・null list を除く
            .explode(self.column, empty_as_null=False)  # 空 list の扱いを明示（Polars 2.0 の既定に合わせる）
            .drop_nulls()
            .group_by(self.column)
            .len()
        )
        self.categories_ = sorted(counts.filter(pl.col("len") >= self.min_count)[self.column].to_list())
        return self

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        check_is_fitted(self, "categories_")
        exprs = [
            pl.col(self.column).list.contains(v).fill_null(False).cast(pl.Int8).alias(f"{self.column}_{v}")
            for v in self.categories_
        ]
        if self.include_count:
            exprs.append(pl.col(self.column).list.len().fill_null(0).alias(f"{self.column}_n_tags"))
        return x.select(exprs)

    def feature_names(self) -> list[str]:
        check_is_fitted(self, "categories_")  # データ依存：fit 前は NotFittedError
        names = [f"{self.column}_{v}" for v in self.categories_]
        if self.include_count:
            names.append(f"{self.column}_n_tags")
        return names


# target の集約（mean 以外）。mean は sklearn TargetEncoder（内部 CV＋平滑化）に回す＝ここでは持たない。
_TARGET_AGGS: dict[str, Callable[[str], pl.Expr]] = {
    "std": lambda c: pl.col(c).std(),  # ddof=1（polars 既定）
    "median": lambda c: pl.col(c).median(),
    "min": lambda c: pl.col(c).min(),
    "max": lambda c: pl.col(c).max(),
}


class TargetAggregate(FeatureBlock):
    """カテゴリ（組）別の target 統計（mean 以外）を学習し、行ごとに引き当てる（有状態・OOF 内蔵）。

    - "mean" は受け付けない（fit で ValueError）。平滑化平均の target encoding は sklearn TargetEncoder が
      内部 cross-fitting＋自動平滑化つきで正しく持つので、ここで再発明しない。
    - 漏れ対策は 2 段：外側は run_cv の clone-per-fold（統計は fold の train でだけ学習）。内側は fit_transform
      の cross-fitting（KFold で train を分け、各行を残りの行だけの統計で埋める）。行自身の y が自分の特徴量に
      混ざる自己漏れを防ぐ。よって fit_transform(x,y) と fit(x,y).transform(x) は一致しない（前者が学習用）。
    - 未知グループ・統計が null のグループ（1 行グループの std 等）は全体統計で埋める。キーの null は 1 グループ。
    """

    _TARGET = "__target__"

    def __init__(self, group_by: Sequence[str], aggs: Sequence[str], cv: int = 5, seed: int = 0) -> None:
        self.group_by = group_by
        self.aggs = aggs
        self.cv = cv
        self.seed = seed

    def _name(self, agg: str) -> str:
        return f"target_{agg}_by_{'_'.join(self.group_by)}"

    def _validate(self, y: object) -> None:
        if y is None:
            raise ValueError("TargetAggregate は target(y) が必須（教師あり特徴量）")
        for a in self.aggs:
            if a == "mean":
                raise ValueError("mean は非対応（平滑化平均の target encoding は sklearn TargetEncoder を使う）")
            if a not in _TARGET_AGGS:
                raise ValueError(f"未対応の集約 '{a}'（{sorted(_TARGET_AGGS)} のいずれか）")

    def _learn(self, keys: pl.DataFrame, target: NDArray[np.float64]) -> tuple[pl.DataFrame, dict[str, object]]:
        frame = keys.with_columns(pl.Series(self._TARGET, target))
        exprs = [_TARGET_AGGS[a](self._TARGET).alias(self._name(a)) for a in self.aggs]
        return frame.group_by(self.group_by).agg(exprs), frame.select(exprs).row(0, named=True)

    def _lookup(self, keys: pl.DataFrame, stats: pl.DataFrame, global_: dict[str, object]) -> pl.DataFrame:
        joined = keys.join(stats, on=list(self.group_by), how="left", nulls_equal=True, maintain_order="left")
        return joined.select(
            pl.coalesce(pl.col(self._name(a)), pl.lit(global_[self._name(a)])).alias(self._name(a)) for a in self.aggs
        )

    def fit(self, x: pl.DataFrame, y: object = None) -> TargetAggregate:
        self._validate(y)
        target = np.asarray(y, dtype=np.float64)
        self.stats_, self.global_ = self._learn(x.select(self.group_by), target)
        return self

    def fit_transform(self, x: pl.DataFrame, y: object = None, **fit_params: object) -> pl.DataFrame:
        self._validate(y)
        target = np.asarray(y, dtype=np.float64)
        keys = x.select(self.group_by)
        n = x.height
        cols = {self._name(a): np.empty(n, dtype=np.float64) for a in self.aggs}
        for train_idx, valid_idx in KFold(n_splits=self.cv, shuffle=True, random_state=self.seed).split(np.arange(n)):
            stats, global_ = self._learn(keys[train_idx], target[train_idx])  # 残りの fold だけで学習
            looked = self._lookup(keys[valid_idx], stats, global_)
            for a in self.aggs:
                cols[self._name(a)][valid_idx] = looked[self._name(a)].to_numpy()
        self.stats_, self.global_ = self._learn(keys, target)  # 以後の transform 用（全 train の統計）
        return pl.DataFrame({self._name(a): cols[self._name(a)] for a in self.aggs})

    def _transform(self, x: pl.DataFrame) -> pl.DataFrame:
        check_is_fitted(self, "stats_")
        return self._lookup(x.select(self.group_by), self.stats_, self.global_)

    def feature_names(self) -> list[str]:
        return [self._name(a) for a in self.aggs]


# config の kind 文字列 → ブロックのクラス。config から特徴量を組む唯一の表（足したら 1 行足す）。
BLOCKS: dict[str, type[FeatureBlock]] = {
    "columns": Columns,
    "interactions": Interactions,
    "ratios": Ratios,
    "differences": Differences,
    "group_aggregate": GroupAggregate,
    "count_encode": CountEncode,
    "combine_keys": CombineKeys,
    "multi_hot": MultiHot,
    "target_aggregate": TargetAggregate,
}
