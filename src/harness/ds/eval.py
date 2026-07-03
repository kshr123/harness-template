"""評価ハーネス：指標の算出（scikit-learn）と、設定の閾値による合否判定。

- 指標そのものは業界標準の `sklearn.metrics` を使う（再発明しない）。ここが担うのは
  「案件ごとに閾値で合否を決める」ハーネス固有の接続（指標レジストリ・evaluate の辞書化・passes の合否）だけ。
- 指標は `METRICS` レジストリ（BLOCKS/ENCODERS/MODELS と同型）。指標名は既に config の語彙（thresholds）なので
  カタログの対象（DEC-0009）。回帰指標（小さいほど良い）が入るため、**向き（higher_is_better）は指標の属性**
  として持つ（`passes` はこれで `>=`/`<=` を切り替える）。本体は全部 sklearn 素通し。
- 合否の閾値はコードに埋めず、設定（辞書）で外から与える（案件ごとに決める）。
- `passes` が返す合否は、共通の検証コマンドと同じ「成功/失敗」に接続できる。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_absolute_percentage_error,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    root_mean_squared_error,
)


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


def _pr_auc(y_true: NDArray[np.int_], y_score: NDArray[np.float64]) -> float:
    """PR 曲線下面積（average_precision）。単一クラスは定義できないので方針値（陽性なし 0.0・陽性のみ 1.0）。"""
    uniq = np.unique(y_true)
    if len(uniq) < 2:
        return 1.0 if uniq[0] == 1 else 0.0
    return float(average_precision_score(y_true, y_score))


def _log_loss(y_true: NDArray[np.int_], y_score: NDArray[np.float64]) -> float:
    """対数損失（小さいほど良い）。単一クラスの fold で落ちないよう labels=[0,1] を明示する。"""
    return float(log_loss(y_true, y_score, labels=[0, 1]))


# 以下は sklearn.metrics の薄い包み（再発明しない・zero_division/型を吸収するだけ）。名前で引けるよう関数にする。
def _f1(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(f1_score(y_true, y_pred, zero_division=0.0))


def _precision(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(precision_score(y_true, y_pred, zero_division=0.0))


def _recall(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(recall_score(y_true, y_pred, zero_division=0.0))


def _rmse(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(root_mean_squared_error(y_true, y_pred))


def _mae(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(mean_absolute_error(y_true, y_pred))


def _mape(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(mean_absolute_percentage_error(y_true, y_pred))


MetricInput = Literal["score", "label", "value"]
# fn の第一引数は分類で int・回帰で float。両方を受けるため NDArray[Any]（sklearn 自体が型なし）。
MetricBody = Callable[[NDArray[Any], NDArray[Any]], float]


@dataclass(frozen=True)
class Metric:
    """指標 1 つの登録情報。fn は sklearn.metrics の薄い包み（再発明しない）。

    input：fn に何を渡すか。score=確率・label=閾値後のラベル・value=回帰の予測値。
    higher_is_better：合否判定（passes）の向き。回帰の rmse/log_loss は False（小さいほど良い）。
    description：一覧コマンド（uv run data metrics）に載る 1 行（test_catalog で必須検査）。
    """

    fn: MetricBody
    task: Literal["classification", "regression"]
    input: MetricInput
    higher_is_better: bool
    description: str


# config の thresholds に書ける指標名 → 指標の定義。足したら 1 行（他レジストリと同じ）。本体は全部 sklearn 素通し。
METRICS: dict[str, Metric] = {
    # 分類・確率入力（score）
    "roc_auc": Metric(roc_auc, "classification", "score", True, "ROC 曲線下面積（順位の良さ・0.5=でたらめ）"),
    "pr_auc": Metric(_pr_auc, "classification", "score", True, "PR 曲線下面積（不均衡に強い・陽性の当てやすさ）"),
    "log_loss": Metric(_log_loss, "classification", "score", False, "対数損失（確率の当たり具合・小さいほど良い）"),
    # 分類・ラベル入力（label＝閾値後）
    "accuracy": Metric(accuracy, "classification", "label", True, "正解率（当たった割合）"),
    "f1": Metric(_f1, "classification", "label", True, "F1（適合率と再現率の調和平均）"),
    "precision": Metric(_precision, "classification", "label", True, "適合率（陽性のうち本当に陽性の割合）"),
    "recall": Metric(_recall, "classification", "label", True, "再現率（本当の陽性を取りこぼさない割合）"),
    # 回帰・予測値入力（value）
    "rmse": Metric(_rmse, "regression", "value", False, "二乗平均平方根誤差（小さいほど良い）"),
    "mae": Metric(_mae, "regression", "value", False, "平均絶対誤差（小さいほど良い）"),
    "mape": Metric(_mape, "regression", "value", False, "平均絶対百分率誤差（比率・小さいほど良い）"),
}

MetricFn = Callable[[NDArray[np.int_], NDArray[np.float64]], dict[str, float]]


def _select(task: Literal["classification", "regression"], names: Sequence[str] | None) -> list[str]:
    """名前を検証して task に合う指標名の並びを返す。names 未指定はその task の全登録指標。"""
    if names is None:
        return [n for n, m in METRICS.items() if m.task == task]
    chosen: list[str] = []
    for n in names:
        if n not in METRICS:
            raise ValueError(f"未登録の指標 '{n}'（{sorted(METRICS)} のいずれか）")
        if METRICS[n].task != task:
            other = "回帰" if task == "classification" else "分類"
            raise ValueError(f"指標 '{n}' は{other}用（この評価は {task}）")
        chosen.append(n)
    return chosen


def evaluate(
    y_true: NDArray[np.int_],
    y_score: NDArray[np.float64],
    *,
    threshold: float = 0.5,
    metrics: Sequence[str] | None = None,
) -> dict[str, float]:
    """分類の指標をまとめて返す。既定は分類の全登録指標。label 系は threshold でラベル化してから測る。

    threshold はスコアをラベルに変える決定境界（既定 0.5）。metrics=["roc_auc", ...] で選べる
    （回帰指標の名を渡すと ValueError）。返り値は追加のみで増えることがある（キーの部分集合で参照すること）。
    """
    y_label = (y_score >= threshold).astype("int64")
    out: dict[str, float] = {}
    for name in _select("classification", metrics):
        m = METRICS[name]
        out[name] = m.fn(y_true, y_label if m.input == "label" else y_score)
    return out


def evaluate_regression(
    y_true: NDArray[np.float64], y_pred: NDArray[np.float64], *, metrics: Sequence[str] | None = None
) -> dict[str, float]:
    """回帰の指標をまとめて返す。既定は回帰の全登録指標（rmse/mae/mape）。"""
    return {name: METRICS[name].fn(y_true, y_pred) for name in _select("regression", metrics)}


def metric_fn_for(
    task: Literal["classification", "regression"] = "classification",
    *,
    threshold: float = 0.5,
    metrics: Sequence[str] | None = None,
) -> MetricFn:
    """run_cv / run_experiment の metric_fn に渡す形へ束ねる（task の分岐はここ 1 か所）。

    classification は evaluate（threshold でラベル化）・regression は evaluate_regression を包む。
    どちらも (y_true, 予測) → dict の同じ形で返す（run_cv は中身を知らないまま fold ごとに呼ぶ）。
    """
    if task == "regression":
        return lambda t, p: evaluate_regression(t.astype(np.float64), p, metrics=metrics)
    return lambda t, p: evaluate(t, p, threshold=threshold, metrics=metrics)


def passes(metrics: dict[str, float], thresholds: dict[str, float]) -> bool:
    """設定の閾値をすべて満たすときだけ成功（True）。向きはレジストリで解決する。

    higher_is_better なら `>=`、そうでなければ `<=`（例 log_loss: 0.5 は「0.5 以下で合格」）。
    thresholds に METRICS 未登録の名があれば ValueError（typo を黙って不合格にしない）。
    metrics 側に無い登録済みの名は不合格（測っていない＝満たしたと見なさない）。
    """
    for name, limit in thresholds.items():
        if name not in METRICS:
            raise ValueError(f"未登録の指標 '{name}'（thresholds に書けるのは {sorted(METRICS)}）")
        if name not in metrics:
            return False
        value = metrics[name]
        if METRICS[name].higher_is_better:
            if value < limit:
                return False
        elif value > limit:
            return False
    return True


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
