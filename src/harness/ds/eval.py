"""評価ハーネス：指標の算出（scikit-learn）と、設定の閾値による合否判定。

- 指標そのものは業界標準の `sklearn.metrics` を使う（再発明しない）。ここが担うのは
  「案件ごとに閾値で合否を決める」ハーネス固有の接続（evaluate の辞書化・passes の合否）だけ。
- 合否の閾値はコードに埋めず、設定（辞書）で外から与える（案件ごとに決める）。
- `passes` が返す合否は、共通の検証コマンドと同じ「成功/失敗」に接続できる。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import accuracy_score, precision_recall_curve, roc_auc_score


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


def _curve(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """precision_recall_curve の閾値付き部分（末尾の閾値なし点を除いた P・R・閾値）。両クラス必須。"""
    if len(np.unique(y_true)) < 2:
        raise ValueError("閾値選択には正例・負例の両方が要る（OOF/valid 全体で呼ぶこと）")
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    return (
        np.asarray(precision[:-1], dtype=np.float64),
        np.asarray(recall[:-1], dtype=np.float64),
        np.asarray(thresholds, dtype=np.float64),
    )


def select_threshold_max_f1(y_true: NDArray[np.int_], y_score: NDArray[np.float64]) -> tuple[float, float]:
    """F1 を最大にする閾値を y_score の一意な値から選ぶ。返り値は (閾値, そのときの F1)。同点は大きい方の閾値。

    ※閾値は valid か OOF の予測で選ぶこと。train で選ぶと過大評価、test で選ぶと漏れ。
    返した閾値はそのまま evaluate(y_true, y_score, threshold=...) に渡せる（どちらも >= 判定）。
    """
    precision, recall, thresholds = _curve(y_true, y_score)
    denom = precision + recall
    f1 = np.where(denom > 0, 2 * precision * recall / np.where(denom > 0, denom, 1.0), 0.0)
    best = float(f1.max())
    idx = int(np.flatnonzero(f1 == best).max())  # thresholds は昇順→最大添字＝大きい方の閾値
    return float(thresholds[idx]), best


def select_threshold_at_recall(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, target: float) -> float:
    """再現率 >= target を満たす最大の閾値（見逃し上限を決めてから、できるだけ誤検知を減らす）。

    満たす閾値が無ければ min(y_score)（全部陽性）。target は (0, 1]。※選ぶのは valid/OOF で。
    """
    if not 0.0 < target <= 1.0:
        raise ValueError("target は 0 より大きく 1 以下")
    _, recall, thresholds = _curve(y_true, y_score)
    ok = np.flatnonzero(recall >= target)
    if ok.size == 0:
        return float(np.min(y_score))
    return float(thresholds[int(ok.max())])


def select_threshold_at_precision(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, target: float) -> float:
    """適合率 >= target を満たす最小の閾値（誤検知上限を決めてから、できるだけ見逃しを減らす）。

    満たす閾値が無ければ max(y_score) の直上（全部陰性）。target は (0, 1]。※選ぶのは valid/OOF で。
    """
    if not 0.0 < target <= 1.0:
        raise ValueError("target は 0 より大きく 1 以下")
    precision, _, thresholds = _curve(y_true, y_score)
    ok = np.flatnonzero(precision >= target)
    if ok.size == 0:
        return float(np.nextafter(np.max(y_score), np.inf))
    return float(thresholds[int(ok.min())])
