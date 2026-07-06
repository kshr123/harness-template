"""特徴量枠組み features.py の単体テスト。期待値は入力の構成から導ける。"""

from __future__ import annotations

from datetime import datetime

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
    DateTimeFeatures,
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


def test_datetime_parts_are_polars_ranges() -> None:
    # 2021-01-15 は金曜・2021-12-15 は水曜。polars の weekday は 1..7（月曜=1）なので 5 と 3。
    x = pl.DataFrame({"t": [datetime(2021, 1, 15, 9, 0), datetime(2021, 12, 15, 23, 0)]})
    out = DateTimeFeatures(["t"]).fit(x).transform(x)
    assert out["t_year"].to_list() == [2021, 2021]
    assert out["t_month"].to_list() == [1, 12]  # month は 1..12
    assert out["t_day"].to_list() == [15, 15]
    assert out["t_weekday"].to_list() == [5, 3]  # 金=5・水=3（月曜=1 起点）
    assert out["t_hour"].to_list() == [9, 23]  # hour は 0..23


def test_datetime_cyclical_month_unit_circle_and_wraparound() -> None:
    # 12 か月ぶんの月初。sin²+cos²=1（単位円上）。位相は 2π(month-1)/12 なので month=1 は角度 0（sin=0, cos=1）。
    x = pl.DataFrame({"t": [datetime(2021, m, 1) for m in range(1, 13)]})
    out = DateTimeFeatures(["t"], parts=(), cyclical=("month",)).transform(x)
    s = out["t_month_sin"].to_numpy()
    c = out["t_month_cos"].to_numpy()
    np.testing.assert_allclose(s**2 + c**2, 1.0)
    np.testing.assert_allclose([s[0], c[0]], [0.0, 1.0], atol=1e-12)
    # 周期性：12月→1月の距離が 1月→2月の距離と等しい（12月と1月は隣＝不連続が消えている）。
    dist_12_to_1 = np.hypot(s[11] - s[0], c[11] - c[0])
    dist_1_to_2 = np.hypot(s[0] - s[1], c[0] - c[1])
    np.testing.assert_allclose(dist_12_to_1, dist_1_to_2)


def test_datetime_cyclical_hour_wraps_around_midnight() -> None:
    # hour=23 と hour=0 の距離が hour=0 と hour=1 の距離と等しい（日またぎで隣接）。
    x = pl.DataFrame({"t": [datetime(2021, 1, 1, h) for h in (0, 1, 23)]})
    out = DateTimeFeatures(["t"], parts=(), cyclical=("hour",)).transform(x)
    s = out["t_hour_sin"].to_numpy()
    c = out["t_hour_cos"].to_numpy()
    dist_23_to_0 = np.hypot(s[2] - s[0], c[2] - c[0])
    dist_0_to_1 = np.hypot(s[0] - s[1], c[0] - c[1])
    np.testing.assert_allclose(dist_23_to_0, dist_0_to_1)


def test_datetime_cyclical_weekday_wraps_and_anchors_monday() -> None:
    # 2021-01-18(月)〜01-24(日)＝weekday 1..7。位相 2π(weekday-1)/7 なので月曜(1)は角度 0（sin=0, cos=1）
    # ＝-1 補正忘れをアンカーで検出。日曜(7)→月曜(1) の距離が 月(1)→火(2) と等しい（週またぎで隣接）。
    x = pl.DataFrame({"t": [datetime(2021, 1, d) for d in range(18, 25)]})
    out = DateTimeFeatures(["t"], parts=(), cyclical=("weekday",)).transform(x)
    s = out["t_weekday_sin"].to_numpy()
    c = out["t_weekday_cos"].to_numpy()
    np.testing.assert_allclose(s**2 + c**2, 1.0)
    np.testing.assert_allclose([s[0], c[0]], [0.0, 1.0], atol=1e-12)  # 月曜=角度 0（-1 補正の確認）
    dist_sun_to_mon = np.hypot(s[6] - s[0], c[6] - c[0])  # 日(idx6)→月(idx0)
    dist_mon_to_tue = np.hypot(s[0] - s[1], c[0] - c[1])
    np.testing.assert_allclose(dist_sun_to_mon, dist_mon_to_tue)


def test_datetime_feature_names_match_output() -> None:
    # parts と cyclical に同じ part（month）があれば整数列と sin/cos の両方が出る。順序は parts → cyclical。
    x = pl.DataFrame({"t": [datetime(2021, 1, 15, 9, 0)]})
    block = DateTimeFeatures(["t"], parts=("year", "month"), cyclical=("month", "hour"))
    out = block.transform(x)
    expected = ["t_year", "t_month", "t_month_sin", "t_month_cos", "t_hour_sin", "t_hour_cos"]
    assert out.columns == expected
    assert block.feature_names() == expected  # 無状態＝fit 前でも確定


def test_datetime_rejects_unknown_part_and_cycle() -> None:
    x = pl.DataFrame({"t": [datetime(2021, 1, 1)]})
    with pytest.raises(ValueError, match="part"):
        DateTimeFeatures(["t"], parts=("minute_of_century",)).transform(x)
    with pytest.raises(ValueError, match="cyclical"):
        DateTimeFeatures(["t"], cyclical=("year",)).feature_names()  # year は周期を持たない
