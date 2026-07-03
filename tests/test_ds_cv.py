"""cv.py の単体テスト（fold 割当・添字対）。期待値はテストデータの構成から導ける。"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import cv

pytestmark = pytest.mark.unit


def test_make_folds_even_sizes() -> None:
    # 20 行を 4 fold → 各 fold ちょうど 5 行（差 0）。
    df = pl.DataFrame({"id": np.arange(20, dtype=np.int64)})
    folds = cv.make_folds(df, n_folds=4, seed=0)
    counts = folds["fold"].value_counts().sort("fold")["count"].to_list()
    assert counts == [5, 5, 5, 5]


def test_make_folds_stratified_keeps_class_balance() -> None:
    # y が 8 個の 1 と 12 個の 0。4 fold で層化 → 各 fold は 1 が 2 個・0 が 3 個。
    df = pl.DataFrame({"id": np.arange(20, dtype=np.int64), "y": np.array([1] * 8 + [0] * 12, dtype=np.int64)})
    folds = cv.make_folds(df, n_folds=4, seed=0, stratify_by="y").join(df, on="id")
    for k in range(4):
        part = folds.filter(pl.col("fold") == k)
        assert part.filter(pl.col("y") == 1).height == 2
        assert part.filter(pl.col("y") == 0).height == 3


def test_make_folds_deterministic() -> None:
    df = pl.DataFrame({"id": np.arange(30, dtype=np.int64)})
    a = cv.make_folds(df, n_folds=5, seed=7)
    b = cv.make_folds(df, n_folds=5, seed=7)
    c = cv.make_folds(df, n_folds=5, seed=8)
    assert a.equals(b)  # 同じ (df, seed) → 同じ表
    assert not a.equals(c)  # 種が違えば別の表


def test_make_folds_rejects_bad_args() -> None:
    df = pl.DataFrame({"id": np.arange(3, dtype=np.int64)})
    with pytest.raises(ValueError, match="n_folds"):
        cv.make_folds(df, n_folds=1, seed=0)
    with pytest.raises(ValueError, match="少ない"):
        cv.make_folds(df, n_folds=5, seed=0)  # 行数 3 < 5


def test_fold_indices_roundtrip() -> None:
    df = pl.DataFrame({"id": np.arange(6, dtype=np.int64)})
    folds = pl.DataFrame({"id": np.arange(6, dtype=np.int64), "fold": np.array([0, 1, 0, 1, 0, 1], dtype=np.int64)})
    splits = cv.fold_indices(df, folds)
    assert len(splits) == 2
    # fold 0：valid＝行位置 0,2,4／train＝1,3,5（構成から厳密）。
    np.testing.assert_array_equal(splits[0][1], [0, 2, 4])
    np.testing.assert_array_equal(splits[0][0], [1, 3, 5])
    np.testing.assert_array_equal(splits[1][1], [1, 3, 5])


def test_fold_indices_rejects_id_mismatch() -> None:
    df = pl.DataFrame({"id": np.arange(3, dtype=np.int64)})
    folds = pl.DataFrame({"id": np.array([0, 1], dtype=np.int64), "fold": np.array([0, 1], dtype=np.int64)})
    with pytest.raises(ValueError, match="一致しない"):
        cv.fold_indices(df, folds)  # id=2 に fold が無い


def test_holdout_indices() -> None:
    splits = cv.holdout_indices(n_train=3, n_valid=2)
    assert len(splits) == 1
    np.testing.assert_array_equal(splits[0][0], [0, 1, 2])
    np.testing.assert_array_equal(splits[0][1], [3, 4])
