"""評価ハーネスのテスト：指標の算出と、設定の閾値による合否判定。"""

from __future__ import annotations

import numpy as np
import pytest

from harness.ds import eval as ev

pytestmark = pytest.mark.unit


def test_perfect_predictions_score_top() -> None:
    y_true = np.array([0, 0, 1, 1], dtype="int64")
    y_score = np.array([0.1, 0.2, 0.8, 0.9], dtype="float64")
    metrics = ev.evaluate(y_true, y_score)
    assert metrics["accuracy"] == 1.0
    assert metrics["roc_auc"] == 1.0


def test_reversed_predictions_score_bottom() -> None:
    y_true = np.array([0, 0, 1, 1], dtype="int64")
    y_score = np.array([0.9, 0.8, 0.2, 0.1], dtype="float64")
    assert ev.evaluate(y_true, y_score)["roc_auc"] == 0.0


def test_auc_is_half_without_both_classes() -> None:
    y_true = np.array([1, 1, 1], dtype="int64")
    y_score = np.array([0.2, 0.5, 0.9], dtype="float64")
    assert ev.roc_auc(y_true, y_score) == 0.5


def test_select_threshold_max_f1_exact() -> None:
    # y=[0,0,1,1], s=[.1,.4,.6,.9]。閾値 0.6 で pred=[0,0,1,1]＝P=R=1・F1=1.0（構成から厳密）。
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    threshold, f1 = ev.select_threshold_max_f1(y, s)
    assert threshold == 0.6
    assert f1 == 1.0


def test_select_threshold_max_f1_ties_prefer_larger() -> None:
    # y=[1,0,0,1], s=[.9,.7,.5,.2]。F1 最大 2/3 が閾値 0.2 と 0.9 で同点 → 大きい方 0.9 を返す。
    y = np.array([1, 0, 0, 1], dtype="int64")
    s = np.array([0.9, 0.7, 0.5, 0.2], dtype="float64")
    threshold, f1 = ev.select_threshold_max_f1(y, s)
    assert threshold == 0.9
    assert f1 == pytest.approx(2 / 3)


def test_select_threshold_at_recall() -> None:
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    assert ev.select_threshold_at_recall(y, s, target=1.0) == 0.6  # 両正例を拾う最大の閾値
    assert ev.select_threshold_at_recall(y, s, target=0.5) == 0.9  # 再現率 0.5 を満たす最大


def test_select_threshold_at_precision() -> None:
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    assert ev.select_threshold_at_precision(y, s, target=1.0) == 0.6  # 適合率 1 を満たす最小の閾値


def test_select_threshold_at_precision_unreachable() -> None:
    # どの閾値でも適合率 1 に届かない → max(y_score) より上（全部陰性）を返す。
    y = np.array([1, 0], dtype="int64")
    s = np.array([0.3, 0.8], dtype="float64")
    assert ev.select_threshold_at_precision(y, s, target=1.0) > 0.8


def test_select_threshold_single_class_is_error() -> None:
    with pytest.raises(ValueError, match="両方"):
        ev.select_threshold_max_f1(np.array([1, 1, 1], dtype="int64"), np.array([0.2, 0.5, 0.9], dtype="float64"))


def test_passes_requires_all_thresholds() -> None:
    metrics = {"accuracy": 0.8, "roc_auc": 0.85}
    # すべての閾値を満たす → 成功。
    assert ev.passes(metrics, {"accuracy": 0.75, "roc_auc": 0.8})
    # ひとつでも下回る → 失敗。
    assert not ev.passes(metrics, {"accuracy": 0.9})
    # 閾値に無い指標は判定に使わない（空の閾値は常に成功）。
    assert ev.passes(metrics, {})


def test_metrics_registry_covers_classification_and_regression() -> None:
    # 分類・回帰の両タスクが登録され、向きが指標の属性として持たれる。
    assert ev.METRICS["roc_auc"].higher_is_better is True
    assert ev.METRICS["log_loss"].higher_is_better is False  # 小さいほど良い
    assert ev.METRICS["rmse"].task == "regression"
    assert ev.METRICS["accuracy"].input == "label"  # 閾値後のラベルで測る
    assert ev.METRICS["roc_auc"].input == "score"  # 確率で測る


def test_evaluate_returns_all_classification_metrics() -> None:
    y_true = np.array([0, 0, 1, 1], dtype="int64")
    y_score = np.array([0.1, 0.2, 0.8, 0.9], dtype="float64")
    metrics = ev.evaluate(y_true, y_score)
    # 完全予測：確率系も閾値後のラベル系もすべて満点（構成から導出）。
    for name in ("accuracy", "roc_auc", "pr_auc", "f1", "precision", "recall"):
        assert metrics[name] == 1.0, name
    assert metrics["log_loss"] >= 0.0  # 小さいほど良い（0 以上）
    # metrics= で選べる（回帰指標名を渡すと拒否）。
    assert set(ev.evaluate(y_true, y_score, metrics=["roc_auc"])) == {"roc_auc"}
    with pytest.raises(ValueError, match="回帰|分類"):
        ev.evaluate(y_true, y_score, metrics=["rmse"])


def test_evaluate_regression_values_from_construction() -> None:
    # y_true=[0,0], y_pred=[3,4] → mae=(3+4)/2=3.5・rmse=√((9+16)/2)=√12.5（電卓で導ける）。
    y_true = np.array([0.0, 0.0], dtype="float64")
    y_pred = np.array([3.0, 4.0], dtype="float64")
    m = ev.evaluate_regression(y_true, y_pred)
    assert m["mae"] == pytest.approx(3.5)
    assert m["rmse"] == pytest.approx(np.sqrt(12.5))


def test_passes_respects_direction_and_rejects_unknown() -> None:
    # log_loss は小さいほど良い：0.4 は閾値 0.5 で合格・0.6 は不合格。
    assert ev.passes({"log_loss": 0.4}, {"log_loss": 0.5})
    assert not ev.passes({"log_loss": 0.6}, {"log_loss": 0.5})
    # roc_auc は大きいほど良い（従来どおり）。
    assert ev.passes({"roc_auc": 0.85}, {"roc_auc": 0.8})
    # 未登録の指標名は typo を黙って不合格にせず ValueError。
    with pytest.raises(ValueError, match="未登録|未知"):
        ev.passes({"roc_auc": 0.85}, {"nope": 0.5})


def test_evaluate_single_class_edges_absorbed() -> None:
    # 単一クラス（y 全 0）でも log_loss は落ちない・pr_auc は方針値 0.0（docstring と一致）。
    y_true = np.array([0, 0, 0], dtype="int64")
    y_score = np.array([0.2, 0.5, 0.9], dtype="float64")
    m = ev.evaluate(y_true, y_score)
    assert np.isfinite(m["log_loss"])
    assert m["pr_auc"] == 0.0


def test_confusion_from_construction() -> None:
    # y=[0,0,1,1], score=[0.9,0.1,0.8,0.2], 閾値 0.5 → pred=[1,0,1,0] → tn=fp=fn=tp==1。
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.9, 0.1, 0.8, 0.2], dtype="float64")
    assert ev.confusion(y, s) == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}


def test_class_metrics_both_classes() -> None:
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.9, 0.1, 0.8, 0.2], dtype="float64")  # pred=[1,0,1,0]
    rows = {r["class"]: r for r in ev.class_metrics(y, s).to_dicts()}
    assert set(rows) == {0, 1}  # 両クラスが出る
    assert rows[0]["precision"] == pytest.approx(0.5)  # pred=0 は 2 件・うち正しく 0 は 1 件
    assert rows[1]["recall"] == pytest.approx(0.5)  # 実際の 1 は 2 件・拾えたのは 1 件
    assert rows[0]["count"] == 2  # support


def test_calibration_table_single_bin() -> None:
    # score 全行 0.3・y は 4 行中 1 正例 → 1 ビン：count 4・fraction 0.25・mean_predicted 0.3。
    y = np.array([1, 0, 0, 0], dtype="int64")
    s = np.array([0.3, 0.3, 0.3, 0.3], dtype="float64")
    tbl = ev.calibration_table(y, s).to_dicts()
    assert len(tbl) == 1
    assert tbl[0]["count"] == 4
    assert tbl[0]["fraction_positive"] == pytest.approx(0.25)
    assert tbl[0]["mean_predicted"] == pytest.approx(0.3)


def test_threshold_table_matches_confusion_and_selector() -> None:
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    tbl = ev.threshold_table(y, s)
    for r in tbl.to_dicts():  # 各行の tp/fp/fn/tn は confusion と一致（土台の共有）
        c = ev.confusion(y, s, threshold=r["threshold"])
        assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (c["tp"], c["fp"], c["fn"], c["tn"])
    best_t, _ = ev.select_threshold_max_f1(y, s)  # f1 最大の行の閾値が選択器と一致
    max_row = max(tbl.to_dicts(), key=lambda r: r["f1"])
    assert max_row["threshold"] == pytest.approx(best_t)
