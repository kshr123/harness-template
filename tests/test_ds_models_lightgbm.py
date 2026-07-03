"""LightGBM（optional extra）の条件登録と未導入ヒントの検査。

開発・verify 環境は `uv sync --all-extras` で全部入り（AGENTS の DS 節の規約）＝ここは導入済みとして走る
（optional 依存のテストを skip しない）。未導入時の挙動は monkeypatch で MODELS から外して再現する。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import pipeline
from harness.ds.pipeline import MODELS, build_estimator, build_model


@pytest.mark.unit
def test_unknown_kind_hint_with_monkeypatched_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    # lightgbm を MODELS から一時的に外し「未導入」を再現 → エラー文に extra 導入コマンドが出る（自力復帰できる）。
    patched = {k: v for k, v in MODELS.items() if k != "lightgbm"}
    monkeypatch.setattr(pipeline, "MODELS", patched)
    with pytest.raises(ValueError, match="lightgbm.*uv sync --extra lightgbm"):
        build_model({"kind": "lightgbm"}, seed=0, task="classification")


@pytest.mark.integration
def test_lightgbm_registered_and_runs() -> None:
    # all-extras 環境（verify の規約）では lightgbm 系が登録され、背骨の proba 経路に載る。
    assert MODELS["lightgbm"].task == "classification"
    assert MODELS["lightgbm_reg"].task == "regression"
    rng = np.random.default_rng(0)
    x1 = rng.normal(size=200)
    x = pl.DataFrame({"x1": x1, "x2": rng.normal(size=200)})
    y = (x1 > 0).astype("int64")
    est = build_estimator(
        {"features": [{"kind": "columns", "columns": ["x1", "x2"]}]},
        build_model({"kind": "lightgbm", "n_estimators": 20}, seed=0, task="classification"),
        seed=0,
    )
    est.fit(x, y)
    assert est.predict_proba(x).shape == (200, 2)  # 二値の確率を返す
