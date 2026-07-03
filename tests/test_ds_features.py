"""特徴量枠組み features.py の単体テスト。期待値は入力の構成から導ける。"""

from __future__ import annotations

import polars as pl
import pytest
from sklearn.base import clone
from sklearn.exceptions import NotFittedError

from harness.ds.features import (
    Columns,
    CountEncode,
    Differences,
    FeaturePipeline,
    GroupAggregate,
    Interactions,
    Ratios,
)

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


def test_ratios_zero_and_null_become_null() -> None:
    x = pl.DataFrame({"a": [6.0, 9.0, 1.0], "b": [2.0, 3.0, 0.0]})
    out = Ratios([("a", "b")]).fit(x).transform(x)
    assert out["a_div_b"].to_list() == [3.0, 3.0, None]  # 6/2, 9/3, 1/0→null


def test_differences_propagate_null() -> None:
    x = pl.DataFrame({"a": [5.0, None], "b": [2.0, 1.0]})
    out = Differences([("a", "b")]).fit(x).transform(x)
    assert out["a_minus_b"].to_list() == [3.0, None]


def test_group_aggregate_learns_group_stats() -> None:
    x = pl.DataFrame({"g": ["A", "A", "B"], "v": [1.0, 3.0, 5.0]})
    out = GroupAggregate("g", ["v"], ["mean", "max"]).fit(x).transform(x)
    assert out.columns == ["v_mean_by_g", "v_max_by_g"]
    assert out["v_mean_by_g"].to_list() == [2.0, 2.0, 5.0]  # A: (1+3)/2, B: 5
    assert out["v_max_by_g"].to_list() == [3.0, 3.0, 5.0]


def test_group_aggregate_unknown_group_uses_global() -> None:
    x = pl.DataFrame({"g": ["A", "A", "B"], "v": [1.0, 3.0, 5.0]})
    block = GroupAggregate("g", ["v"], ["mean", "max"]).fit(x)
    out = block.transform(pl.DataFrame({"g": ["C"], "v": [9.0]}))
    assert out["v_mean_by_g"].to_list() == [3.0]  # 全体 mean (1+3+5)/3
    assert out["v_max_by_g"].to_list() == [5.0]


def test_group_aggregate_derived_ratio_and_diff() -> None:
    x = pl.DataFrame({"g": ["A", "A"], "v": [0.0, 4.0]})  # グループ mean 2
    out = GroupAggregate("g", ["v"], ["mean"], derived=["ratio", "diff"]).fit(x).transform(x)
    assert out.columns == ["v_mean_by_g", "v_mean_by_g_ratio", "v_mean_by_g_diff"]
    assert out["v_mean_by_g_ratio"].to_list() == [0.0, 2.0]  # 0/2, 4/2
    assert out["v_mean_by_g_diff"].to_list() == [-2.0, 2.0]  # 0-2, 4-2


def test_group_aggregate_null_group() -> None:
    x = pl.DataFrame({"g": [None, None, "A"], "v": [2.0, 4.0, 9.0]})
    out = GroupAggregate("g", ["v"], ["mean"]).fit(x).transform(x)
    assert out["v_mean_by_g"].to_list() == [3.0, 3.0, 9.0]  # null も 1 グループ（(2+4)/2）


def test_group_aggregate_rejects_unknown_agg() -> None:
    x = pl.DataFrame({"g": ["A"], "v": [1.0]})
    with pytest.raises(ValueError, match="未対応の集約"):
        GroupAggregate("g", ["v"], ["variance"]).fit(x)


def test_count_encode() -> None:
    x = pl.DataFrame({"c": ["A", "A", "A", "B", "B", "C"]})
    block = CountEncode(["c"]).fit(x)
    out = block.transform(x)
    assert out.columns == ["c_count"]
    assert out["c_count"].to_list() == [3, 3, 3, 2, 2, 1]
    assert block.transform(pl.DataFrame({"c": ["D"]}))["c_count"].to_list() == [0]  # 未知は 0


def test_count_encode_normalize() -> None:
    x = pl.DataFrame({"c": ["A", "A", "A", "B", "B", "C"]})  # 6 行・A=3
    out = CountEncode(["c"], normalize=True).fit(x).transform(pl.DataFrame({"c": ["A"]}))
    assert out["c_freq"].to_list() == [0.5]  # 3/6


def test_feature_names_match_output_columns() -> None:
    x = pl.DataFrame({"x1": [1.0, 2.0], "x2": [3.0, 4.0], "g": ["A", "A"]})
    blocks = [
        Columns(["x1"]),
        Interactions([("x1", "x2")]),
        Ratios([("x1", "x2")]),
        Differences([("x1", "x2")]),
        GroupAggregate("g", ["x1"], ["mean"], derived=["diff"]),
        CountEncode(["g"]),
    ]
    for block in blocks:
        out = block.fit(x).transform(x)
        assert block.feature_names() == out.columns  # 列順の契約（feature_names＝出力列順）


def test_stateful_unfitted_and_clone_lose_state() -> None:
    x = pl.DataFrame({"g": ["A", "A"], "v": [1.0, 2.0]})
    block = GroupAggregate("g", ["v"], ["mean"])
    with pytest.raises(NotFittedError):
        block.transform(x)  # fit 前
    fitted = block.fit(x)
    fitted.transform(x)  # ok
    with pytest.raises(NotFittedError):
        clone(fitted).transform(x)  # clone は状態を落とす（fold 独立性の前提）
