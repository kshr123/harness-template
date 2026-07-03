"""交差検証（CV）と固定分割：fold 割当・添字対のリスト・run_cv。

- 分割は「行番号の対のリスト」で渡す（固定分割＝要素1・CV＝要素k）。形をそろえる。
- fold 割当は表 (id, fold) にして split 層に保存でき、再現をコードでなくデータで担保する。
- 分割の計算そのものは sklearn（KFold/StratifiedKFold）を使う（再発明しない）。
- run_cv は estimator（sklearn 互換の Pipeline 等）を **fold ごとに clone して train 側だけで fit** する。
  これで特徴量の学習も train でだけ起き、valid の統計が混ざらない（漏れ防止が規約でなく構造）。
- 未カバー行の黙認を避けるため CVResult は oof に加えて oof_mask を持つ（固定分割でも同じ関数が正しく使える）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

import numpy as np
import polars as pl
from numpy.typing import NDArray
from sklearn.base import clone
from sklearn.model_selection import KFold, StratifiedKFold

from harness.ds.eval import evaluate

Splits = Sequence[tuple[NDArray[np.int64], NDArray[np.int64]]]
MetricFn = Callable[[NDArray[np.int_], NDArray[np.float64]], dict[str, float]]


@runtime_checkable
class SklearnLike(Protocol):
    """sklearn 互換の最小契約（clone できる＝get_params を持ち、fit できる）。

    LogisticRegression も LGBMClassifier も Pipeline も FeaturePipeline もこれを満たす。
    run_cv はこの型だけに依存し、モデルの具体を知らない（差し替えは estimator の交換だけ）。
    """

    def fit(self, x: object, y: object) -> object: ...
    def get_params(self, deep: bool = True) -> dict[str, object]: ...


def make_folds(
    df: pl.DataFrame,
    *,
    n_folds: int,
    seed: int,
    id_column: str = "id",
    stratify_by: str | None = None,
) -> pl.DataFrame:
    """fold 割当表 (id_column, fold) を作る。同じ (df, seed) なら必ず同じ表。

    分割は scikit-learn の標準実装を使う（再発明しない）：無層化は KFold、層化は StratifiedKFold
    （クラス比率を保つ）。どちらも shuffle・random_state=seed で再現する。
    """
    if n_folds < 2:
        raise ValueError("n_folds は 2 以上にすること")
    n = df.height
    if n < n_folds:
        raise ValueError(f"行数 {n} が n_folds {n_folds} より少ない")
    fold = np.empty(n, dtype=np.int64)
    rows = np.arange(n)
    if stratify_by is None:
        splitter = KFold(n_splits=n_folds, shuffle=True, random_state=seed)
        for k, (_, valid) in enumerate(splitter.split(rows)):
            fold[valid] = k
    else:
        strat = df[stratify_by].to_numpy()
        stratified = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
        for k, (_, valid) in enumerate(stratified.split(rows, strat)):
            fold[valid] = k
    return df.select(id_column).with_columns(pl.Series("fold", fold))


def fold_indices(
    df: pl.DataFrame,
    folds: pl.DataFrame,
    *,
    id_column: str = "id",
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """fold 表を df の行番号の対 [(train_idx, valid_idx)] × k に引き直す。

    df の id と fold 表の id が一致しないと失敗する（部分適用の黙認をしない）。
    """
    df_ids = df[id_column].to_list()
    fold_map = dict(zip(folds[id_column].to_list(), folds["fold"].to_list(), strict=True))
    if set(df_ids) != set(fold_map):
        only_df = sorted(set(df_ids) - set(fold_map), key=str)[:3]
        only_table = sorted(set(fold_map) - set(df_ids), key=str)[:3]
        raise ValueError(f"fold 表と df の id が一致しない（df のみ {only_df} / 表のみ {only_table}）")
    assigned = np.array([fold_map[i] for i in df_ids], dtype=np.int64)
    out: list[tuple[NDArray[np.int64], NDArray[np.int64]]] = []
    # 実際に存在する fold 値だけを回す（欠番があっても valid が空の fold を作らない＝空で指標が nan になるのを防ぐ）。
    for k in sorted(set(assigned.tolist())):
        valid = np.nonzero(assigned == k)[0].astype(np.int64)
        train = np.nonzero(assigned != k)[0].astype(np.int64)
        out.append((train, valid))
    return out


def holdout_indices(n_train: int, n_valid: int) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """固定分割用。train を先頭・valid を後ろに連結した行列を前提に、要素 1 のリストを返す。

    固定分割も CV も「添字対のリスト」で学習系へ渡す形をそろえる。
    """
    train = np.arange(0, n_train, dtype=np.int64)
    valid = np.arange(n_train, n_train + n_valid, dtype=np.int64)
    return [(train, valid)]


@dataclass(frozen=True)
class CVResult:
    """CV の結果。oof は全行ぶんの器で、oof_mask が True の行だけ予測が入っている。"""

    oof: NDArray[np.float64]
    oof_mask: NDArray[np.bool_]
    fold_metrics: list[dict[str, float]]
    estimators: list[object]  # fold ごとに学習済みの estimator（Pipeline 丸ごと）
    oof_metrics: dict[str, float]


def _predict(estimator: object, x: pl.DataFrame, how: Literal["proba", "value"]) -> NDArray[np.float64]:
    """valid への予測。分類は陽性の確率（predict_proba[:, 1]）、回帰は predict の値。"""
    if how == "proba":
        proba: NDArray[np.float64] = estimator.predict_proba(x)[:, 1]  # type: ignore[attr-defined]
        return proba
    value: NDArray[np.float64] = np.asarray(estimator.predict(x), dtype=np.float64)  # type: ignore[attr-defined]
    return value


def run_cv(
    estimator: SklearnLike,
    x: pl.DataFrame,
    y: NDArray[np.float64],
    splits: Splits,
    *,
    predict: Literal["proba", "value"] = "proba",
    metric_fn: MetricFn = evaluate,
) -> CVResult:
    """fold ごとに estimator を clone して train 側だけで fit し、valid の予測を oof に格納する。

    - clone するので特徴量の学習も fold の train でだけ起きる（valid の統計が混ざらない＝構造的な漏れ防止）。
    - valid_idx が重複していたら失敗（同じ行に 2 回書く分割は分割の誤り）。
    - 指標は分類（evaluate＝accuracy・roc_auc）を既定にし、y_true は整数ラベルとして渡す（段階1）。
    - 再現性は estimator が持つ random_state に委ねる（fold ごとの独立種は作らない。clone で足りる）。
    """
    n = len(y)
    oof = np.zeros(n, dtype=np.float64)
    oof_mask = np.zeros(n, dtype=np.bool_)
    fold_metrics: list[dict[str, float]] = []
    estimators: list[object] = []
    for train_idx, valid_idx in splits:
        if oof_mask[valid_idx].any():
            raise ValueError("valid_idx が重複している（同じ行に 2 回予測を書く分割は誤り）")
        fitted = clone(estimator)
        fitted.fit(x[train_idx], y[train_idx])
        pred = _predict(fitted, x[valid_idx], predict)
        oof[valid_idx] = pred
        oof_mask[valid_idx] = True
        fold_metrics.append(metric_fn(y[valid_idx].astype(np.int_), pred))
        estimators.append(fitted)
    oof_metrics = metric_fn(y[oof_mask].astype(np.int_), oof[oof_mask])
    return CVResult(
        oof=oof, oof_mask=oof_mask, fold_metrics=fold_metrics, estimators=estimators, oof_metrics=oof_metrics
    )
