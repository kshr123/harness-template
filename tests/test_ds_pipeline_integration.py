"""build_estimator で組んだ 3 段 Pipeline が run_cv を確実に通る（用意が『使える』）ことの結線テスト。

- 未知カテゴリが fold の valid にだけ現れても OneHot 既定で落ちず、encode も fold の train だけで学習される。
- bins/pca は null 入りでも中央値埋め既定で落ちない。TargetEncoder の内部 OOF が生きて決定的。列名が manifest まで通る。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import polars as pl
import pytest
from sklearn.linear_model import LogisticRegression

from harness.ds import cv
from harness.ds import models as model_store
from harness.ds.pipeline import build_estimator

pytestmark = pytest.mark.integration


def _model() -> LogisticRegression:
    return LogisticRegression(random_state=0, max_iter=1000)


def test_unseen_category_does_not_crash_and_learns_on_train_fold() -> None:
    df = pl.DataFrame(
        {
            "id": list(range(12)),
            "c": ["a"] * 6 + ["b"] * 4 + ["z"] * 2,  # z は末尾 2 行だけ
            "x1": [float(i) for i in range(12)],
            "y": [0, 1] * 6,
        }
    )
    y = df["y"].to_numpy().astype(np.float64)
    spec = {"features": [{"kind": "columns", "columns": ["c", "x1"]}], "encode": [{"kind": "onehot", "columns": ["c"]}]}
    est = build_estimator(spec, _model(), seed=0)
    # train は行 0:10（z 無し）、valid は 10:11（z あり）。未知カテゴリでも落ちないこと。
    result = cv.run_cv(est, df, y, [(np.arange(0, 10), np.array([10, 11]))], predict="proba")
    assert result.oof_mask.sum() == 2
    oh = result.estimators[0].named_steps["encode"].named_transformers_["onehot"]  # type: ignore[attr-defined]
    assert list(oh.categories_[0]) == ["a", "b"]  # train fold だけで学習（z は入らない＝漏れない）


def test_bins_and_pca_handle_null_through_cv() -> None:
    n = 20
    x1 = np.arange(n, dtype=np.float64)
    x1[0] = np.nan  # null を混ぜる（bins/pca は素で NaN に落ちる）
    df = pl.DataFrame({"id": range(n), "x1": x1, "x2": np.arange(n, dtype=np.float64), "y": [0, 1] * (n // 2)})
    y = df["y"].to_numpy().astype(np.float64)
    spec = {
        "features": [{"kind": "columns", "columns": ["x1", "x2"]}],
        "encode": [
            {"kind": "bins", "columns": ["x1"], "n_bins": 3},
            {"kind": "pca", "columns": ["x2"], "n_components": 1},
        ],
    }
    result = cv.run_cv(build_estimator(spec, _model(), seed=0), df, y, cv.holdout_indices(10, 10), predict="proba")
    assert result.oof_mask.sum() == 10
    assert bool(np.isfinite(result.oof[result.oof_mask]).all())  # 中央値埋め既定で NaN なく通る


def test_target_encoder_inner_oof_is_alive_and_deterministic() -> None:
    df = pl.DataFrame({"c": ["a", "a", "a", "a", "b", "b", "b", "b"]})
    y = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0])
    spec = {
        "features": [{"kind": "columns", "columns": ["c"]}],
        "encode": [{"kind": "target", "columns": ["c"], "cv": 2}],
    }
    ft = build_estimator(spec, _model(), seed=0)[:-1].fit_transform(df, y)
    tr = build_estimator(spec, _model(), seed=0)[:-1].fit(df, y).transform(df)
    assert not np.allclose(ft, tr)  # fit_transform(OOF) ≠ fit.transform(全train)＝内部 CV が生きている
    ft2 = build_estimator(spec, _model(), seed=0)[:-1].fit_transform(df, y)
    np.testing.assert_allclose(ft, ft2)  # 同 spec・同 seed で決定的


def test_feature_names_tracked_to_manifest(make_project: Callable[..., Any]) -> None:
    df = pl.DataFrame({"c": ["a", "b", "c", "a"], "x1": [1.0, 2.0, 3.0, 4.0], "y": [0, 1, 0, 1]})
    y = df["y"].to_numpy().astype(np.float64)
    spec = {"features": [{"kind": "columns", "columns": ["c", "x1"]}], "encode": [{"kind": "onehot", "columns": ["c"]}]}
    est = build_estimator(spec, _model(), seed=0)
    est.fit(df, y)
    names = list(est[:-1].get_feature_names_out())
    assert names == ["c_a", "c_b", "c_c", "x1"]  # onehot の 3 値 ＋ passthrough の x1
    proj = make_project()
    record = model_store.save_model(proj.root, est, name="m", work="E", feature_names=names)
    assert list(record.feature_names) == names  # 列名が manifest まで通る


def test_tfidf_sparse_output_fits_through_numpy_boundary() -> None:
    # tfidf は語彙が増えると scipy 疎行列を返す。model 直前の _to_numpy が密化しないと fit で落ちる（回帰防止）。
    rng = np.random.default_rng(0)
    vocab = [f"w{k}" for k in range(30)]  # 疎になる程度の語彙
    rows = [" ".join(rng.choice(vocab, size=4)) for _ in range(200)]
    df = pl.DataFrame({"txt": rows})
    y = np.array([1.0 if "w0" in t else 0.0 for t in rows])  # w0 の有無で決まる
    spec = {"features": [{"kind": "columns", "columns": ["txt"]}], "encode": [{"kind": "tfidf", "columns": "txt"}]}
    est = build_estimator(spec, _model(), seed=0)
    est.fit(df, y)  # 疎→密の境界が効いていれば落ちない
    assert est.predict_proba(df).shape == (200, 2)
