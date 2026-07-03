"""cv.run_cv の結線テスト（統合）。Fake の学習器で「繋がっていること」を確かめる。

Fake は呼ばれた順に定数 (呼び出し回数)/10 を返すだけの学習器（Trainer 契約を満たす最小実装）。
これで OOF が全行埋まること・呼び出し回数・fold ごとに種が違うこと・valid 重複の検知を、
テストデータの構成から導ける値で固定する。fold 表の store 往復も併せて確かめる。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from harness.ds import cv, data, store

pytestmark = pytest.mark.integration


@dataclass
class FakeTrainer:
    """呼ばれるたびに記録し、その回の定数予測を返す（1 回目→0.1, 2 回目→0.2, …）。"""

    seeds: list[int] = field(default_factory=list)
    shapes: list[tuple[int, int]] = field(default_factory=list)

    def train(
        self,
        x_train: NDArray[np.float64],
        y_train: NDArray[np.float64],
        x_valid: NDArray[np.float64],
        y_valid: NDArray[np.float64],
        *,
        seed: int,
    ) -> cv.FoldOutcome:
        self.seeds.append(seed)
        self.shapes.append((len(x_train), len(x_valid)))
        value = len(self.seeds) / 10.0  # 1 回目=0.1, 2 回目=0.2, 3 回目=0.3
        return cv.FoldOutcome(y_pred=np.full(len(x_valid), value, dtype=np.float64), model=object())


def _xy(n: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    x = np.arange(n * 2, dtype=np.float64).reshape(n, 2)
    y = np.zeros(n, dtype=np.float64)  # 指標は結線確認では見ないので単純な値
    return x, y


def test_run_cv_wiring_fills_oof_and_counts_calls() -> None:
    x, y = _xy(30)
    # 3 fold：valid が 0:10, 10:20, 20:30 を順に覆う分割。
    splits = [
        (np.arange(10, 30, dtype=np.int64), np.arange(0, 10, dtype=np.int64)),
        (np.concatenate([np.arange(0, 10), np.arange(20, 30)]).astype(np.int64), np.arange(10, 20, dtype=np.int64)),
        (np.arange(0, 20, dtype=np.int64), np.arange(20, 30, dtype=np.int64)),
    ]
    trainer = FakeTrainer()
    result = cv.run_cv(x, y, splits, trainer, seed=42)

    assert len(trainer.seeds) == 3  # train は fold 数だけ呼ばれる
    assert result.oof_mask.all()  # OOF は全行埋まる
    np.testing.assert_array_equal(result.oof[0:10], 0.1)  # 1 回目の予測が最初の valid に入る
    np.testing.assert_array_equal(result.oof[10:20], 0.2)
    np.testing.assert_array_equal(result.oof[20:30], 0.3)
    assert len(result.fold_metrics) == 3
    assert len(set(trainer.seeds)) == 3  # fold ごとに種が異なる（SeedSequence で導出）


def test_run_cv_holdout_single_fold() -> None:
    x, y = _xy(30)
    trainer = FakeTrainer()
    result = cv.run_cv(x, y, cv.holdout_indices(20, 10), trainer, seed=1)
    assert len(trainer.seeds) == 1  # 固定分割＝要素1 → 1 回だけ
    assert result.oof_mask.sum() == 10  # valid の 10 行だけ覆う
    assert not result.oof_mask[0:20].any()  # train 側は未カバー（黙って 0 埋めしない）


def test_run_cv_rejects_overlapping_valid() -> None:
    x, y = _xy(20)
    overlapping = [
        (np.arange(10, 20, dtype=np.int64), np.arange(0, 10, dtype=np.int64)),
        (np.arange(0, 10, dtype=np.int64), np.arange(5, 15, dtype=np.int64)),  # 5:10 が重複
    ]
    with pytest.raises(ValueError, match="重複"):
        cv.run_cv(x, y, overlapping, FakeTrainer(), seed=0)


def test_fold_table_store_roundtrip(make_project: Callable[..., Any]) -> None:
    # make_folds → store.save(split 層) → load → fold_indices が元と一致すること。
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

    before = cv.fold_indices(df, folds)
    after = cv.fold_indices(df, loaded)
    for (tr_a, va_a), (tr_b, va_b) in zip(before, after, strict=True):
        np.testing.assert_array_equal(tr_a, tr_b)
        np.testing.assert_array_equal(va_a, va_b)

    # split 層は同じ id への再書き込みを許さない（分割を切り直さない）。
    with pytest.raises(ValueError, match="split"):
        store.save(root, folds, "folds")
