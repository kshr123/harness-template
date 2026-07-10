"""評価ハーネス：指標の算出（scikit-learn）と、設定の閾値による合否判定。

- 指標そのものは業界標準の `sklearn.metrics` を使う（再発明しない）。ここが担うのは
  「案件ごとに閾値で合否を決める」ハーネス固有の接続（指標レジストリ・evaluate の辞書化・passes の合否）だけ。
- 指標は `METRICS` レジストリ（BLOCKS/ENCODERS/MODELS と同型）。指標名は既に config の語彙（thresholds）なので
  カタログの対象。回帰指標（小さいほど良い）が入るため、**向き（higher_is_better）は指標の属性**
  として持つ（`passes` はこれで `>=`/`<=` を切り替える）。本体は全部 sklearn 素通し。
- 合否の閾値はコードに埋めず、設定（辞書）で外から与える（案件ごとに決める）。
- `passes` が返す合否は、共通の検証コマンドと同じ「成功/失敗」に接続できる。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from functools import partial
from typing import Any, Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    matthews_corrcoef,
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_pinball_loss,
    precision_recall_curve,
    precision_recall_fscore_support,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    roc_curve,
    root_mean_squared_error,
)

from harness import gates
from harness.registry import MetricEntry, Registry


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


def _brier(y_true: NDArray[Any], y_score: NDArray[Any]) -> float:  # noqa: ANN401
    return float(brier_score_loss(y_true, y_score))


# 以下は sklearn.metrics の薄い包み（再発明しない・zero_division/型を吸収するだけ）。名前で引けるよう関数にする。
def _f1(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(f1_score(y_true, y_pred, zero_division=0.0))


def _precision(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(precision_score(y_true, y_pred, zero_division=0.0))


def _recall(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(recall_score(y_true, y_pred, zero_division=0.0))


# mcc・balanced_accuracy は sklearn がそのまま多クラスも扱う（average 不要）＝二値・多クラス共用（tasks に併記）。
def _mcc(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(matthews_corrcoef(y_true, y_pred))


def _balanced_accuracy(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(balanced_accuracy_score(y_true, y_pred))


def _calibration_gap(y_true: NDArray[Any], y_score: NDArray[Any]) -> float:  # noqa: ANN401
    """較正のずれの診断 |1 - mean(score)/mean(true)|。0 が最良（小さいほど良い）。

    「1 に近いほど良い」比のままだと passes の大小比較（向き属性）に乗らないため、絶対値のずれで返す。
    mean(true)=0（正例なし）は比が定義できないので nan（passes は NaN を不合格にする＝fail closed）。
    """
    mean_true = float(np.asarray(y_true, dtype=np.float64).mean())
    if mean_true == 0.0:
        return float("nan")
    return abs(1.0 - float(np.asarray(y_score, dtype=np.float64).mean()) / mean_true)


# 多クラス分類の包み（average="macro"・multi_class="ovr" を sklearn へ素通し。手書きしない）。
# labels は proba の列数から明示する（fold にクラスが欠けても sklearn が黙って列対応をずらさない）。
# ラベルは 0..n_classes-1 が前提（proba の列順と一致。cv._predict の多クラス出力・evaluate_multiclass と同じ契約）。
def _macro_f1(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(f1_score(y_true, y_pred, average="macro", zero_division=0.0))


def _macro_precision(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(precision_score(y_true, y_pred, average="macro", zero_division=0.0))


def _macro_recall(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(recall_score(y_true, y_pred, average="macro", zero_division=0.0))


def _log_loss_multi(y_true: NDArray[Any], y_proba: NDArray[Any]) -> float:  # noqa: ANN401
    return float(log_loss(y_true, y_proba, labels=np.arange(y_proba.shape[1])))


def _macro_roc_auc(y_true: NDArray[Any], y_proba: NDArray[Any]) -> float:  # noqa: ANN401
    return float(roc_auc_score(y_true, y_proba, multi_class="ovr", average="macro", labels=np.arange(y_proba.shape[1])))


def _rmse(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(root_mean_squared_error(y_true, y_pred))


def _mae(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(mean_absolute_error(y_true, y_pred))


def _mape(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(mean_absolute_percentage_error(y_true, y_pred))


def _r2(y_true: NDArray[Any], y_pred: NDArray[Any]) -> float:  # noqa: ANN401
    return float(r2_score(y_true, y_pred))


def pinball(y_true: NDArray[Any], y_pred: NDArray[Any], *, alpha: float = 0.5) -> float:  # noqa: ANN401
    """ピンボール損失（分位 α の非対称誤差・小さいほど良い）。mean_pinball_loss 素通し。

    α は狙う分位（0 < α < 1）：loss = α·max(y−pred, 0) + (1−α)·max(pred−y, 0)。過小予測に α・
    過大予測に 1−α の重み（α=0.9 は上側分位＝過小予測に重い罰）。α=0.5 は |誤差|/2＝mae/2（中央値の点予測）。
    代表分位は METRICS に登録済み（pinball=α0.5・pinball_q10・pinball_q90）。その他の α はこの関数を直接呼ぶ。
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha は 0 より大きく 1 未満（分位。指定値: {alpha}）")
    return float(mean_pinball_loss(y_true, y_pred, alpha=alpha))


# config の thresholds に書ける指標名 → 指標の定義（MetricEntry：input・向き・対応 task つき）。足したら 1 行。
# description は説明用の日本語（工場の docstring より一覧向きの短文）なので明示で渡す。本体は全部 sklearn 素通し。
# tasks は「測れる課題」の並び（語彙は binary | multiclass | regression。省略時は task から導く＝分類は二値）。
METRICS: Registry[MetricEntry] = Registry("指標", catalog="data metrics")


def _register_metric(
    name: str,
    fn: Callable[[NDArray[Any], NDArray[Any]], float],
    task: Literal["classification", "regression"],
    input_: Literal["score", "label", "value"],
    higher_is_better: bool,
    description: str,
    *,
    tasks: tuple[str, ...] | None = None,
) -> None:
    if tasks is None:
        tasks = ("binary",) if task == "classification" else ("regression",)
    METRICS.register(
        name,
        fn,
        description=description,
        task=task,
        entry_cls=MetricEntry,
        input=input_,
        higher_is_better=higher_is_better,
        tasks=tasks,
    )


# 分類・確率入力（score）
_register_metric("roc_auc", roc_auc, "classification", "score", True, "ROC 曲線下面積（順位の良さ・0.5=でたらめ）")
_register_metric("pr_auc", _pr_auc, "classification", "score", True, "PR 曲線下面積（不均衡に強い・陽性の当てやすさ）")
_register_metric(
    "log_loss", _log_loss, "classification", "score", False, "対数損失（確率の当たり具合・小さいほど良い）"
)
_register_metric(
    "brier",
    _brier,
    "classification",
    "score",
    False,
    "ブライアスコア（確率のずれの二乗平均・0 が最良・小さいほど良い）",
)
_register_metric(
    "calibration_gap",
    _calibration_gap,
    "classification",
    "score",
    False,
    "較正のずれ（|1-平均予測/平均実測|・0 が最良。reliability の calibration_table とは別＝平均レベルのみ）",
)
# 分類・ラベル入力（label＝閾値後）。accuracy は多クラスでもそのまま測れる（tasks に multiclass を併記）。
_register_metric(
    "accuracy", accuracy, "classification", "label", True, "正解率（当たった割合）", tasks=("binary", "multiclass")
)
_register_metric("f1", _f1, "classification", "label", True, "F1（適合率と再現率の調和平均）")
_register_metric("precision", _precision, "classification", "label", True, "適合率（陽性のうち本当に陽性の割合）")
_register_metric("recall", _recall, "classification", "label", True, "再現率（本当の陽性を取りこぼさない割合）")
_register_metric(
    "mcc",
    _mcc,
    "classification",
    "label",
    True,
    "マシューズ相関（-1〜1・不均衡に強い）",
    tasks=("binary", "multiclass"),
)
_register_metric(
    "balanced_accuracy",
    _balanced_accuracy,
    "classification",
    "label",
    True,
    "均衡正解率（クラス毎 recall の平均）",
    tasks=("binary", "multiclass"),
)
# 分類・多クラス（tasks=("multiclass",)。名前は二値名と衝突させない＝macro_ 接頭辞・_multi 接尾辞）
_register_metric(
    "macro_roc_auc",
    _macro_roc_auc,
    "classification",
    "score",
    True,
    "多クラス AUC（各クラス ovr の macro 平均）",
    tasks=("multiclass",),
)
_register_metric(
    "log_loss_multi",
    _log_loss_multi,
    "classification",
    "score",
    False,
    "多クラス対数損失（確率の当たり具合・小さいほど良い）",
    tasks=("multiclass",),
)
_register_metric(
    "macro_f1",
    _macro_f1,
    "classification",
    "label",
    True,
    "多クラス F1（クラス別 F1 の macro 平均）",
    tasks=("multiclass",),
)
_register_metric(
    "macro_precision",
    _macro_precision,
    "classification",
    "label",
    True,
    "多クラス適合率（クラス別適合率の macro 平均）",
    tasks=("multiclass",),
)
_register_metric(
    "macro_recall",
    _macro_recall,
    "classification",
    "label",
    True,
    "多クラス再現率（クラス別再現率の macro 平均）",
    tasks=("multiclass",),
)
# 回帰・予測値入力（value）
_register_metric("rmse", _rmse, "regression", "value", False, "二乗平均平方根誤差（小さいほど良い）")
_register_metric("mae", _mae, "regression", "value", False, "平均絶対誤差（小さいほど良い）")
_register_metric("mape", _mape, "regression", "value", False, "平均絶対百分率誤差（比率・小さいほど良い）")
_register_metric("r2", _r2, "regression", "value", True, "決定係数（1 で完全・0 で平均予測並み）")
_register_metric(
    "pinball",
    pinball,
    "regression",
    "value",
    False,
    "ピンボール損失 α=0.5（点予測では mae/2＝中央値。他の分位は pinball_q10/q90 か pinball(alpha=) を直接）",
)
_register_metric(
    "pinball_q10",
    partial(pinball, alpha=0.1),
    "regression",
    "value",
    False,
    "ピンボール損失 α=0.1（下側 10% 分位・過大予測に重い罰・小さいほど良い）",
)
_register_metric(
    "pinball_q90",
    partial(pinball, alpha=0.9),
    "regression",
    "value",
    False,
    "ピンボール損失 α=0.9（上側 90% 分位・過小予測に重い罰・小さいほど良い）",
)

MetricFn = Callable[[NDArray[np.int_], NDArray[np.float64]], dict[str, float]]

# 課題の語彙（binary | multiclass | regression）。指標側は MetricEntry.tasks（測れる課題の並び）で表す。
EvalTask = Literal["binary", "multiclass", "regression"]
_TASK_JA: dict[str, str] = {"binary": "二値分類", "multiclass": "多クラス分類", "regression": "回帰"}


def _select(task: EvalTask, names: Sequence[str] | None) -> list[str]:
    """名前を検証して task で測れる指標名の並びを返す。names 未指定はその task の全登録指標（tasks 照合）。"""
    if names is None:
        return [n for n, m in METRICS.items() if task in m.tasks]
    chosen: list[str] = []
    for n in names:
        if n not in METRICS:
            raise ValueError(f"未登録の指標 '{n}'（{sorted(METRICS)} のいずれか）")
        if task not in METRICS[n].tasks:
            usable = "/".join(_TASK_JA.get(t, t) for t in METRICS[n].tasks)
            raise ValueError(f"指標 '{n}' は{usable}用（この評価は {task}）")
        chosen.append(n)
    return chosen


def evaluate(
    y_true: NDArray[np.int_],
    y_score: NDArray[np.float64],
    *,
    threshold: float = 0.5,
    metrics: Sequence[str] | None = None,
) -> dict[str, float]:
    """二値分類の指標をまとめて返す。既定は二値の全登録指標。label 系は threshold でラベル化してから測る。

    threshold はスコアをラベルに変える決定境界（既定 0.5）。metrics=["roc_auc", ...] で選べる
    （二値で測れない指標の名を渡すと ValueError）。返り値は追加のみで増えることがある（キーの部分集合で参照すること）。
    y_true は分類ラベルとして int に揃える（run_cv が float の器で渡してきても安全に）。多クラスは evaluate_multiclass。
    """
    y_int = np.asarray(y_true).astype(np.int_)
    y_label = (y_score >= threshold).astype("int64")
    out: dict[str, float] = {}
    for name in _select("binary", metrics):
        m = METRICS[name]
        out[name] = m.fn(y_int, y_label if m.input == "label" else y_score)
    return out


def evaluate_multiclass(
    y_true: NDArray[np.int_],
    y_proba: NDArray[np.float64],
    *,
    metrics: Sequence[str] | None = None,
) -> dict[str, float]:
    """多クラス分類の指標をまとめて返す。既定は multiclass の全登録指標（accuracy・macro 平均系・log_loss_multi）。

    y_proba は (n, n_classes) の確率（cv._predict(how="proba") の多クラス出力と同じ形）。label 系は argmax で
    ラベル化してから測る（二値の threshold 経路はここでは使わない）。ラベルは 0..n_classes-1 が前提
    （proba の列順と対応。二値の「陽性=ラベル 1」前提と同じく、外れるラベルは呼び手で振り直す）。
    """
    proba = np.asarray(y_proba, dtype=np.float64)
    if proba.ndim != 2 or proba.shape[1] < 3:
        # 2 クラスは二値経路（evaluate）へ。多クラス指標（macro_roc_auc 等）は 2 列だと不透明に落ちるので明示で止める。
        raise ValueError(
            f"多クラスの y_proba は (n, n_classes>=3) の 2 次元（実際の形: {proba.shape}）。2 クラスは evaluate を使う"
        )
    y_int = np.asarray(y_true).astype(np.int_)
    y_label = proba.argmax(axis=1).astype("int64")
    out: dict[str, float] = {}
    for name in _select("multiclass", metrics):
        m = METRICS[name]
        out[name] = m.fn(y_int, y_label if m.input == "label" else proba)
    return out


def evaluate_regression(
    y_true: NDArray[np.float64], y_pred: NDArray[np.float64], *, metrics: Sequence[str] | None = None
) -> dict[str, float]:
    """回帰の指標をまとめて返す。既定は回帰の全登録指標（rmse/mae/mape）。"""
    return {name: METRICS[name].fn(y_true, y_pred) for name in _select("regression", metrics)}


def metric_fn_for(
    task: Literal["classification", "multiclass", "regression"] = "classification",
    *,
    threshold: float = 0.5,
    metrics: Sequence[str] | None = None,
) -> MetricFn:
    """run_cv / run_experiment の metric_fn に渡す形へ束ねる（task の分岐はここ 1 か所）。

    classification（二値）は evaluate（threshold でラベル化）・multiclass は evaluate_multiclass
    （予測は (n, n_classes) の proba・threshold は使わない）・regression は evaluate_regression を包む。
    いずれも (y_true, 予測) → dict の同じ形で返す（run_cv は中身を知らないまま fold ごとに呼ぶ）。
    """
    if task == "regression":
        return lambda t, p: evaluate_regression(t.astype(np.float64), p, metrics=metrics)
    if task == "multiclass":
        return lambda t, p: evaluate_multiclass(t, p, metrics=metrics)
    return lambda t, p: evaluate(t, p, threshold=threshold, metrics=metrics)


def passes(metrics: dict[str, float], thresholds: dict[str, float]) -> bool:
    """設定の閾値をすべて満たすときだけ成功（True）。向きはレジストリで解決する。

    higher_is_better なら `>=`、そうでなければ `<=`（例 log_loss: 0.5 は「0.5 以下で合格」）。
    thresholds に METRICS 未登録の名があれば ValueError（typo を黙って不合格にしない）。
    metrics 側に無い登録済みの名は不合格（測っていない＝満たしたと見なさない）。
    値が NaN のときも不合格（fail closed。発散したモデルを昇格させない）。

    判定そのものは中核の `harness.gates.value_threshold` が持つ（agent プロファイルの `passes` と同じ実体）。
    ここが持つのは「どのレジストリで向きを解決するか」だけ。
    """
    ctx = gates.GateContext(candidate=metrics, baseline=None, directions=directions(thresholds))
    return gates.evaluate(ctx, gates.value_threshold_specs(thresholds)).approved


def directions(names: Iterable[str]) -> dict[str, bool]:
    """指標名 → 向き（大きいほど良いか）。未登録の名があれば ValueError（typo を黙って不合格にしない）。

    向きの正本は METRICS。昇格の判定（`harness.gates`）は解決済みの向きだけを受け取るので、
    「どのレジストリで解決するか」を決めるのはこの関数の役目。
    """
    resolved: dict[str, bool] = {}
    for name in names:
        if name not in METRICS:
            raise ValueError(f"未登録の指標 '{name}'（thresholds に書けるのは {sorted(METRICS)}）")
        resolved[name] = METRICS[name].higher_is_better
    return resolved


def bootstrap_ci(
    y_true: NDArray[Any],  # noqa: ANN401
    y_pred: NDArray[Any],  # noqa: ANN401
    *,
    metric: str,
    n_boot: int = 1000,
    seed: int,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """指標のブートストラップ信頼区間（百分位法）。返り値は (lo, hi)＝百分位 (alpha/2, 1−alpha/2)。

    行を rng.choice で n_boot 回再標本し、指標の計算は METRICS[metric] に委譲する（再発明しない）。
    leaderboard の変種差が「ノイズか本物か」の目安に使う（OOF 予測で呼ぶ・区間が重ならなければ本物の差とみなしやすい）。
    y_pred は指標の input に合わせて渡す（score=確率・label=閾値後ラベル・value=回帰の予測値。
    一覧は `uv run data metrics`）。seed は明示必須・同じ seed なら同じ区間（決定的）。
    例：lo, hi = bootstrap_ci(y, oof_score, metric="roc_auc", seed=0)
    """
    entry = METRICS.resolve(metric)  # 未知の指標名はここで ValueError（候補一覧つき）
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha は 0 より大きく 1 未満（両側の外れ確率。指定値: {alpha}）")
    if n_boot < 1:
        raise ValueError(f"n_boot は 1 以上（指定値: {n_boot}）")
    y = np.asarray(y_true)
    pred = np.asarray(y_pred)
    if y.shape[0] == 0 or y.shape[0] != pred.shape[0]:
        raise ValueError(f"y_true と y_pred は同じ長さで空でないこと（実際: {y.shape[0]} 行と {pred.shape[0]} 行）")
    rng = np.random.default_rng(seed)
    n = y.shape[0]
    stats = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        idx = rng.choice(n, size=n, replace=True)
        stats[b] = entry.fn(y[idx], pred[idx])
    lo, hi = np.quantile(stats, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(lo), float(hi)


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


def select_threshold_min_cost(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, fp_cost: float, fn_cost: float
) -> tuple[float, float]:
    """期待費用 fp×fp_cost + fn×fn_cost を最小にする閾値。返り値は (閾値, 最小費用)。同点は大きい方の閾値。

    誤検知（fp）と見逃し（fn）の費用が非対称なときの閾値選択。候補は select_threshold_* 兄弟と同じ
    スコアの一意な値（_curve）に「全部陰性」（max(y_score) の直上）を加えたもの。数えは threshold_table
    の累積カウントに相乗り（confusion と同値・O(n log n)）。較正済みスコアなら最適閾値は
    fp_cost/(fp_cost+fn_cost) の近傍に出る。※選ぶのは valid/OOF で（train は過大評価・test は漏れ）。
    """
    if fp_cost <= 0 or fn_cost <= 0:
        raise ValueError(f"fp_cost・fn_cost は正の費用（指定値: fp_cost={fp_cost}, fn_cost={fn_cost}）")
    candidates = [float(t) for t in _curve(y_true, y_score)[2]]
    candidates.append(float(np.nextafter(np.max(y_score), np.inf)))  # 全部陰性（fp=0）も候補に含める
    tbl = threshold_table(y_true, y_score, thresholds=candidates)
    cost = tbl["fp"].to_numpy() * fp_cost + tbl["fn"].to_numpy() * fn_cost
    best = float(cost.min())
    idx = int(np.flatnonzero(cost == best).max())  # 候補は昇順→最大添字＝大きい方の閾値（max_f1 と同じ規約）
    return float(tbl["threshold"][idx]), best


def confusion(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, threshold: float = 0.5) -> dict[str, int]:
    """混同行列の要約 {tn, fp, fn, tp}。confusion_matrix(labels=[0,1]) の dict 化のみ（単一クラスでも 4 キー揃う）。

    率（tpr 等）は evaluate/class_metrics が持つ＝二重に返さない。OOF/valid の予測で呼ぶこと。
    """
    y_pred = (y_score >= threshold).astype("int64")
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}


def class_metrics(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, threshold: float = 0.5) -> pl.DataFrame:
    """クラス別指標（classification_report の機械可読版）。列 = class, count, precision, recall, f1。

    precision_recall_fscore_support(labels=[0,1], zero_division=0) 素通し。文字列レポートは作らない（表が正本）。
    evaluate との違い：evaluate は陽性クラスの値だけ・こちらは両クラス。
    """
    y_pred = (y_score >= threshold).astype("int64")
    precision, recall, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=[0, 1], zero_division=0.0)
    rows = [
        {
            "class": k,
            "count": int(support[k]),
            "precision": float(precision[k]),
            "recall": float(recall[k]),
            "f1": float(f1[k]),
        }
        for k in (0, 1)
    ]
    return pl.DataFrame(rows)


def calibration_table(
    y_true: NDArray[np.int_],
    y_score: NDArray[np.float64],
    *,
    bins: int = 10,
    strategy: Literal["uniform", "quantile"] = "uniform",
) -> pl.DataFrame:
    """確率の較正（reliability）の表。列 = bin, mean_predicted, fraction_positive, count（空ビンは出さない）。

    calibration_curve と同じビン分けに件数を足したもの（件数が無いとビンの信頼度を読めない）。
    mean_predicted ≒ fraction_positive なら較正されている。strategy="quantile" はスコア分位で切る＝デシル表を兼ねる。
    """
    if strategy == "quantile":
        edges = np.unique(np.quantile(y_score, np.linspace(0.0, 1.0, bins + 1)))
    else:
        edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.searchsorted(edges, y_score, side="right") - 1, 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        mask = idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        rows.append(
            {
                "bin": b,
                "mean_predicted": float(y_score[mask].mean()),
                "fraction_positive": float(y_true[mask].mean()),
                "count": count,
            }
        )
    schema: dict[str, Any] = {
        "bin": pl.Int64,
        "mean_predicted": pl.Float64,
        "fraction_positive": pl.Float64,
        "count": pl.Int64,
    }
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def roc_table(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, max_points: int | None = None) -> pl.DataFrame:
    """ROC 曲線の表。列 = fpr, tpr, threshold。roc_curve 素通し（人は marimo で見る・AUC＝roc_auc の下地）。

    threshold は sklearn のまま降順（先頭は番兵の inf）。両クラス必須（_curve と同じ・OOF/valid 全体で呼ぶこと）。
    max_points 指定時は等間隔の添字で間引く（先頭・末尾の点は必ず残す）。省略時は全点。max_points は 2 以上
    （両端点を残す約束のため。1 以下は端点を落とすので拒否する）。
    """
    if len(np.unique(y_true)) < 2:
        raise ValueError("ROC 曲線には正例・負例の両方が要る（OOF/valid 全体で呼ぶこと）")
    if max_points is not None and max_points < 2:
        raise ValueError(f"max_points は 2 以上（先頭・末尾の点を残すため。指定値: {max_points}）")
    fpr, tpr, thresholds = roc_curve(y_true, y_score)
    if max_points is not None and len(fpr) > max_points:
        keep = np.unique(np.round(np.linspace(0, len(fpr) - 1, max_points)).astype(int))
        fpr, tpr, thresholds = fpr[keep], tpr[keep], thresholds[keep]
    return pl.DataFrame(
        {
            "fpr": np.asarray(fpr, dtype=np.float64),
            "tpr": np.asarray(tpr, dtype=np.float64),
            "threshold": np.asarray(thresholds, dtype=np.float64),
        }
    )


def threshold_table(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, thresholds: Sequence[float] | None = None
) -> pl.DataFrame:
    """閾値スイープ表。列 = threshold, precision, recall, f1, tp, fp, fn, tn。

    省略時の閾値は _curve（precision_recall_curve）のもの＝select_threshold_* と同じ土台（前後を見比べる用）。
    tp/fp/fn/tn はスコア昇順の累積和から一括算出（閾値ごとに confusion_matrix を回さない＝O(n log n)）。
    数えは confusion（labels=[0,1]・pred = score >= t）と同値。閾値の「選択」は select_threshold_* が持つ。
    """
    ts = list(thresholds) if thresholds is not None else [float(t) for t in _curve(y_true, y_score)[2]]
    if not ts:
        return pl.DataFrame([])  # 空指定は従来どおり空表（列なし）
    y = np.asarray(y_true)
    scores = np.asarray(y_score, dtype=np.float64)
    order = np.argsort(scores)
    s_sorted = scores[order]
    # 先頭 0 番兵つき累積和：cum_pos[i]/cum_neg[i] = スコア昇順で先頭 i 件中の正例/負例数（0/1 以外は数えない）。
    cum_pos = np.concatenate(([0], np.cumsum(y[order] == 1)))
    cum_neg = np.concatenate(([0], np.cumsum(y[order] == 0)))
    ts_arr = np.asarray(ts, dtype=np.float64)
    below = np.searchsorted(s_sorted, ts_arr, side="left")  # score < t の件数（>= t が陽性＝confusion と同じ境界）
    fn = cum_pos[below]  # score < t の正例＝見逃し
    tn = cum_neg[below]
    tp = cum_pos[-1] - fn
    fp = cum_neg[-1] - tn
    pred_pos = tp + fp
    precision = np.where(pred_pos > 0, tp / np.where(pred_pos > 0, pred_pos, 1), 0.0)
    actual_pos = tp + fn
    recall = np.where(actual_pos > 0, tp / np.where(actual_pos > 0, actual_pos, 1), 0.0)
    denom = precision + recall
    f1 = np.where(denom > 0, 2 * precision * recall / np.where(denom > 0, denom, 1.0), 0.0)
    return pl.DataFrame(
        {
            "threshold": ts_arr,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tn": tn.astype(np.int64),
            "fp": fp.astype(np.int64),
            "fn": fn.astype(np.int64),
            "tp": tp.astype(np.int64),
        }
    )
