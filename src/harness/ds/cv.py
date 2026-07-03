"""交差検証（CV）と固定分割：fold 割当・添字対のリスト・run_cv。

- 分割は「行番号の対のリスト」で学習系へ渡す（固定分割＝要素1・CV＝要素k）。形をそろえる。
- fold 割当は表（id, fold）にして split 層に保存でき、再現をコードでなくデータで担保する。
- run_cv は fold ごとに種を SeedSequence で導出し、trainer に明示引数で渡す（グローバル種を使わない）。
- 未カバー行の黙認を避けるため CVResult は oof に加えて oof_mask を持つ（固定分割でも同じ関数が正しく使える）。
- Trainer は「run_cv が消費する契約」なのでここに置く。具体（SklearnTrainer 等）は別モジュールで実装する。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
import polars as pl
from numpy.typing import NDArray

from harness.ds.eval import evaluate

Splits = Sequence[tuple[NDArray[np.int64], NDArray[np.int64]]]
MetricFn = Callable[[NDArray[np.int_], NDArray[np.float64]], dict[str, float]]


@dataclass(frozen=True)
class FoldOutcome:
    """1 つの fold の学習結果。y_pred は valid への予測（必ず元スケール）。"""

    y_pred: NDArray[np.float64]
    model: object
    feature_importance: NDArray[np.float64] | None = None


@runtime_checkable
class Trainer(Protocol):
    """1 fold を学習する契約。seed は明示引数（呼ぶ場所で決めた種だけが効く）。"""

    def train(
        self,
        x_train: NDArray[np.float64],
        y_train: NDArray[np.float64],
        x_valid: NDArray[np.float64],
        y_valid: NDArray[np.float64],
        *,
        seed: int,
    ) -> FoldOutcome: ...


def make_folds(
    df: pl.DataFrame,
    *,
    n_folds: int,
    seed: int,
    id_column: str = "id",
    stratify_by: str | None = None,
) -> pl.DataFrame:
    """fold 割当表 (id_column, fold) を作る。同じ (df, seed) なら必ず同じ表（純 numpy）。

    - 無層化：行の並びをシャッフルし n_folds に等分（各 fold の行数差は高々 1）。
    - 層化：stratify_by の値ごとにシャッフルして順に fold を配る（各 fold 内のクラス件数差はクラスごとに高々 1）。
    """
    if n_folds < 2:
        raise ValueError("n_folds は 2 以上にすること")
    n = df.height
    if n < n_folds:
        raise ValueError(f"行数 {n} が n_folds {n_folds} より少ない")
    rng = np.random.default_rng(seed)
    fold = np.empty(n, dtype=np.int64)
    if stratify_by is None:
        for k, group in enumerate(np.array_split(rng.permutation(n), n_folds)):
            fold[group] = k
    else:
        strat = df[stratify_by].to_numpy()
        for value in np.unique(strat):  # 値の昇順＝決定的な反復（再現性）
            idx = np.nonzero(strat == value)[0]
            shuffled = rng.permutation(idx)
            fold[shuffled] = np.arange(len(shuffled)) % n_folds
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
    models: list[object]
    oof_metrics: dict[str, float]


def run_cv(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    splits: Splits,
    trainer: Trainer,
    *,
    seed: int,
    metric_fn: MetricFn = evaluate,
) -> CVResult:
    """fold ごとに trainer.train を呼び、valid への予測を oof に格納する。

    - fold の種は SeedSequence(seed).spawn(k) から導出（fold 間で独立・再現可能）。
    - valid_idx が重複していたら失敗（同じ行に 2 回書く分割は分割の誤り）。
    - 指標は分類（evaluate＝accuracy・roc_auc）を既定にし、y_true は整数ラベルとして渡す（段階1）。
    """
    n = len(y)
    oof = np.zeros(n, dtype=np.float64)
    oof_mask = np.zeros(n, dtype=np.bool_)
    fold_metrics: list[dict[str, float]] = []
    models: list[object] = []
    fold_seeds = np.random.SeedSequence(seed).spawn(len(splits))
    for (train_idx, valid_idx), fold_seed in zip(splits, fold_seeds, strict=True):
        if oof_mask[valid_idx].any():
            raise ValueError("valid_idx が重複している（同じ行に 2 回予測を書く分割は誤り）")
        outcome = trainer.train(
            x[train_idx], y[train_idx], x[valid_idx], y[valid_idx], seed=int(fold_seed.generate_state(1)[0])
        )
        oof[valid_idx] = outcome.y_pred
        oof_mask[valid_idx] = True
        fold_metrics.append(metric_fn(y[valid_idx].astype(np.int_), outcome.y_pred))
        models.append(outcome.model)
    oof_metrics = metric_fn(y[oof_mask].astype(np.int_), oof[oof_mask])
    return CVResult(oof=oof, oof_mask=oof_mask, fold_metrics=fold_metrics, models=models, oof_metrics=oof_metrics)
