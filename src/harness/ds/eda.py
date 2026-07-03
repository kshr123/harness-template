"""EDA（探索的データ分析）の第一の出力＝機械可読な構造化レポート（polars/dict）。

- 図でなくデータで返す（テストでき・エージェントが読める）。人が図で見たいときは notebooks/eda.py（marimo）が
  この同じ関数を呼んで表と図にする（正本はここ・ビューは薄い）。DESIGN §4 判断1。
- 集計は polars（describe/null_count/n_unique/value_counts）に委譲し、束ねるだけ（再発明しない）。
- train/test の比較（compare/psi/drift_auc）は別関数で、2 つの DataFrame を別々に集計する
  （結合してから集計する経路をこのモジュールに置かない＝リーク禁止を API の形で守る）。※ T-0026 で追加。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import polars as pl
import polars.selectors as cs

Task = Literal["classification", "regression"]


@dataclass(frozen=True)
class TableProfile:
    """1 テーブルの構造化レポート。to_dict() で YAML にそのまま落ちる（正本→保存/ビューの写像）。"""

    n_rows: int
    n_columns: int
    columns: pl.DataFrame  # column, dtype, null_count, null_ratio, n_unique（df の列順）
    numeric: pl.DataFrame  # column, mean, std, min, q25, median, q75, max（数値列のみ）
    categorical: pl.DataFrame  # column, n_unique, top_value, top_count, top_ratio
    duplicate_rows: int  # 全列一致の重複行数（= n_rows − 相異なる行数）

    def to_dict(self) -> dict[str, Any]:
        """キー順を固定して dict にする（決定的な出力）。polars は行の list[dict] へ。"""
        return {
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
            "columns": self.columns.to_dicts(),
            "numeric": self.numeric.to_dicts(),
            "categorical": self.categorical.to_dicts(),
            "duplicate_rows": self.duplicate_rows,
        }


def _column_overview(df: pl.DataFrame) -> pl.DataFrame:
    n = df.height
    nulls = df.null_count()  # 1 行 DataFrame（列ごとの null 数）
    rows = [
        {
            "column": c,
            "dtype": str(df.schema[c]),
            "null_count": int(nulls[c][0]),
            "null_ratio": (int(nulls[c][0]) / n) if n else 0.0,
            "n_unique": int(df[c].n_unique()),
        }
        for c in df.columns
    ]
    return pl.DataFrame(rows)


def _numeric_overview(df: pl.DataFrame) -> pl.DataFrame:
    cols = df.select(cs.numeric()).columns
    rows = [
        {
            "column": c,
            "mean": _f(df[c].mean()),
            "std": _f(df[c].std()),
            "min": _f(df[c].min()),
            "q25": _f(df[c].quantile(0.25)),
            "median": _f(df[c].median()),
            "q75": _f(df[c].quantile(0.75)),
            "max": _f(df[c].max()),
        }
        for c in cols
    ]
    schema = ["column", "mean", "std", "min", "q25", "median", "q75", "max"]
    return pl.DataFrame(rows) if rows else pl.DataFrame(schema={k: pl.Float64 for k in schema} | {"column": pl.String})


def _categorical_overview(df: pl.DataFrame, *, max_categories: int) -> pl.DataFrame:
    n = df.height
    cols = [c for c in df.columns if df.schema[c] == pl.String or df[c].n_unique() <= max_categories]
    rows = []
    for c in cols:
        vc = df[c].value_counts(sort=True)  # 列 [c, "count"]・降順
        top_value = vc[c][0] if vc.height else None
        top_count = int(vc["count"][0]) if vc.height else 0
        rows.append(
            {
                "column": c,
                "n_unique": int(df[c].n_unique()),
                "top_value": None if top_value is None else str(top_value),  # 列で型が混ざらないよう文字列に揃える
                "top_count": top_count,
                "top_ratio": (top_count / n) if n else 0.0,
            }
        )
    return pl.DataFrame(rows) if rows else pl.DataFrame(schema={"column": pl.String, "n_unique": pl.Int64})


def profile(df: pl.DataFrame, *, max_categories: int = 50) -> TableProfile:
    """テーブルの基本レポート（列の欠損・型・一意数／数値の統計量／カテゴリの最頻／重複行数）。

    max_categories：これ以下の一意数の列はカテゴリ扱いでも要約する（String は常にカテゴリ扱い）。
    """
    return TableProfile(
        n_rows=df.height,
        n_columns=df.width,
        columns=_column_overview(df),
        numeric=_numeric_overview(df),
        categorical=_categorical_overview(df, max_categories=max_categories),
        duplicate_rows=df.height - df.n_unique(),
    )


def target_summary(df: pl.DataFrame, *, target: str, task: Task = "classification") -> dict[str, Any]:
    """目的変数の要約。分類＝クラス別の件数と比率（不均衡度）。回帰＝統計量。

    「目的変数を確認せずに学習へ進まない」（参考リポの禁止事項）の機械的な入り口。
    """
    if target not in df.columns:
        raise ValueError(f"目的変数の列 '{target}' がテーブルに無い（列: {df.columns}）")
    s = df[target]
    n = s.len()
    if task == "regression":
        return {
            "task": "regression",
            "n": n,
            "mean": _f(s.mean()),
            "std": _f(s.std()),
            "min": _f(s.min()),
            "q25": _f(s.quantile(0.25)),
            "median": _f(s.median()),
            "q75": _f(s.quantile(0.75)),
            "max": _f(s.max()),
        }
    vc = s.value_counts(sort=True)
    counts = {row[target]: int(row["count"]) for row in vc.iter_rows(named=True)}
    ratios = {k: (v / n if n else 0.0) for k, v in counts.items()}
    return {"task": "classification", "n": n, "n_classes": len(counts), "counts": counts, "ratios": ratios}


def _f(value: Any) -> float | None:  # noqa: ANN401  polars 集計は数値 or None
    """polars 集計値を素の float（または None）にする（YAML 化と型の一貫のため）。"""
    return None if value is None else float(value)
