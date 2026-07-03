"""特徴量枠組み features.py の単体テスト。期待値は入力の構成から導ける。"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.base import clone
from sklearn.exceptions import NotFittedError
from sklearn.model_selection import KFold

from harness.ds.features import (
    Columns,
    CombineKeys,
    CountEncode,
    Differences,
    FeaturePipeline,
    GroupAggregate,
    Interactions,
    MultiHot,
    Ratios,
    TargetAggregate,
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


def test_combine_keys_joins_with_null_marker() -> None:
    x = pl.DataFrame({"a": ["x", None], "b": ["p", "q"]})
    out = CombineKeys([["a", "b"]]).fit(x).transform(x)
    assert out.columns == ["a__b"]
    assert out["a__b"].to_list() == ["x__p", "<null>__q"]  # null は <null> で区別


def test_multihot_min_count_unknown_and_null() -> None:
    x = pl.DataFrame({"t": [["a", "b"], ["a"], ["a"], ["c"]]})  # a:3行, b:1, c:1
    block = MultiHot("t", min_count=2).fit(x)
    assert block.feature_names() == ["t_a"]  # b・c は min_count 未満で落ちる
    out = block.transform(pl.DataFrame({"t": [["a", "z"], None]}))  # z は未知・null list
    assert out["t_a"].to_list() == [1, 0]  # 未知は無視・null は 0


def test_multihot_feature_names_before_fit_raises() -> None:
    with pytest.raises(NotFittedError):
        MultiHot("t").feature_names()  # データ依存：fit 前は確定しない


def test_target_aggregate_std_and_unknown_group() -> None:
    x = pl.DataFrame({"g": ["A", "A", "B", "B"]})
    y = np.array([0.0, 2.0, 5.0, 5.0])
    block = TargetAggregate(["g"], ["std"]).fit(x, y)
    out = block.transform(x)
    assert out["target_std_by_g"].to_list() == pytest.approx([2**0.5, 2**0.5, 0.0, 0.0])  # A: std[0,2], B: 0
    unknown = block.transform(pl.DataFrame({"g": ["C"]}))["target_std_by_g"].to_list()
    assert unknown == pytest.approx([float(np.std([0, 2, 5, 5], ddof=1))])  # 未知は全体 std


def test_target_aggregate_rejects_mean_and_missing_y() -> None:
    x = pl.DataFrame({"g": ["A"]})
    with pytest.raises(ValueError, match="mean"):
        TargetAggregate(["g"], ["mean"]).fit(x, np.array([1.0]))  # mean は sklearn TargetEncoder へ
    with pytest.raises(ValueError, match="target"):
        TargetAggregate(["g"], ["std"]).fit(x, None)  # y 必須


def test_target_aggregate_fit_transform_is_out_of_fold() -> None:
    # OOF：各行は反対 fold の y だけの統計で埋まる（単一グループなら反対 fold の std）。期待値は分割から導出。
    x = pl.DataFrame({"g": ["A"] * 4})
    y = np.array([0.0, 2.0, 10.0, 12.0])
    oof = TargetAggregate(["g"], ["std"], cv=2, seed=0).fit_transform(x, y)["target_std_by_g"].to_numpy()
    expected = np.empty(4)
    for train_idx, valid_idx in KFold(n_splits=2, shuffle=True, random_state=0).split(np.arange(4)):
        expected[valid_idx] = np.std(y[train_idx], ddof=1)
    np.testing.assert_allclose(oof, expected)
    # fit_transform（OOF）と fit→transform（全 train）は一致しない（内部 CV が生きている証拠）。
    full = TargetAggregate(["g"], ["std"], cv=2, seed=0).fit(x, y).transform(x)["target_std_by_g"].to_numpy()
    assert not np.allclose(oof, full)


def test_describe_marks_data_dependent_before_fit() -> None:
    pipe = FeaturePipeline([("m", MultiHot("t"))])
    assert pipe.describe()[0]["output_columns"] == "fit 後に確定（データ依存）"


def test_feature_pipeline_fit_transform_delegates_oof() -> None:
    # FeaturePipeline.fit_transform が各ブロックの fit_transform を呼ぶ（OOF 経路が生きる）ことの担保。
    x = pl.DataFrame({"g": ["A"] * 4})
    y = np.array([0.0, 2.0, 10.0, 12.0])
    oof = FeaturePipeline([("ta", TargetAggregate(["g"], ["std"], cv=2, seed=0))]).fit_transform(x, y)
    full = FeaturePipeline([("ta", TargetAggregate(["g"], ["std"], cv=2, seed=0))]).fit(x, y).transform(x)
    assert not np.allclose(oof["target_std_by_g"].to_numpy(), full["target_std_by_g"].to_numpy())
