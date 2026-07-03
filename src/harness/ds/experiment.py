"""実験ループの一気通貫（薄い接着）。

`run_experiment` が「fold 作成 → 交差検証 → 合否判定」を 1 本で通す。保存や results の書き出しは
実験スクリプト（work/…/code/train.py）が担い、ここは計算の流れだけを持つ（テストしやすく・再利用できる）。
特徴量→モデルは呼び出し側が 1 本の sklearn Pipeline として渡す（run_cv が fold ごとに clone する）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray

from harness.ds.cv import CVResult, SklearnLike, fold_indices, make_folds, make_time_folds, run_cv
from harness.ds.eval import metric_fn_for, passes

Task = Literal["classification", "regression"]


@dataclass(frozen=True)
class ExperimentResult:
    """実験 1 回ぶんの結果。folds は再現のため保存でき、cv は OOF・fold 別モデル・指標を持つ。"""

    folds: pl.DataFrame
    cv: CVResult
    passed: bool

    @property
    def metrics(self) -> dict[str, float]:
        return self.cv.oof_metrics


def run_experiment(
    df: pl.DataFrame,
    y: NDArray[np.float64],
    estimator: SklearnLike,
    *,
    n_folds: int,
    seed: int,
    thresholds: Mapping[str, float],
    id_column: str = "id",
    stratify_by: str | None = None,
    order_by: str | None = None,
    task: Task = "classification",
    threshold: float = 0.5,
    metrics: Sequence[str] | None = None,
    predict: Literal["proba", "value"] | None = None,
) -> ExperimentResult:
    """fold を作り、estimator を交差検証し、OOF 指標が閾値を満たすか（passed）まで一気に返す。

    estimator は特徴量→モデルの 1 本の Pipeline。run_cv が fold ごとに clone→train で fit するので、
    特徴量の学習も train でだけ起き、漏れは構造的に起きない。task で分類/回帰を切り替える（指標と予測の種類が
    task から決まる）。predict 未指定は task から導く（分類=proba・回帰=value）。
    order_by を渡すと時間順分割（過去→未来の拡大窓）になる＝時間の順序があるデータで shuffle CV の誤用を防ぐ
    （stratify_by との同時指定はエラー）。fold 0 は学習専用で OOF に入らない。
    """
    if order_by is not None and stratify_by is not None:
        raise ValueError("order_by（時間順）と stratify_by（層化）は同時に使えない")
    if predict is None:
        predict = "value" if task == "regression" else "proba"
    metric_fn = metric_fn_for(task, threshold=threshold, metrics=metrics)
    if order_by is not None:
        folds = make_time_folds(df, n_folds=n_folds, order_by=order_by, id_column=id_column)
        splits = fold_indices(df, folds, id_column=id_column, how="expanding")
    else:
        folds = make_folds(df, n_folds=n_folds, seed=seed, id_column=id_column, stratify_by=stratify_by)
        splits = fold_indices(df, folds, id_column=id_column)
    cv_result = run_cv(estimator, df, y, splits, predict=predict, metric_fn=metric_fn)
    return ExperimentResult(folds=folds, cv=cv_result, passed=passes(cv_result.oof_metrics, dict(thresholds)))
