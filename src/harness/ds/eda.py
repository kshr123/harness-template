"""EDA（探索的データ分析）の第一の出力＝機械可読な構造化レポート（polars/dict）。

- 図でなくデータで返す（テストでき・エージェントが読める）。人が図で見たいときは notebooks/eda.py（marimo）が
  この同じ関数を呼んで表と図にする（正本はここ・ビューは薄い）。DESIGN §4 判断1。
- 集計は polars（describe/null_count/n_unique/value_counts）に委譲し、束ねるだけ（再発明しない）。
- train/test の比較（compare/psi/drift_auc）は別関数で、2 つの DataFrame を別々に集計する
  （結合してから集計する経路をこのモジュールに置かない＝リーク禁止を API の形で守る）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import polars as pl
import polars.selectors as cs

Task = Literal["classification", "regression"]


@dataclass(frozen=True)
class TableProfile:
    """1 テーブルの構造化レポート。to_dict() で YAML にそのまま落ちる（正本→保存/ビューの写像）。"""

    n_rows: int
    n_columns: int
    columns: pl.DataFrame  # column, dtype, null_count, null_ratio, n_unique（df の列順）
    numeric: (
        pl.DataFrame
    )  # column, mean/std/min/q25/median/q75/max, skew, kurtosis, iqr_lower/upper, n_outliers, outlier_ratio
    categorical: pl.DataFrame  # column, n_unique, top_value, top_count, top_ratio
    duplicate_rows: int  # 全列一致の重複行数（= n_rows − 相異なる行数）
    datetime: pl.DataFrame  # column, min, max, n_unique（日時列のみ・無ければ 0 行）
    flags: pl.DataFrame  # column, flag, detail（怪しい列の一覧・0 行なら異常なし）

    def to_dict(self) -> dict[str, Any]:
        """キー順を固定して dict にする（決定的な出力）。polars は行の list[dict] へ。"""
        return {
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
            "columns": self.columns.to_dicts(),
            "numeric": self.numeric.to_dicts(),
            "categorical": self.categorical.to_dicts(),
            "duplicate_rows": self.duplicate_rows,
            "datetime": self.datetime.to_dicts(),
            "flags": self.flags.to_dicts(),
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


def _numeric_row(df: pl.DataFrame, c: str) -> dict[str, Any]:
    s = df[c]
    q25, q75 = _f(s.quantile(0.25)), _f(s.quantile(0.75))
    lower = upper = n_out = ratio = None
    if q25 is not None and q75 is not None:
        iqr = q75 - q25
        lower, upper = q25 - 1.5 * iqr, q75 + 1.5 * iqr  # Tukey の柵
        non_null = s.drop_nulls()
        n_out = int(((non_null < lower) | (non_null > upper)).sum())
        ratio = (n_out / non_null.len()) if non_null.len() else 0.0
    return {
        "column": c,
        "mean": _f(s.mean()),
        "std": _f(s.std()),
        "min": _f(s.min()),
        "q25": q25,
        "median": _f(s.median()),
        "q75": q75,
        "max": _f(s.max()),
        "skew": _f(s.skew()),
        "kurtosis": _f(s.kurtosis()),
        "iqr_lower": lower,
        "iqr_upper": upper,
        "n_outliers": n_out,
        "outlier_ratio": ratio,
    }


def _numeric_overview(df: pl.DataFrame) -> pl.DataFrame:
    cols = df.select(cs.numeric()).columns
    rows = [_numeric_row(df, c) for c in cols]
    floats = ["mean", "std", "min", "q25", "median", "q75", "max"]
    floats += ["skew", "kurtosis", "iqr_lower", "iqr_upper", "outlier_ratio"]
    schema: dict[str, Any] = {"column": pl.String} | {k: pl.Float64 for k in floats} | {"n_outliers": pl.Int64}
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def _datetime_overview(df: pl.DataFrame) -> pl.DataFrame:
    rows = [
        {"column": c, "min": str(df[c].min()), "max": str(df[c].max()), "n_unique": int(df[c].n_unique())}
        for c in df.columns
        if df.schema[c].is_temporal()
    ]
    schema: dict[str, Any] = {"column": pl.String, "min": pl.String, "max": pl.String, "n_unique": pl.Int64}
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def _flags_overview(df: pl.DataFrame, *, quasi_constant_ratio: float) -> pl.DataFrame:
    n = df.height
    rows: list[dict[str, Any]] = []
    for c in df.columns:
        s = df[c]
        nu = s.n_unique()
        null_ratio = (s.null_count() / n) if n else 0.0
        if null_ratio == 1.0:
            rows.append({"column": c, "flag": "all_null", "detail": "全行が欠損"})
            continue
        if nu == 1:
            rows.append({"column": c, "flag": "constant", "detail": "一意数 1（学習に寄与しない）"})
            continue
        vc = s.drop_nulls().value_counts(sort=True)
        top_ratio = (int(vc["count"][0]) / n) if (vc.height and n) else 0.0
        if top_ratio >= quasi_constant_ratio:
            rows.append({"column": c, "flag": "quasi_constant", "detail": f"最頻値の比率 {top_ratio:.3f}"})
        if nu == n and (s.dtype.is_integer() or s.dtype == pl.String):
            rows.append({"column": c, "flag": "id_like", "detail": "一意数=行数（識別子疑い・リークの温床）"})
    schema: dict[str, Any] = {"column": pl.String, "flag": pl.String, "detail": pl.String}
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


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


def profile(df: pl.DataFrame, *, max_categories: int = 50, quasi_constant_ratio: float = 0.99) -> TableProfile:
    """テーブルの基本レポート（列の欠損・型・一意数／数値の統計量・外れ値／カテゴリの最頻／重複行数／日時／品質フラグ）。

    max_categories：これ以下の一意数の列はカテゴリ扱いでも要約する（String は常にカテゴリ扱い）。
    quasi_constant_ratio：最頻値の比率がこれ以上なら準定数フラグ（既定 0.99）。
    """
    return TableProfile(
        n_rows=df.height,
        n_columns=df.width,
        columns=_column_overview(df),
        numeric=_numeric_overview(df),
        categorical=_categorical_overview(df, max_categories=max_categories),
        duplicate_rows=df.height - df.n_unique(),
        datetime=_datetime_overview(df),
        flags=_flags_overview(df, quasi_constant_ratio=quasi_constant_ratio),
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


def missing_patterns(df: pl.DataFrame, *, top: int = 20) -> pl.DataFrame:
    """欠損の同時発生パターン（列 = columns（欠損列名の list）, count, ratio・count 降順・上位 top）。

    「どの列がまとまって欠けるか」（同一原因の欠損・結合漏れ）を行単位で見る。全列非欠損の行は columns=[]。
    """
    cols = df.columns
    null_flags = df.select([pl.col(c).is_null() for c in cols])
    patterns: dict[tuple[str, ...], int] = {}
    for row in null_flags.iter_rows():
        key = tuple(c for c, is_null in zip(cols, row, strict=True) if is_null)
        patterns[key] = patterns.get(key, 0) + 1
    n = df.height
    ordered = sorted(patterns.items(), key=lambda kv: kv[1], reverse=True)[:top]
    rows = [{"columns": list(k), "count": v, "ratio": (v / n if n else 0.0)} for k, v in ordered]
    schema: dict[str, Any] = {"columns": pl.List(pl.String), "count": pl.Int64, "ratio": pl.Float64}
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def duplicate_columns(df: pl.DataFrame) -> pl.DataFrame:
    """内容が同一の列ペア（列 = column, duplicate_of（先に現れた列名））。0 行なら重複なし。

    null 同士は等しいとみなす（eq_missing）。列内容のハッシュで候補を絞ってから全比較（総当たりを避ける）。
    片方を落とす判断はエージェント/実験側（ここは事実の報告だけ）。
    """
    buckets: dict[int, list[str]] = {}
    rows: list[dict[str, Any]] = []
    for c in df.columns:
        fingerprint = hash(tuple(df[c].hash().to_list()))  # 内容＋null 位置が同じなら同じ指紋
        match = next((p for p in buckets.get(fingerprint, []) if bool(df[c].eq_missing(df[p]).all())), None)
        if match is not None:
            rows.append({"column": c, "duplicate_of": match})
        else:
            buckets.setdefault(fingerprint, []).append(c)
    schema: dict[str, Any] = {"column": pl.String, "duplicate_of": pl.String}
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def category_target_summary(
    df: pl.DataFrame,
    *,
    target: str,
    columns: Sequence[str] | None = None,
    max_categories: int = 50,
    top: int = 20,
) -> pl.DataFrame:
    """カテゴリ×目的変数（列 = column, value, count, ratio, target_mean・各列 count 上位 top）。

    分類なら target_mean＝そのカテゴリの陽性率・回帰なら平均。件数の多いカテゴリで target_mean が 0/1 に
    張り付いていたらリーク疑い（目安・門番にはしない）。専用のリーク検出関数は作らない（correlations でも読める）。
    """
    if target not in df.columns:
        raise ValueError(f"目的変数の列 '{target}' がテーブルに無い（列: {df.columns}）")

    def _is_cat(c: str) -> bool:
        return c != target and (df.schema[c] == pl.String or df[c].n_unique() <= max_categories)

    cat_cols = list(columns) if columns is not None else [c for c in df.columns if _is_cat(c)]
    n = df.height
    rows: list[dict[str, Any]] = []
    for c in cat_cols:
        agg = (
            df.group_by(c)
            .agg(pl.len().alias("count"), pl.col(target).mean().alias("target_mean"))
            .sort("count", descending=True)
            .head(top)
        )
        for row in agg.iter_rows(named=True):
            rows.append(
                {
                    "column": c,
                    "value": str(row[c]),
                    "count": int(row["count"]),
                    "ratio": (int(row["count"]) / n) if n else 0.0,
                    "target_mean": _f(row["target_mean"]),
                }
            )
    schema: dict[str, Any] = {
        "column": pl.String,
        "value": pl.String,
        "count": pl.Int64,
        "ratio": pl.Float64,
        "target_mean": pl.Float64,
    }
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    """ピアソン相関。両方が有限な行だけで計算（pairwise-complete。null→NaN が 1 個でも全体を NaN にしない）。

    有効行 2 未満・どちらかが定数（分散 0）なら 0.0（NaN を黙って混ぜない）。
    """
    m = np.isfinite(x) & np.isfinite(y)
    if int(m.sum()) < 2 or np.std(x[m]) == 0 or np.std(y[m]) == 0:
        return 0.0
    return float(np.corrcoef(x[m], y[m])[0, 1])


def correlations(df: pl.DataFrame, *, target: str, columns: Sequence[str] | None = None) -> pl.DataFrame:
    """数値列と目的変数の相関（列 = feature, correlation・|r| 降順）。定数列は 0.0。

    リーク疑い・効きそうな特徴の当たりを付ける読み口（門番にはしない・値は事実）。
    """
    if target not in df.columns:
        raise ValueError(f"目的変数の列 '{target}' がテーブルに無い（列: {df.columns}）")
    cols = list(columns) if columns is not None else [c for c in df.select(cs.numeric()).columns if c != target]
    t = df[target].to_numpy().astype(np.float64)
    rows = [{"feature": c, "correlation": _corr(df[c].to_numpy().astype(np.float64), t)} for c in cols]
    schema: dict[str, Any] = {"feature": pl.String, "correlation": pl.Float64}
    out = pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)
    return out.sort(pl.col("correlation").abs(), descending=True)


def high_correlation_pairs(
    df: pl.DataFrame, *, threshold: float = 0.99, columns: Sequence[str] | None = None
) -> pl.DataFrame:
    """相関の高い列ペア（列 = a, b, correlation・|r| 降順）。既定 0.99＝リーク/重複疑い。

    0.8 に下げれば多重共線性の点検にも使える（引数で外から）。定数列は相関が定義できないので除く。
    """
    cols = list(columns) if columns is not None else df.select(cs.numeric()).columns
    vals = {c: df[c].to_numpy().astype(np.float64) for c in cols}
    rows = []
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            r = _corr(vals[a], vals[b])
            if abs(r) >= threshold:
                rows.append({"a": a, "b": b, "correlation": r})
    schema: dict[str, Any] = {"a": pl.String, "b": pl.String, "correlation": pl.Float64}
    out = pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)
    return out.sort(pl.col("correlation").abs(), descending=True)


def psi(train: pl.Series, test: pl.Series, *, bins: int = 10) -> float:
    """PSI（母集団安定性指標）。数値＝ビン境界は train の分位点だけから作る（test を見ない＝リーク無し）。

    カテゴリ＝train に現れたカテゴリ＋「その他」1 束。空ビンは小さい床値（1e-6）で 0 割を防ぐ。
    目安：0.1 未満=安定・0.1〜0.25=要注意・0.25 以上=大きな変化（門番にはしない）。
    """
    floor = 1e-6
    if train.dtype.is_numeric():
        train_values = train.drop_nulls().to_numpy()
        if len(train_values) == 0:
            return 0.0  # train が全欠損＝分位点を計算できない。分布差は測れないので 0 とする
        edges = np.unique(np.quantile(train_values, np.linspace(0.0, 1.0, bins + 1)))
        if len(edges) < 2:
            return 0.0  # train が定数（分位点が 1 点）＝ビンを切れない。分布差は測れないので 0 とする
        edges[0], edges[-1] = -np.inf, np.inf  # 外側ビンを開く＝train の範囲外に出た test の質量を落とさない
        e_counts, _ = np.histogram(train_values, bins=edges)
        a_counts, _ = np.histogram(test.drop_nulls().to_numpy(), bins=edges)
        e = np.maximum(e_counts / max(e_counts.sum(), 1), floor)
        a = np.maximum(a_counts / max(a_counts.sum(), 1), floor)
    else:
        cats = train.drop_nulls().unique().to_list()

        def _props(s: pl.Series) -> np.ndarray:
            n = max(s.len(), 1)
            counts = dict.fromkeys(cats, 0)
            other = 0
            for row in s.value_counts().iter_rows(named=True):
                value, cnt = row[s.name], row["count"]
                if value in counts:
                    counts[value] = cnt
                elif value is not None:
                    other += cnt
            props = [counts[k] / n for k in cats] + [other / n]
            floored: np.ndarray = np.maximum(np.array(props), floor)
            return floored

        e, a = _props(train), _props(test)
    return float(np.sum((a - e) * np.log(a / e)))


@dataclass(frozen=True)
class CompareReport:
    """train/test 比較の構造化レポート。統計は各側で別々に計算済み（結合統計は存在しない＝リーク無し）。"""

    n_train: int
    n_test: int
    numeric: pl.DataFrame  # column, train_mean, test_mean, train_std, test_std, mean_gap, psi
    categorical: pl.DataFrame  # column, n_train_only, n_test_only, train_only_top, test_only_top, test_coverage, psi

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_train": self.n_train,
            "n_test": self.n_test,
            "numeric": self.numeric.to_dicts(),
            "categorical": self.categorical.to_dicts(),
        }


def compare(
    train: pl.DataFrame,
    test: pl.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    max_categories: int = 50,
    psi_bins: int = 10,
) -> CompareReport:
    """train/test の列ごとの分布比較（統計量・カテゴリの共通/固有・PSI）。

    リーク禁止は API の形で守る：2 つの DataFrame を受け、各側で独立に集計する（結合してから集計しない）。
    """
    common = [c for c in train.columns if c in test.columns]
    if columns is not None:
        common = [c for c in columns if c in common]
    num_cols = [c for c in common if train.schema[c].is_numeric() and test.schema[c].is_numeric()]
    cat_cols = [
        c
        for c in common
        if c not in num_cols and (train.schema[c] == pl.String or train[c].n_unique() <= max_categories)
    ]

    num_rows = []
    for c in num_cols:
        tm, um, ts, us = _f(train[c].mean()), _f(test[c].mean()), _f(train[c].std()), _f(test[c].std())
        gap = None if (ts is None or ts == 0 or tm is None or um is None) else abs(tm - um) / ts
        num_rows.append(
            {
                "column": c,
                "train_mean": tm,
                "test_mean": um,
                "train_std": ts,
                "test_std": us,
                "mean_gap": gap,
                "psi": psi(train[c], test[c], bins=psi_bins),
            }
        )

    cat_rows = []
    for c in cat_cols:
        tr_set = set(train[c].drop_nulls().unique().to_list())
        te_set = set(test[c].drop_nulls().unique().to_list())
        train_only, test_only = tr_set - te_set, te_set - tr_set
        covered = int(test[c].is_in(list(tr_set)).sum()) if tr_set else 0
        cat_rows.append(
            {
                "column": c,
                "n_train_only": len(train_only),
                "n_test_only": len(test_only),
                "train_only_top": [str(x) for x in sorted(train_only, key=str)[:5]],
                "test_only_top": [str(x) for x in sorted(test_only, key=str)[:5]],
                "test_coverage": (covered / test.height) if test.height else 0.0,
                "psi": psi(train[c], test[c], bins=psi_bins),
            }
        )

    num_schema: dict[str, Any] = {
        "column": pl.String,
        "train_mean": pl.Float64,
        "test_mean": pl.Float64,
        "train_std": pl.Float64,
        "test_std": pl.Float64,
        "mean_gap": pl.Float64,
        "psi": pl.Float64,
    }
    cat_schema: dict[str, Any] = {
        "column": pl.String,
        "n_train_only": pl.Int64,
        "n_test_only": pl.Int64,
        "train_only_top": pl.List(pl.String),
        "test_only_top": pl.List(pl.String),
        "test_coverage": pl.Float64,
        "psi": pl.Float64,
    }
    return CompareReport(
        n_train=train.height,
        n_test=test.height,
        numeric=pl.DataFrame(num_rows, schema=num_schema) if num_rows else pl.DataFrame(schema=num_schema),
        categorical=pl.DataFrame(cat_rows, schema=cat_schema) if cat_rows else pl.DataFrame(schema=cat_schema),
    )


@dataclass(frozen=True)
class DriftResult:
    """train/test を見分ける分類器の成績。auc=0.5 は見分けられない（分布が近い）。"""

    auc: float
    fold_aucs: list[float]
    n_train: int
    n_test: int
    estimators: list[object]  # fold 別の学習済み Pipeline（原因列は analysis.cv_permutation_importance で）


def drift_auc(
    train: pl.DataFrame,
    test: pl.DataFrame,
    *,
    columns: Sequence[str],
    seed: int,
    n_folds: int = 5,
    spec: Mapping[str, Any] | None = None,
    model: Mapping[str, Any] | None = None,
) -> DriftResult:
    """train/test を見分ける分類器を交差検証し OOF AUC を返す（adversarial validation）。

    実装は既存部品の合成だけ：特徴量列だけを縦に結合し、所属（train=0/test=1）を y にして
    build_estimator → make_folds(stratify_by=所属) → run_cv。目的変数は一切使わない（リーク無し）。
    既定の spec は columns 素通し＝数値列向け（カテゴリは spec に onehot を渡す）。AUC が高い（目安 0.7 以上）ときは
    効く列を analysis.cv_permutation_importance で特定して原因を調べる。
    """
    from harness.ds import cv
    from harness.ds.pipeline import build_estimator, build_model

    cols = list(columns)
    combined = pl.concat([train.select(cols), test.select(cols)], how="vertical")
    y = np.array([0] * train.height + [1] * test.height, dtype=np.int64)
    labelled = combined.with_columns(__membership__=pl.Series(y)).with_row_index("__id__")

    est_spec = spec if spec is not None else {"features": [{"kind": "columns", "columns": cols}]}
    estimator = build_estimator(est_spec, build_model(model or {"kind": "logreg"}, seed=seed), seed=seed)
    folds = cv.make_folds(labelled, n_folds=n_folds, seed=seed, id_column="__id__", stratify_by="__membership__")
    splits = cv.fold_indices(labelled, folds, id_column="__id__")
    result = cv.run_cv(estimator, combined, y.astype(np.float64), splits, predict="proba")
    return DriftResult(
        auc=result.oof_metrics["roc_auc"],
        fold_aucs=[m["roc_auc"] for m in result.fold_metrics],
        n_train=train.height,
        n_test=test.height,
        estimators=result.estimators,
    )
