"""cv.run_cv の結線テスト（統合）。sklearn の estimator を fold ごとに clone して回すことを確かめる。

- 結線：DummyClassifier(strategy="prior") は train 側の陽性率を返すので、oof の各 valid が
  その fold の train 陽性率と一致することで「clone→train で fit→valid を予測」の結線を厳密に確かめる。
- 漏れ防止：train と valid で分布をずらし、Pipeline 内の StandardScaler が train 側だけで fit された
  （mean_ が train 部の平均）ことを estimators から確認する（漏れていれば混ざった平均になる）。
- fold 表の store 往復も併せて確かめる。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import NotFittedError
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.validation import check_is_fitted

from harness.ds import cv, data, store

pytestmark = pytest.mark.integration


def test_run_cv_clones_and_leaves_original_unfitted() -> None:
    # run_cv は fold ごとに clone してから fit する。元の estimator は未 fit のまま——
    # これが「漏れ防止は構造」の担保。clone を消して同一オブジェクトを再 fit する退行が入れば、
    # 元 estimator が fit 済みになり NotFittedError が出ず、このテストが落ちる。
    x = data.generate_synthetic(n=20, seed=0).select("x1", "x2")
    y = np.array([0, 1] * 10, dtype=np.float64)
    estimator = Pipeline([("sc", StandardScaler()), ("m", DummyClassifier(strategy="prior"))])
    cv.run_cv(estimator, x, y, cv.holdout_indices(10, 10), predict="proba")
    with pytest.raises(NotFittedError):
        check_is_fitted(estimator.named_steps["sc"])


def test_run_cv_wiring_with_dummy() -> None:
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1, 0, 1] * 3, dtype=np.float64)  # 30 行
    x = data.generate_synthetic(n=30, seed=0).select("x1", "x2")
    splits = [
        (np.arange(10, 30, dtype=np.int64), np.arange(0, 10, dtype=np.int64)),
        (np.concatenate([np.arange(0, 10), np.arange(20, 30)]).astype(np.int64), np.arange(10, 20, dtype=np.int64)),
        (np.arange(0, 20, dtype=np.int64), np.arange(20, 30, dtype=np.int64)),
    ]
    result = cv.run_cv(DummyClassifier(strategy="prior"), x, y, splits, predict="proba")

    assert len(result.estimators) == 3  # fold ごとに 1 つずつ学習済み estimator
    assert result.oof_mask.all()  # OOF は全行埋まる
    for train_idx, valid_idx in splits:
        # DummyClassifier(prior) の陽性確率＝train の陽性率。oof はそれが入る（構成から厳密）。
        np.testing.assert_allclose(result.oof[valid_idx], y[train_idx].mean())
    assert len(result.fold_metrics) == 3


def test_run_cv_no_leak_standardscaler_fits_on_train_only() -> None:
    # train 部（行 0:10）は f=0、valid 部（行 10:20）は f=100。分布をずらす。
    x = (
        data.generate_synthetic(n=20, seed=0)
        .with_columns(f=np.concatenate([np.zeros(10), np.full(10, 100.0)]))
        .select("f")
    )
    y = np.array([0, 1] * 10, dtype=np.float64)
    splits = cv.holdout_indices(10, 10)
    estimator = Pipeline([("sc", StandardScaler()), ("m", DummyClassifier(strategy="prior"))])
    result = cv.run_cv(estimator, x, y, splits, predict="proba")

    fitted_scaler = result.estimators[0].named_steps["sc"]  # type: ignore[attr-defined]
    # train 側（f=0）だけで fit された証拠。valid の f=100 が混ざっていれば平均は 50 になる。
    np.testing.assert_allclose(fitted_scaler.mean_, [0.0])


def test_run_cv_rejects_overlapping_valid() -> None:
    x = data.generate_synthetic(n=20, seed=0).select("x1", "x2")
    y = np.array([0, 1] * 10, dtype=np.float64)  # 両クラスある（predict_proba が 2 列になる）
    overlapping = [
        (np.arange(10, 20, dtype=np.int64), np.arange(0, 10, dtype=np.int64)),
        (np.arange(0, 10, dtype=np.int64), np.arange(5, 15, dtype=np.int64)),  # 5:10 が重複
    ]
    with pytest.raises(ValueError, match="重複"):
        cv.run_cv(DummyClassifier(strategy="prior"), x, y, overlapping, predict="proba")


def test_fold_table_store_roundtrip(make_project: Callable[..., Any]) -> None:
    # make_folds → store.save(split 層) → load → fold_indices が元と一致すること＋再保存拒否。
    proj = make_project()
    proj.add_schema(
        {
            "id": "folds",
            "description": "fold 割当",
            "layer": "split",
            "scope": "project",
            "primary_key": ["id"],
            "columns": [
                {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
                {"name": "fold", "dtype": "Int64", "nullable": False},
            ],
        }
    )
    root: Path = proj.root
    df = data.generate_synthetic(n=30, seed=0)
    folds = cv.make_folds(df, n_folds=3, seed=1)
    store.save(root, folds, "folds")
    loaded = store.load(root, "folds")

    for (tr_a, va_a), (tr_b, va_b) in zip(cv.fold_indices(df, folds), cv.fold_indices(df, loaded), strict=True):
        np.testing.assert_array_equal(tr_a, tr_b)
        np.testing.assert_array_equal(va_a, va_b)

    with pytest.raises(ValueError, match="split"):
        store.save(root, folds, "folds")  # split 層は再書き込みを許さない
