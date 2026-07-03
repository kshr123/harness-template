"""EDA の結線テスト：分布差 AUC（drift_auc）は既存部品（build_estimator＋run_cv＋eval）の合成。

期待値はデータ構成から導出する（完全分離なら AUC≈1・見分けられなければ 0.5）。目的変数は使わない（リーク無し）。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import eda

pytestmark = pytest.mark.integration


def test_drift_auc_detects_shift() -> None:
    rng = np.random.default_rng(0)
    train = pl.DataFrame({"x1": rng.normal(size=100)})
    test = pl.DataFrame({"x1": rng.normal(size=100) + 10.0})  # 10σ ずらす＝ほぼ完全分離
    res = eda.drift_auc(train, test, columns=["x1"], seed=0)
    assert res.n_train == 100 and res.n_test == 100
    assert res.auc >= 0.95  # 構成上ほぼ見分けられる
    assert len(res.fold_aucs) == 5 and len(res.estimators) == 5


def test_drift_auc_half_when_indistinguishable() -> None:
    # 特徴量が定数 1 本＝スコアが全行同値 → 見分けられない（roc_auc の同値処理で 0.5）。
    const_train = pl.DataFrame({"x1": [1.0] * 100})
    const_test = pl.DataFrame({"x1": [1.0] * 100})
    assert eda.drift_auc(const_train, const_test, columns=["x1"], seed=0).auc == pytest.approx(0.5)
