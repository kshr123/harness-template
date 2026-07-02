"""評価ハーネス：指標の算出と、設定の閾値による合否判定。

- 合否の閾値はコードに埋め込まず、設定（辞書）で外から与える（案件ごとに決める）。
- `passes` が返す合否は、共通の検証コマンドと同じ「成功/失敗」に接続できる
  （例：評価スクリプトが passes を見て終了コードを返す）。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def accuracy(y_true: NDArray[np.int_], y_pred: NDArray[np.int_]) -> float:
    """正解率（当たった割合）。"""
    return float(np.mean(y_true == y_pred))


def roc_auc(y_true: NDArray[np.int_], y_score: NDArray[np.float64]) -> float:
    """AUC を順位から計算する（正例の予測スコアが負例より高い確率）。

    正例・負例が片方でも無いときは 0.5（判断できない）を返す。
    """
    order = np.argsort(y_score, kind="mergesort")
    ranks = np.empty(len(y_score), dtype="float64")
    ranks[order] = np.arange(1, len(y_score) + 1)
    # 同点は平均順位にする（同点があっても偏らないように）。
    _, inverse, counts = np.unique(y_score, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts), dtype="float64")
    np.add.at(sums, inverse, ranks)
    ranks = (sums / counts)[inverse]

    pos = y_true == 1
    n_pos = int(pos.sum())
    n_neg = int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    sum_pos = float(ranks[pos].sum())
    return (sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def evaluate(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, threshold: float = 0.5) -> dict[str, float]:
    """指標をまとめて返す。threshold はスコアをラベルに変える決定境界（既定 0.5・引数で変えられる）。"""
    y_pred = (y_score >= threshold).astype("int64")
    return {"accuracy": accuracy(y_true, y_pred), "roc_auc": roc_auc(y_true, y_score)}


def passes(metrics: dict[str, float], thresholds: dict[str, float]) -> bool:
    """設定の閾値をすべて満たすときだけ成功（True）。閾値に無い指標は判定に使わない。"""
    return all(metrics.get(name, float("-inf")) >= limit for name, limit in thresholds.items())
