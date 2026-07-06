"""OOF 予測の深掘り（analysis）の単体テスト：期待値はデータ構成から導出する。"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from numpy.typing import NDArray

from harness.ds import analysis

pytestmark = pytest.mark.unit


def test_segment_metrics_classification() -> None:
    seg = pl.Series("s", ["A", "A", "B", "B"])
    y = np.array([1, 1, 0, 0], dtype="int64")
    score = np.array([0.9, 0.9, 0.9, 0.9], dtype="float64")  # 全部 pred=1（閾値0.5）
    out = {r["segment"]: r for r in analysis.segment_metrics(seg, y, score).to_dicts()}
    assert out["A"]["accuracy"] == 1.0  # A は y==1 で当たり
    assert out["B"]["accuracy"] == 0.0  # B は y==0 で全外し
    assert out["A"]["count"] == 2


def test_segment_metrics_multiclass_argmax_accuracy_from_construction() -> None:
    # A は 3 行とも argmax＝正解ラベル（accuracy=1.0）。B は全行 argmax=0 → y=0 の 1 行だけ正解（1/3）。
    seg = pl.Series("s", ["A", "A", "A", "B", "B", "B"])
    y = np.array([0, 1, 2, 0, 1, 2], dtype="int64")
    proba = np.array(
        [
            [0.8, 0.1, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.1, 0.8],
            [0.8, 0.1, 0.1],
            [0.8, 0.1, 0.1],
            [0.8, 0.1, 0.1],
        ],
        dtype="float64",
    )
    out = {r["segment"]: r for r in analysis.segment_metrics(seg, y, proba, task="multiclass").to_dicts()}
    assert out["A"]["accuracy"] == 1.0
    assert out["B"]["accuracy"] == pytest.approx(1 / 3)
    assert out["A"]["count"] == 3
    assert out["B"]["count"] == 3


def test_segment_metrics_fail_loud_on_score_shape() -> None:
    seg = pl.Series("s", ["A", "B"])
    y = np.array([0, 1], dtype="int64")
    proba = np.array([[0.7, 0.2, 0.1], [0.1, 0.8, 0.1]], dtype="float64")
    with pytest.raises(ValueError, match="2 次元"):  # 多クラスに 1 次元スコアは不可
        analysis.segment_metrics(seg, y, np.array([0.5, 0.5]), task="multiclass")
    with pytest.raises(ValueError, match="1 次元"):  # 既定（二値）に proba 行列は不可
        analysis.segment_metrics(seg, y, proba)


def test_segment_metrics_regression_residual_mean() -> None:
    seg = pl.Series("s", ["A", "A", "B", "B"])
    yt = np.array([2.0, 3.0, 5.0, 6.0])
    yp = np.array([1.0, 2.0, 6.0, 7.0])  # A の残差 +1 固定・B の残差 −1 固定
    out = {r["segment"]: r for r in analysis.segment_metrics(seg, yt, yp, task="regression").to_dicts()}
    assert out["A"]["residual_mean"] == pytest.approx(1.0)
    assert out["B"]["residual_mean"] == pytest.approx(-1.0)


def test_worst_rows_orders_by_error() -> None:
    df = pl.DataFrame({"id": [0, 1, 2, 3]})
    y = np.array([0, 0, 1, 1], dtype="int64")
    score = np.array([0.0, 0.1, 0.2, 1.0], dtype="float64")  # error=|y-score|: 0, .1, .8, 0
    top = analysis.worst_rows(df, y, score, n=2)
    assert top["id"].to_list()[0] == 2  # 最大誤差の行
    assert top.height == 2
    assert "error" in top.columns


def test_worst_rows_multiclass_orders_by_true_class_proba() -> None:
    # error＝1 − 正解クラスに割いた確率（構成から厳密）：0.1, 0.3, 0.9, 0.7 → 上位 2 行は id=2, 3。
    df = pl.DataFrame({"id": [0, 1, 2, 3]})
    y = np.array([0, 1, 2, 0], dtype="int64")
    proba = np.array(
        [
            [0.9, 0.05, 0.05],  # p_true=0.9・argmax=0（正解）
            [0.1, 0.7, 0.2],  # p_true=0.7・argmax=1（正解）
            [0.5, 0.4, 0.1],  # p_true=0.1・argmax=0（外し）
            [0.3, 0.4, 0.3],  # p_true=0.3・argmax=1（外し）
        ],
        dtype="float64",
    )
    top = analysis.worst_rows(df, y, proba, n=2, task="multiclass")
    assert top["id"].to_list() == [2, 3]
    assert top["y_pred"].to_list() == [0, 1]  # argmax ラベル
    assert top["y_score"].to_list() == pytest.approx([0.1, 0.3])  # 正解クラスに割いた確率
    assert top["error"].to_list() == pytest.approx([0.9, 0.7])


def test_worst_rows_multiclass_rejects_out_of_range_labels() -> None:
    df = pl.DataFrame({"id": [0, 1]})
    proba = np.array([[0.5, 0.3, 0.2], [0.2, 0.5, 0.3]], dtype="float64")
    with pytest.raises(ValueError, match="0..n_classes-1"):  # ラベル 3 は proba の列（0..2）を指せない
        analysis.worst_rows(df, np.array([0, 3], dtype="int64"), proba, task="multiclass")


def test_worst_rows_fail_loud_on_score_shape() -> None:
    df = pl.DataFrame({"id": [0, 1]})
    y = np.array([0, 1], dtype="int64")
    proba = np.array([[0.7, 0.2, 0.1], [0.1, 0.8, 0.1]], dtype="float64")
    with pytest.raises(ValueError, match="1 次元"):  # 既定（二値）に proba 行列は不可
        analysis.worst_rows(df, y, proba)
    with pytest.raises(ValueError, match="2 次元"):  # 多クラスに 1 次元スコアは不可
        analysis.worst_rows(df, y, np.array([0.5, 0.5]), task="multiclass")


def test_residual_summary_from_construction() -> None:
    r = analysis.residual_summary(np.array([0.0, 0.0]), np.array([3.0, 4.0]))  # 残差 -3, -4
    assert r["mean"] == pytest.approx(-3.5)
    assert r["min"] == pytest.approx(-4.0)
    assert r["max"] == pytest.approx(-3.0)


class _IdentityEstimator:
    """predict が x1 列をそのまま返す偽推定器。全行を v に置換すると平均予測＝v（構成から厳密）。"""

    def predict(self, x: pl.DataFrame) -> NDArray[np.float64]:
        return x["x1"].to_numpy()


class _SpyEstimator:
    """受け取った DataFrame を記録し x2 列を返す偽推定器（他列が保たれるかの観測用）。"""

    def __init__(self) -> None:
        self.received: list[pl.DataFrame] = []

    def predict(self, x: pl.DataFrame) -> NDArray[np.float64]:
        self.received.append(x)
        return x["x2"].to_numpy()


def test_partial_dependence_monotone_increasing_with_logreg() -> None:
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(0)
    x1 = rng.normal(size=200)
    x = pl.DataFrame({"x1": x1})
    y = (x1 > 0).astype("int64")  # x1 が大きいほど陽性（線形分離）
    est = LogisticRegression(random_state=0).fit(x, y)
    out = analysis.partial_dependence_table(est, x, "x1")
    assert out.columns == ["feature_value", "avg_prediction"]
    avg = out["avg_prediction"].to_list()
    assert all(a < b for a, b in zip(avg, avg[1:], strict=False))  # 単調増加（logreg のシグモイドは狭義単調）
    assert avg[0] < 0.5 < avg[-1]  # 分離データ＝左端は陰性側・右端は陽性側


def test_partial_dependence_grid_passthrough_sorted() -> None:
    x = pl.DataFrame({"x1": [0.0, 10.0, 20.0]})
    out = analysis.partial_dependence_table(_IdentityEstimator(), x, "x1", grid=[0.5, -1.0, 2.0], predict="value")
    assert out["feature_value"].to_list() == [-1.0, 0.5, 2.0]  # 渡した 3 値ちょうど・昇順
    assert out["avg_prediction"].to_list() == [-1.0, 0.5, 2.0]  # 恒等予測＝全行置換の平均はグリッド値そのもの


def test_partial_dependence_n_points_linspace() -> None:
    x = pl.DataFrame({"x1": np.arange(21, dtype="float64")})  # ユニーク 21 個 > n_points=5 → 等分
    out = analysis.partial_dependence_table(_IdentityEstimator(), x, "x1", n_points=5, predict="value")
    assert out["feature_value"].to_list() == [0.0, 5.0, 10.0, 15.0, 20.0]  # min..max（0..20）の 5 等分
    assert out.height == 5


def test_partial_dependence_discrete_uses_unique_values() -> None:
    x = pl.DataFrame({"x1": [2, 0, 1, 0, 2, 1]})  # ユニーク {0,1,2} ≤ n_points → ユニーク値がグリッド
    out = analysis.partial_dependence_table(_IdentityEstimator(), x, "x1", predict="value")
    assert out["feature_value"].to_list() == [0.0, 1.0, 2.0]
    assert out.height == 3


def test_partial_dependence_keeps_other_columns() -> None:
    x = pl.DataFrame({"x1": [1.0, 2.0, 3.0], "x2": [10.0, 20.0, 30.0]})
    spy = _SpyEstimator()
    out = analysis.partial_dependence_table(spy, x, "x1", grid=[99.0], predict="value")
    assert len(spy.received) == 1
    seen = spy.received[0]
    assert seen["x1"].to_list() == [99.0, 99.0, 99.0]  # feature 列だけ全行置換
    assert seen["x2"].to_list() == x["x2"].to_list()  # 他列は元のまま
    assert out["avg_prediction"].to_list()[0] == pytest.approx(20.0)  # x2 の平均＝置換の影響は feature 列だけ


@pytest.mark.integration
def test_partial_dependence_int_feature_with_join_encoder() -> None:
    # Int64 の離散 feature を CountEncode（transform で元列に join する）に通した Pipeline でも、置換が元 dtype を
    # 保つので f64 vs i64 の SchemaError を出さない。グリッドは離散ユニーク値そのもの（構成から）。
    from harness.ds.pipeline import build_estimator, build_model

    df = pl.DataFrame({"cat": np.array([0, 1, 2, 0, 1, 2, 0, 1], dtype=np.int64)})
    y = np.array([0, 1, 1, 0, 1, 1, 0, 1], dtype=np.float64)
    spec = {"features": [{"kind": "columns", "columns": ["cat"]}, {"kind": "count_encode", "columns": ["cat"]}]}
    est = build_estimator(spec, build_model({"kind": "logreg"}, seed=0), seed=0)
    est.fit(df, y)
    tbl = analysis.partial_dependence_table(est, df, "cat")  # 落ちない（元 dtype 保持）
    assert tbl["feature_value"].to_list() == [0.0, 1.0, 2.0]  # 離散ユニーク値がグリッド
    assert tbl.height == 3


@pytest.mark.integration
def test_partial_dependence_rejects_multiclass_proba() -> None:
    # 多クラス proba は (n, クラス数) で、平均すると 1/k に潰れて黙って誤る → fail-closed で止める。
    from harness.ds.pipeline import build_estimator, build_model

    rng = np.random.default_rng(0)
    x = pl.DataFrame({"a": np.concatenate([rng.normal(c, 0.5, 10) for c in (0.0, 5.0, 10.0)])})
    y = np.repeat(np.arange(3), 10).astype(np.float64)  # 3 クラス
    spec = {"features": [{"kind": "columns", "columns": ["a"]}]}
    est = build_estimator(spec, build_model({"kind": "logreg"}, seed=0), seed=0)
    est.fit(x, y)
    with pytest.raises(ValueError, match="多クラス"):
        analysis.partial_dependence_table(est, x, "a")
