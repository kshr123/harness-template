"""OOF 予測の深掘り：セグメント別指標・誤差の大きい行・並べ替え重要度・回帰の残差。

すべて OOF/valid の予測で呼ぶ（train の予測で呼ぶと過大評価・test のラベルは使わない）。入口
（cv_permutation_importance）は fold の valid 行だけを使う形にして、この規律を構造で守る（DESIGN §1-3・§9-3）。
指標の計算は eval（METRICS＝sklearn）へ委譲し、ここでは並べ替え・グループ化・残差だけを持つ。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray

from harness.ds import eval as ev
from harness.ds.cv import CVResult, _predict

Task = Literal["classification", "regression"]
Predict = Literal["proba", "value"]


def segment_metrics(
    segments: pl.Series,
    y_true: NDArray[Any],
    y_score: NDArray[np.float64],
    *,
    task: Task = "classification",
    threshold: float = 0.5,
    metrics: Sequence[str] | None = None,
) -> pl.DataFrame:
    """セグメント（カテゴリ列）別の指標表（列 = segment, count, <指標...>・count 降順）。

    指標の計算は eval の evaluate / evaluate_regression に委譲（polars group_by で回すだけ）。回帰は residual_mean
    列も足す（予測レンジ別の偏りが見える）。OOF 予測（cv.oof[oof_mask]）で呼ぶこと。連続値で切りたいときは
    事前に列をビン化して渡す（polars の qcut 1 式・ビン化専用関数は作らない）。
    """
    frame = pl.DataFrame({"segment": segments, "_y": y_true, "_s": y_score})
    rows: list[dict[str, Any]] = []
    for key, group in frame.group_by("segment"):
        yt, ys = group["_y"].to_numpy(), group["_s"].to_numpy()
        if task == "regression":
            row = ev.evaluate_regression(yt.astype(np.float64), ys, metrics=metrics)
            row["residual_mean"] = float(np.mean(yt - ys))
        else:
            row = ev.evaluate(yt.astype(np.int_), ys, threshold=threshold, metrics=metrics)
        rows.append({"segment": str(key[0]), "count": group.height, **row})
    return pl.DataFrame(rows).sort("count", descending=True)


def worst_rows(
    df: pl.DataFrame,
    y_true: NDArray[Any],
    y_score: NDArray[np.float64],
    *,
    n: int = 20,
    task: Task = "classification",
) -> pl.DataFrame:
    """誤差の大きい行の一覧（df の列＋ y_true, y_score, error・error 降順の上位 n）。

    error は分類＝|y_true − y_score|（確率との差）・回帰＝|y_true − y_pred|。どんな行で外しているかを
    特徴量追加の仮説にする入り口。
    """
    error = np.abs(y_true.astype(np.float64) - y_score)
    out = df.with_columns(
        y_true=pl.Series("y_true", y_true),
        y_score=pl.Series("y_score", y_score),
        error=pl.Series("error", error),
    )
    return out.sort("error", descending=True).head(n)


def residual_summary(y_true: NDArray[np.float64], y_pred: NDArray[np.float64]) -> dict[str, float]:
    """回帰の残差（y_true − y_pred）の要約。mean が 0 から離れていれば系統的な偏り（過大/過小予測）。

    分布の形は marimo でヒストグラム表示（sklearn の PredictionErrorDisplay は図＝正本にできない・ここは数表）。
    """
    r = y_true.astype(np.float64) - y_pred.astype(np.float64)
    return {
        "mean": float(np.mean(r)),
        "std": float(np.std(r)),
        "min": float(np.min(r)),
        "q25": float(np.quantile(r, 0.25)),
        "median": float(np.median(r)),
        "q75": float(np.quantile(r, 0.75)),
        "max": float(np.max(r)),
    }


def _metric_value(name: str, y_true: NDArray[Any], pred: NDArray[np.float64], *, threshold: float) -> float:
    """METRICS の 1 指標を、input 種別（score/label/value）に応じた入力で計算する。"""
    metric = ev.METRICS[name]
    # MetricEntry.fn は Callable[..., Any]（レジストリの汎用形）＝返りは float に丸めて型を確定させる。
    if metric.input == "label":
        return float(metric.fn(y_true.astype(np.int_), (pred >= threshold).astype(np.int_)))
    if metric.input == "value":
        return float(metric.fn(y_true.astype(np.float64), pred))
    return float(metric.fn(y_true.astype(np.int_), pred))  # score


def permutation_importance(
    estimator: object,
    x: pl.DataFrame,
    y: NDArray[Any],
    *,
    metric: str,
    seed: int,
    n_repeats: int = 5,
    columns: Sequence[str] | None = None,
    predict: Predict = "proba",
    threshold: float = 0.5,
) -> pl.DataFrame:
    """入力列の並べ替え重要度（列 = column, importance_mean, importance_std・重要度は悪化量）。

    importance は「その列を壊すと指標がどれだけ悪くなるか」で、METRICS の向きで符号を揃える（常に大きいほど効く）。
    estimator は学習済みの Pipeline 丸ごと（モデル非依存）。x は fit に使っていない行（fold の valid / holdout）で呼ぶ。
    sklearn.inspection.permutation_importance を使わない理由（DEC-0008）：numpy/pandas 入力前提で、polars 入力
    （特に MultiHot の list 列）の Pipeline に入らない。並べ替えの繰り返しだけ自作し、指標計算は METRICS へ委譲する。
    """
    cols = list(columns) if columns is not None else x.columns
    higher_is_better = ev.METRICS[metric].higher_is_better
    rng = np.random.default_rng(seed)
    base = _metric_value(metric, y, _predict(estimator, x, predict), threshold=threshold)
    rows: list[dict[str, Any]] = []
    for c in cols:
        deltas = []
        for _ in range(n_repeats):
            shuffled = x[c].gather(rng.permutation(x.height))
            score = _metric_value(
                metric, y, _predict(estimator, x.with_columns(shuffled.alias(c)), predict), threshold=threshold
            )
            deltas.append((base - score) if higher_is_better else (score - base))  # 悪化量（常に正が効いている）
        rows.append({"column": c, "importance_mean": float(np.mean(deltas)), "importance_std": float(np.std(deltas))})
    return pl.DataFrame(rows).sort("importance_mean", descending=True)


def cv_permutation_importance(
    cv: CVResult,
    x: pl.DataFrame,
    y: NDArray[Any],
    splits: Sequence[tuple[NDArray[np.int64], NDArray[np.int64]]],
    *,
    metric: str,
    seed: int,
    n_repeats: int = 5,
    columns: Sequence[str] | None = None,
    predict: Predict = "proba",
    threshold: float = 0.5,
) -> pl.DataFrame:
    """CV 全体の並べ替え重要度（推奨の入口）。fold k の estimator を「その fold の valid 行」だけで評価して平均。

    「OOF なしに重要度を解釈しない」（参考リポの禁止事項）を引数の形で守る。drift_auc の結果にも使える
    （DriftResult.estimators＋同じ splits を渡す＝分布差の原因列の特定）。
    """
    per_fold = []
    for k, (_, valid_idx) in enumerate(splits):
        rows = valid_idx.tolist()
        imp = permutation_importance(
            cv.estimators[k],
            x[rows],
            y[valid_idx],
            metric=metric,
            seed=seed + k,
            n_repeats=n_repeats,
            columns=columns,
            predict=predict,
            threshold=threshold,
        )
        per_fold.append(imp)
    combined = pl.concat(per_fold)
    return (
        combined.group_by("column")
        .agg(pl.col("importance_mean").mean(), pl.col("importance_std").mean())
        .sort("importance_mean", descending=True)
    )


def partial_dependence_table(
    estimator: object,
    x: pl.DataFrame,
    feature: str,
    *,
    grid: Sequence[float] | None = None,
    n_points: int = 20,
    predict: Predict = "proba",
) -> pl.DataFrame:
    """部分依存表＝入力列を振って平均予測の形を見る（列 = feature_value, avg_prediction・feature_value 昇順）。

    permutation_importance が「どの列が効くか」なら、こちらは「どう効くか（形）」。各グリッド値 v について
    x の feature 列を全行 v に置換し、_predict（proba は陽性確率）の平均を取る（ICE 平均の PDP・学習済み
    Pipeline 丸ごと・モデル非依存）。x は fit に使っていない行（fold の valid / holdout）で呼ぶ。
    グリッドは grid 指定時はその値。未指定時は x[feature] のユニーク数が n_points 以下ならユニーク値そのもの
    （離散/カテゴリ・ソート）、多ければ min..max の n_points 等分（np.linspace）。feature は数値列が前提
    （文字列などの非数値列は grid= に値を渡しても float へ落とすため使えない。事前にエンコードするか数値列で呼ぶ）。
    置換は feature 列の**元 dtype を保つ**（Int64 列を Float64 に化かすと CountEncode/GroupAggregate 等の join 系
    エンコーダが SchemaError で落ちるため）。**二値分類（proba＝陽性確率 1 次元）か回帰（value）向け**：多クラス proba
    （n×クラス数）は平均が無意味になるため非対応（クラス別に呼ぶか value を使う・下で fail-closed に検出する）。
    sklearn.inspection.partial_dependence を使わない理由（DEC-0008）：numpy/pandas 入力前提で、polars 入力
    （特に MultiHot の list 列）の Pipeline に入らない。グリッドの置換だけ自作し、予測は _predict へ委譲する。
    """
    if grid is not None:
        values = sorted(float(v) for v in grid)
    else:
        unique = [float(v) for v in x[feature].drop_nulls().unique().sort().to_list()]
        if len(unique) <= n_points:
            values = unique  # 離散/カテゴリ：ユニーク値そのもの（ソート済み）
        else:
            values = [float(v) for v in np.linspace(unique[0], unique[-1], n_points)]  # 連続：min..max 等分
    dtype = x.schema[feature]  # 置換で元 dtype を保つ（join 系エンコーダの f64 vs i64 SchemaError を防ぐ）
    avg: list[float] = []
    for v in values:
        pred = np.asarray(_predict(estimator, x.with_columns(pl.lit(v).cast(dtype).alias(feature)), predict))
        if pred.ndim != 1:  # 多クラス proba（n×クラス数）＝平均が 1/k に潰れて黙って誤る → 検出して止める
            raise ValueError(
                f"partial_dependence_table は二値分類か回帰向け（多クラス proba 形 {pred.shape} は非対応）"
                "＝クラス別に呼ぶか predict='value' を使う"
            )
        avg.append(float(pred.mean()))
    return pl.DataFrame({"feature_value": values, "avg_prediction": avg})
