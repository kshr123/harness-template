"""時間順分割（ML方式の時系列）：過去→未来の拡大窓。期待値は構成（時刻＝行番号）から導出する。"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import cv
from harness.ds.experiment import run_experiment
from harness.ds.pipeline import build_estimator, build_model


@pytest.mark.unit
def test_time_folds_expanding_is_past_to_future() -> None:
    df = pl.DataFrame({"id": np.arange(100), "t": np.arange(100)})  # 時刻＝行番号
    folds = cv.make_time_folds(df, n_folds=5, order_by="t")
    splits = cv.fold_indices(df, folds, how="expanding")
    assert len(splits) == 4  # fold 0 は valid にならない → 5-1=4 窓
    times = df["t"].to_numpy()
    valids: list[int] = []
    for train, valid in splits:
        assert times[train].max() < times[valid].min()  # 過去だけで学習（未来を見ない）
        assert set(train.tolist()).isdisjoint(set(valid.tolist()))
        valids.extend(valid.tolist())
    assert min(valids) == 20  # 最古ブロック（t=0..19）は valid に一度も入らない＝学習専用


@pytest.mark.unit
def test_order_by_and_stratify_are_exclusive() -> None:
    df = pl.DataFrame({"id": [0, 1], "t": [0, 1]})
    y = np.array([0.0, 1.0])
    with pytest.raises(ValueError, match="同時に使えない"):
        run_experiment(
            df,
            y,
            build_model({"kind": "ridge"}, seed=0),
            n_folds=2,
            seed=0,
            thresholds={},
            order_by="t",
            stratify_by="t",
        )


@pytest.mark.integration
def test_run_experiment_order_by_excludes_oldest_fold() -> None:
    rng = np.random.default_rng(0)
    n = 200
    t = np.arange(n)
    x1 = t / 100.0 + rng.normal(scale=0.05, size=n)  # 時間とともに動く
    df = pl.DataFrame({"id": np.arange(n), "t": t, "x1": x1})
    y = (2.0 * x1 + rng.normal(scale=0.05, size=n)).astype("float64")
    est = build_estimator(
        {"features": [{"kind": "columns", "columns": ["x1"]}]}, build_model({"kind": "ridge"}, seed=0), seed=0
    )
    res = run_experiment(df, y, est, n_folds=5, seed=0, thresholds={}, order_by="t", task="regression")
    assert not res.cv.oof_mask.all()  # 全行は覆わない（fold 0 は学習専用）
    assert res.cv.oof_mask[:40].sum() == 0  # 最古ブロック（40 行）は OOF に入らない
    assert res.cv.oof_mask[40:].all()  # 以降は覆う
