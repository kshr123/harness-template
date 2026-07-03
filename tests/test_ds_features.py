"""特徴量枠組み features.py の単体テスト。期待値は入力の構成から導ける。"""

from __future__ import annotations

import polars as pl
import pytest

from harness.ds.features import Columns, FeaturePipeline, Interactions

pytestmark = pytest.mark.unit


def test_interactions_computes_products() -> None:
    x = pl.DataFrame({"x1": [1.0, 2.0, 3.0], "x2": [4.0, 5.0, 6.0]})
    out = Interactions([("x1", "x2")]).fit(x).transform(x)
    assert out.columns == ["x1_x_x2"]
    assert out["x1_x_x2"].to_list() == [4.0, 10.0, 18.0]  # 1*4, 2*5, 3*6


def test_columns_passthrough() -> None:
    x = pl.DataFrame({"x1": [1.0], "x2": [2.0], "id": [0]})
    out = Columns(["x1", "x2"]).transform(x)
    assert out.columns == ["x1", "x2"]


def test_feature_pipeline_composes_and_describes() -> None:
    x = pl.DataFrame({"x1": [1.0, 2.0], "x2": [3.0, 4.0]})
    pipe = FeaturePipeline([("base", Columns(["x1", "x2"])), ("inter", Interactions([("x1", "x2")]))])
    out = pipe.fit(x).transform(x)
    assert out.columns == ["x1", "x2", "x1_x_x2"]
    assert pipe.feature_names() == ["x1", "x2", "x1_x_x2"]
    assert pipe.describe() == [
        {"block": "base", "output_columns": ["x1", "x2"]},
        {"block": "inter", "output_columns": ["x1_x_x2"]},
    ]


def test_feature_pipeline_rejects_duplicate_output_columns() -> None:
    x = pl.DataFrame({"x1": [1.0, 2.0]})
    pipe = FeaturePipeline([("a", Columns(["x1"])), ("b", Columns(["x1"]))])  # 両方 x1 を出す
    with pytest.raises(ValueError, match="重複"):
        pipe.fit(x).transform(x)
