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
