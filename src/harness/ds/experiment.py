"""実験ループの一気通貫（薄い接着）。

`run_experiment` が「fold 作成 → 交差検証 → 合否判定」を 1 本で通す。保存や results の書き出しは
実験スクリプト（work/…/code/train.py）が担い、ここは計算の流れだけを持つ（テストしやすく・再利用できる）。
特徴量→モデルは呼び出し側が 1 本の sklearn Pipeline として渡す（run_cv が fold ごとに clone する）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray

from harness.ds.cv import CVResult, SklearnLike, fold_indices, make_folds, run_cv
from harness.ds.eval import passes


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
    predict: Literal["proba", "value"] = "proba",
) -> ExperimentResult:
    """fold を作り、estimator を交差検証し、OOF 指標が閾値を満たすか（passed）まで一気に返す。

    estimator は特徴量→モデルの 1 本の Pipeline。run_cv が fold ごとに clone→train で fit するので、
    特徴量の学習も train でだけ起き、漏れは構造的に起きない。
    """
    folds = make_folds(df, n_folds=n_folds, seed=seed, id_column=id_column, stratify_by=stratify_by)
    splits = fold_indices(df, folds, id_column=id_column)
    cv_result = run_cv(estimator, df, y, splits, predict=predict)
    return ExperimentResult(folds=folds, cv=cv_result, passed=passes(cv_result.oof_metrics, dict(thresholds)))
