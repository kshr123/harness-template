"""評価ハーネス：指標の算出（scikit-learn）と、設定の閾値による合否判定。

- 指標そのものは業界標準の `sklearn.metrics` を使う（再発明しない）。ここが担うのは
  「案件ごとに閾値で合否を決める」ハーネス固有の接続（evaluate の辞書化・passes の合否）だけ。
- 合否の閾値はコードに埋めず、設定（辞書）で外から与える（案件ごとに決める）。
- `passes` が返す合否は、共通の検証コマンドと同じ「成功/失敗」に接続できる。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import accuracy_score, roc_auc_score


def accuracy(y_true: NDArray[np.int_], y_pred: NDArray[np.int_]) -> float:
    """正解率（当たった割合）。"""
    return float(accuracy_score(y_true, y_pred))


def roc_auc(y_true: NDArray[np.int_], y_score: NDArray[np.float64]) -> float:
    """AUC（正例の予測スコアが負例より高い確率）。

    正例・負例が片方でも無いと AUC は定義できない。CV の fold で片方だけになっても落ちないよう、
    そのときは 0.5（判断できない）を返す（sklearn は例外を投げるため、ここで揃える）。
    """
    if len(np.unique(y_true)) < 2:
        return 0.5
    return float(roc_auc_score(y_true, y_score))


def evaluate(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, threshold: float = 0.5) -> dict[str, float]:
    """指標をまとめて返す。threshold はスコアをラベルに変える決定境界（既定 0.5・引数で変えられる）。"""
    y_pred = (y_score >= threshold).astype("int64")
    return {"accuracy": accuracy(y_true, y_pred), "roc_auc": roc_auc(y_true, y_score)}


def passes(metrics: dict[str, float], thresholds: dict[str, float]) -> bool:
    """設定の閾値をすべて満たすときだけ成功（True）。閾値に無い指標は判定に使わない。"""
    return all(metrics.get(name, float("-inf")) >= limit for name, limit in thresholds.items())
