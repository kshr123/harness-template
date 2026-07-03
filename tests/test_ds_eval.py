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


def test_passes_requires_all_thresholds() -> None:
    metrics = {"accuracy": 0.8, "roc_auc": 0.85}
    # すべての閾値を満たす → 成功。
    assert ev.passes(metrics, {"accuracy": 0.75, "roc_auc": 0.8})
    # ひとつでも下回る → 失敗。
    assert not ev.passes(metrics, {"accuracy": 0.9})
    # 閾値に無い指標は判定に使わない（空の閾値は常に成功）。
    assert ev.passes(metrics, {})
