"""EDA の構造化レポートのテスト：期待値はデータ構成から導出する（ハードコード期待値禁止）。

作る側（ds.eda）と確かめる側（このテスト）を分け、レポートの数値が構成どおりであることを機械で保証する。
図は作らない（正本は構造化レポート）ので画像比較は無い。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from harness.ds import eda

pytestmark = pytest.mark.unit


def test_correlations_and_constant_column() -> None:
    df = pl.DataFrame(
        {"x1": [1.0, 2, 3, 4, 5], "x2": [5.0, 4, 3, 2, 1], "c": [1.0, 1, 1, 1, 1], "y": [1.0, 2, 3, 4, 5]}
    )
    corr = eda.correlations(df, target="y")
    d = {r["feature"]: r["correlation"] for r in corr.to_dicts()}
    assert d["x1"] == pytest.approx(1.0)  # y と完全一致
    assert d["x2"] == pytest.approx(-1.0)  # 逆相関
    assert d["c"] == 0.0  # 定数列は NaN でなく 0.0
    assert corr["feature"].to_list()[-1] == "c"  # |r| 降順＝定数が末尾


def test_high_correlation_pairs() -> None:
    df = pl.DataFrame({"a": [1.0, 2, 3, 4], "b": [2.0, 4, 6, 8], "c": [1.0, 0, 1, 0]})  # b=2a（r=1）
    pairs = [(r["a"], r["b"]) for r in eda.high_correlation_pairs(df, threshold=0.99).to_dicts()]
    assert ("a", "b") in pairs
    assert ("a", "c") not in pairs and ("b", "c") not in pairs


def test_psi_detects_out_of_range_shift() -> None:
    # train＝[0,1) の一様格子 100 点。test＝60% が同じ範囲・40% が train の範囲外 [1,2)。
    # ビン境界を train の min/max で閉じると範囲外の質量が histogram で落ち、再正規化で PSI≈0（安定と誤報）。
    # 外側ビンを ±inf に開くと最終ビンの実測は ~46%（範囲内の上位 ~6% + 範囲外 40%）対 期待 10% で、
    # その 1 ビンだけで (0.46-0.10)·ln(4.6) ≈ 0.55 → 「大きな変化」の目安 0.25 を確実に超える。
    train = pl.Series("v", [i / 100 for i in range(100)])
    test = pl.Series("v", [i / 60 for i in range(60)] + [1.0 + i / 40 for i in range(40)])
    assert eda.psi(train, test) > 0.25


def test_psi_all_null_train_returns_zero() -> None:
    # train が全欠損 → 分位点を計算できない（従来は np.quantile が IndexError）。
    # 定数 train（ビンを切れない）と同じく「分布差は測れない＝0.0」を返す。
    all_null = pl.Series("v", [None, None, None], dtype=pl.Float64)
    assert eda.psi(all_null, pl.Series("v", [1.0, 2.0, 3.0])) == 0.0


def test_psi_identical_is_zero() -> None:
    s = pl.Series("v", [float(i) for i in range(100)])
    assert eda.psi(s, s) == pytest.approx(0.0, abs=1e-9)  # 同一分布 → 0


def test_correlations_pairwise_complete_with_null() -> None:
    # x1 は null 1 行を除き y と完全に線形（x1=2y）・x2 は逆向き（x2=-y）。
    # null→NaN で np.corrcoef が NaN を返すと、polars の sort は NaN を最大として先頭に置く（誤読の温床）。
    # 有限な行だけ（pairwise-complete）で計算すれば r は ±1.0 になる。
    df = pl.DataFrame(
        {
            "x1": [2.0, 4.0, 6.0, None, 10.0, 12.0],
            "x2": [-1.0, -2.0, -3.0, -4.0, None, -6.0],
            "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    d = {r["feature"]: r["correlation"] for r in eda.correlations(df, target="y").to_dicts()}
    assert d["x1"] == pytest.approx(1.0)  # NaN でなく完全相関
    assert d["x2"] == pytest.approx(-1.0)


def test_high_correlation_pairs_flags_duplicate_with_null() -> None:
    # b は a のコピーだが 1 行だけ null（結合漏れ等でよくある重複列）。
    # NaN だと abs(NaN) >= threshold が False になり黙って見逃す。null 行を除けば r=1.0 で検出される。
    df = pl.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [1.0, 2.0, None, 4.0, 5.0]})
    pairs = {(r["a"], r["b"]): r["correlation"] for r in eda.high_correlation_pairs(df, threshold=0.99).to_dicts()}
    assert ("a", "b") in pairs
    assert pairs[("a", "b")] == pytest.approx(1.0)


def test_psi_constant_numeric_does_not_crash() -> None:
    # train が定数（分位点が 1 点）だとビンを切れない → 0.0 を返す（histogram の例外を避ける）。
    const = pl.Series("v", [5.0] * 20)
    assert eda.psi(const, pl.Series("v", [5.0] * 10)) == 0.0
    assert eda.psi(const, pl.Series("v", [7.0] * 10)) == 0.0  # test が違っても落ちない


def test_psi_categorical_known_value() -> None:
    train = pl.Series("c", ["a"] * 50 + ["b"] * 50)  # a:0.5 b:0.5
    test = pl.Series("c", ["a"] * 75 + ["b"] * 25)  # a:0.75 b:0.25
    # PSI = (0.75-0.5)ln(0.75/0.5) + (0.25-0.5)ln(0.25/0.5)（その他ビンは両側 0 で寄与なし）
    expected = 0.25 * np.log(1.5) - 0.25 * np.log(0.5)
    assert eda.psi(train, test) == pytest.approx(expected)


def test_compare_numeric_and_categorical() -> None:
    train = pl.DataFrame({"n": [0.0, 1, 2, 3, 4], "cat": ["a", "a", "b", "b", "c"]})
    test = pl.DataFrame({"n": [10.0, 11, 12, 13, 14], "cat": ["b", "c", "d", "d", "d"]})
    rep = eda.compare(train, test)
    assert rep.n_train == 5 and rep.n_test == 5
    num = {r["column"]: r for r in rep.numeric.to_dicts()}
    assert num["n"]["train_mean"] == pytest.approx(2.0)
    assert num["n"]["test_mean"] == pytest.approx(12.0)
    cat = {r["column"]: r for r in rep.categorical.to_dicts()}
    assert cat["cat"]["n_train_only"] == 1  # a
    assert cat["cat"]["n_test_only"] == 1  # d
    assert cat["cat"]["test_coverage"] == pytest.approx(0.4)  # test の b,c は train にある＝2/5


def test_compare_report_to_dict_serializable() -> None:
    import yaml

    train = pl.DataFrame({"n": [0.0, 1, 2], "cat": ["a", "b", "b"]})
    d = eda.compare(train, train).to_dict()
    assert list(d) == ["n_train", "n_test", "numeric", "categorical"]
    assert "n_train" in yaml.safe_dump(d, allow_unicode=True)


def _frame() -> pl.DataFrame:
    # 10 行。a に null を 2 個・9 行目は 8 行目と全列一致（重複 1 組）。
    return pl.DataFrame(
        {
            "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 8.0, None],
            "b": [None, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 8.0, 10.0],
            "cat": ["x", "x", "x", "y", "y", "z", "z", "w", "w", "w"],
        }
    ).with_columns(a=pl.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 8.0, None]))


def test_profile_nulls_and_duplicates() -> None:
    prof = eda.profile(_frame())
    assert prof.n_rows == 10
    assert prof.n_columns == 3
    cols = {r["column"]: r for r in prof.columns.to_dicts()}
    assert cols["a"]["null_count"] == 1  # a は null 1 個
    assert cols["a"]["null_ratio"] == pytest.approx(0.1)
    # 8 行目と 9 行目が全列一致（a=8,b=8,cat=w）→ 重複 1 組。
    assert prof.duplicate_rows == 1


def test_profile_numeric_stats_from_construction() -> None:
    df = pl.DataFrame({"v": [0.0, 2.0, 4.0, 6.0, 8.0]})  # mean=4・min=0・max=8・median=4
    num = {r["column"]: r for r in eda.profile(df).numeric.to_dicts()}
    assert num["v"]["mean"] == pytest.approx(4.0)
    assert num["v"]["min"] == pytest.approx(0.0)
    assert num["v"]["max"] == pytest.approx(8.0)
    assert num["v"]["median"] == pytest.approx(4.0)


def test_profile_categorical_top() -> None:
    df = pl.DataFrame({"c": ["a", "a", "a", "b", "b"]})  # a が 3/5=0.6 で最頻
    cat = {r["column"]: r for r in eda.profile(df).categorical.to_dicts()}
    assert cat["c"]["n_unique"] == 2
    assert cat["c"]["top_value"] == "a"
    assert cat["c"]["top_count"] == 3
    assert cat["c"]["top_ratio"] == pytest.approx(0.6)


def test_profile_to_dict_is_serializable() -> None:
    import yaml  # to_dict は YAML にそのまま落ちる（正本→ビュー/保存の写像）。

    d = eda.profile(_frame()).to_dict()
    assert list(d) == [
        "n_rows",
        "n_columns",
        "columns",
        "numeric",
        "categorical",
        "duplicate_rows",
        "datetime",
        "flags",
    ]
    text = yaml.safe_dump(d, allow_unicode=True)  # 例外なく文字列化できる（polars 値が素の Python になっている）
    assert "n_rows" in text


def test_target_summary_classification_ratios() -> None:
    df = pl.DataFrame({"y": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1]})  # 0×6・1×4
    s = eda.target_summary(df, target="y", task="classification")
    assert s["task"] == "classification"
    assert s["counts"] == {0: 6, 1: 4}
    assert s["ratios"] == {0: pytest.approx(0.6), 1: pytest.approx(0.4)}


def test_target_summary_regression_stats() -> None:
    df = pl.DataFrame({"t": [0.0, 2.0, 4.0, 6.0, 8.0]})
    s = eda.target_summary(df, target="t", task="regression")
    assert s["task"] == "regression"
    assert s["mean"] == pytest.approx(4.0)
    assert s["min"] == pytest.approx(0.0)
    assert s["max"] == pytest.approx(8.0)


def test_target_summary_missing_column_errors() -> None:
    with pytest.raises(ValueError, match="目的変数|列"):
        eda.target_summary(pl.DataFrame({"a": [1]}), target="nope")


def test_profile_numeric_skew_and_iqr_outliers() -> None:
    # 対称な構成 → skew==0。[1..8]＋100 → 100 だけが Tukey の柵の外（n_outliers==1・比率 1/9）。
    df = pl.DataFrame({"v": [1.0, 2, 3, 4, 5, 6, 7, 8, 100]})
    num = {r["column"]: r for r in eda.profile(df).numeric.to_dicts()}
    sym = {r["column"]: r for r in eda.profile(pl.DataFrame({"s": [1.0, 2, 3]})).numeric.to_dicts()}
    assert sym["s"]["skew"] == pytest.approx(0.0)
    assert num["v"]["n_outliers"] == 1
    assert num["v"]["outlier_ratio"] == pytest.approx(1 / 9)


def test_profile_flags() -> None:
    df = pl.DataFrame(
        {
            "const": [5] * 100,  # constant
            "quasi": [1] + [0] * 99,  # 最頻値 0.99 → quasi_constant
            "idcol": list(range(100)),  # 一意数=行数の Int → id_like
            "allnull": [None] * 100,  # all_null
            "ok": list(range(50)) * 2,  # 健全（フラグなし）
        }
    )
    flags = {(r["column"], r["flag"]) for r in eda.profile(df).flags.to_dicts()}
    assert ("const", "constant") in flags
    assert ("quasi", "quasi_constant") in flags
    assert ("idcol", "id_like") in flags
    assert ("allnull", "all_null") in flags
    assert not any(c == "ok" for c, _ in flags)  # 健全な列はフラグに出ない


def test_profile_datetime() -> None:
    import datetime as dt

    df = pl.DataFrame({"d": [dt.date(2020, 1, 1), dt.date(2020, 1, 3)], "n": [1, 2]})
    dts = {r["column"]: r for r in eda.profile(df).datetime.to_dicts()}
    assert "d" in dts and dts["d"]["n_unique"] == 2
    assert "2020-01-01" in dts["d"]["min"] and "2020-01-03" in dts["d"]["max"]
    # 日時列なし → 0 行（落ちない）。
    assert eda.profile(pl.DataFrame({"n": [1, 2]})).datetime.height == 0


def test_missing_patterns() -> None:
    # {x,y} 同時欠損 3 行・z 単独欠損 2 行・欠損なし 5 行。
    df = pl.DataFrame(
        {
            "x": [None, None, None, 1, 1, 1, 1, 1, 1, 1],
            "y": [None, None, None, 2, 2, 2, 2, 2, 2, 2],
            "z": [1, 1, 1, None, None, 3, 3, 3, 3, 3],
        }
    )
    pats = eda.missing_patterns(df)
    by_cols = {tuple(r["columns"]): r["count"] for r in pats.to_dicts()}
    assert by_cols[()] == 5  # 欠損なしが最多
    assert by_cols[("x", "y")] == 3
    assert by_cols[("z",)] == 2


def test_missing_patterns_deterministic_order_and_top() -> None:
    # 構成：欠損なし 3 行・a 単独 2 行・b 単独 2 行。count 降順・同数（a と b）は欠損列名の辞書順で決定的。
    df = pl.DataFrame(
        {
            "a": [1, 1, 1, None, None, 4, 5],
            "b": [1, 2, 3, 4, 5, None, None],
        }
    )
    rows = eda.missing_patterns(df).to_dicts()
    assert [tuple(r["columns"]) for r in rows] == [(), ("a",), ("b",)]
    assert [r["count"] for r in rows] == [3, 2, 2]
    assert rows[0]["ratio"] == pytest.approx(3 / 7)
    assert rows[1]["ratio"] == pytest.approx(2 / 7)
    # top は count 降順の上位だけに絞る。
    top1 = eda.missing_patterns(df, top=1).to_dicts()
    assert len(top1) == 1 and tuple(top1[0]["columns"]) == ()


def test_high_correlation_pairs_from_matrix_construction() -> None:
    # b=2a（r=1）・d=-a（r=-1）・c は中心化すると a/b/d と直交（r=0）。しきい値 0.99 で 3 ペアだけ。
    df = pl.DataFrame(
        {
            "a": [1.0, 2.0, 3.0, 4.0],
            "b": [2.0, 4.0, 6.0, 8.0],
            "c": [1.0, -1.0, -1.0, 1.0],
            "d": [-1.0, -2.0, -3.0, -4.0],
        }
    )
    rows = eda.high_correlation_pairs(df, threshold=0.99).to_dicts()
    # |r| が同値（すべて 1.0）のときは (a, b) の昇順＝決定的な整列。
    assert [(r["a"], r["b"]) for r in rows] == [("a", "b"), ("a", "d"), ("b", "d")]
    by_pair = {(r["a"], r["b"]): r["correlation"] for r in rows}
    assert by_pair[("a", "b")] == pytest.approx(1.0)
    assert by_pair[("a", "d")] == pytest.approx(-1.0)
    assert by_pair[("b", "d")] == pytest.approx(-1.0)


def test_high_correlation_pairs_large_offset_no_catastrophic_cancellation() -> None:
    # a = 標準正規 + 1e9・b = 2a（完全な比例関係 → r=1 は構成から自明・ハードコード期待値でない）。
    # 相関を「先に中心化せず」平方和で計算すると 1e9 の桁で有効数字が飛び（桁落ち）、
    # 分散が 0 と誤判定されて r=0.0＝検出漏れになる。中心化してあれば r=1.0 で検出できる。
    rng = np.random.default_rng(0)
    base = rng.standard_normal(50)
    df = pl.DataFrame({"a": base + 1e9, "b": 2.0 * (base + 1e9)})
    rows = eda.high_correlation_pairs(df, threshold=0.99).to_dicts()
    assert [(r["a"], r["b"]) for r in rows] == [("a", "b")]
    assert rows[0]["correlation"] == pytest.approx(1.0)


def test_high_correlation_pairs_constant_column_never_flagged() -> None:
    # 定数列は分散 0 で相関が定義できない → 0.0 扱い（NaN を混ぜない）＝どのペアにも出ない。
    df = pl.DataFrame({"k": [7.0, 7.0, 7.0, 7.0], "a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 4.0, 6.0, 8.0]})
    rows = eda.high_correlation_pairs(df, threshold=0.5).to_dicts()
    assert [(r["a"], r["b"]) for r in rows] == [("a", "b")]


def test_duplicate_columns() -> None:
    df = pl.DataFrame(
        {
            "a": [1, 2, None, 4],
            "b": [1, 2, None, 4],  # a と完全一致（null 位置も同じ）
            "c": [1, 2, 3, None],  # null 位置が違う
        }
    )
    dups = [(r["column"], r["duplicate_of"]) for r in eda.duplicate_columns(df).to_dicts()]
    assert dups == [("b", "a")]  # c は重複でない


def test_duplicate_columns_groups_and_order() -> None:
    # b=a・y=x・z=x（重複 2 組）。perm は a と同じ値の並べ替え（位置が違う）→ 重複でない。
    df = pl.DataFrame(
        {
            "a": [1, 2, 3, 4],
            "b": [1, 2, 3, 4],
            "perm": [4, 3, 2, 1],
            "x": ["u", "v", None, "w"],
            "y": ["u", "v", None, "w"],
            "z": ["u", "v", None, "w"],
        }
    )
    dups = [(r["column"], r["duplicate_of"]) for r in eda.duplicate_columns(df).to_dicts()]
    assert dups == [("b", "a"), ("y", "x"), ("z", "x")]  # 出力は df の列順＝決定的・duplicate_of は先に現れた列


def test_category_target_summary() -> None:
    # A は目的が全 1・B は全 0 → target_mean が 1.0 / 0.0。
    df = pl.DataFrame({"cat": ["A", "A", "A", "B", "B"], "y": [1, 1, 1, 0, 0]})
    rows = {r["value"]: r for r in eda.category_target_summary(df, target="y").to_dicts()}
    assert rows["A"]["target_mean"] == pytest.approx(1.0)
    assert rows["B"]["target_mean"] == pytest.approx(0.0)
    assert rows["A"]["count"] == 3


def test_compare_ks_wasserstein_identical_is_zero() -> None:
    # 同一分布なら KS 統計量も Wasserstein 距離も 0（構成から自明）。psi 列も従来どおり残る。
    train = pl.DataFrame({"n": [float(i) for i in range(100)]})
    row = eda.compare(train, train).numeric.to_dicts()[0]
    assert row["ks"] == pytest.approx(0.0)
    assert row["wasserstein"] == pytest.approx(0.0)
    assert row["psi"] == pytest.approx(0.0, abs=1e-9)  # 既存列は不変


def test_compare_ks_wasserstein_shift_monotone() -> None:
    # 平行移動 d の Wasserstein 距離は d に一致（輸送距離の定義から）。KS は移動が大きいほど単調増で、
    # 分布の台が完全に離れれば 1.0（経験分布関数の最大差＝全質量）。
    base = [i / 10 for i in range(100)]  # [0, 9.9] の一様格子
    train = pl.DataFrame({"n": base})
    small = eda.compare(train, pl.DataFrame({"n": [v + 1.0 for v in base]})).numeric.to_dicts()[0]
    large = eda.compare(train, pl.DataFrame({"n": [v + 100.0 for v in base]})).numeric.to_dicts()[0]
    assert small["wasserstein"] == pytest.approx(1.0)
    assert large["wasserstein"] == pytest.approx(100.0)
    assert large["ks"] == pytest.approx(1.0)  # 台が離れる＝完全に見分く
    assert small["ks"] < large["ks"]  # 移動量で単調増


def test_compare_ks_wasserstein_all_null_side_is_none() -> None:
    # 片側が全欠損＝分布距離を計算できない → None（mean_gap と同じ「測れない」の規約。0.0＝同一と混同しない）。
    train = pl.DataFrame({"n": [1.0, 2.0, 3.0]})
    test = pl.DataFrame({"n": pl.Series([None, None, None], dtype=pl.Float64)})
    row = eda.compare(train, test).numeric.to_dicts()[0]
    assert row["ks"] is None
    assert row["wasserstein"] is None


def test_mutual_information_nonlinear_dependence() -> None:
    # y = x²（x は 0 対称の一様）→ 線形相関はほぼ 0 だが MI は正（非線形依存が見える）。独立な noise は MI ≈ 0。
    rng = np.random.default_rng(0)
    x = rng.uniform(-1.0, 1.0, 400)
    noise = rng.uniform(-1.0, 1.0, 400)
    df = pl.DataFrame({"x": x, "noise": noise, "y": x**2})
    corr = {r["feature"]: r["correlation"] for r in eda.correlations(df, target="y").to_dicts()}
    assert abs(corr["x"]) < 0.2  # 線形相関では依存が見えない構成
    mi = {r["feature"]: r["mi"] for r in eda.mutual_information(df, target="y", task="regression", seed=0).to_dicts()}
    assert mi["x"] > 0.3  # 決定的な関数関係＝大きな MI
    assert mi["noise"] < 0.1  # 独立＝ほぼ 0
    assert mi["x"] > mi["noise"]


def test_mutual_information_classification_and_order() -> None:
    # y = 1(x>0) は x から完全に決まる → MI は y のエントロピー（ln2≈0.693）近くまで届く。独立な noise は低い。
    rng = np.random.default_rng(2)
    x = rng.normal(size=300)
    noise = rng.normal(size=300)
    df = pl.DataFrame({"x": x, "noise": noise, "y": (x > 0).astype(np.int64)})
    out = eda.mutual_information(df, target="y", task="classification", seed=0)
    mi = {r["feature"]: r["mi"] for r in out.to_dicts()}
    assert mi["x"] > 0.3
    assert mi["x"] > mi["noise"]
    assert out["feature"].to_list()[0] == "x"  # mi 降順＝効く列が先頭
    assert "y" not in mi  # 目的変数自身は出ない


def test_mutual_information_deterministic_and_constant_zero() -> None:
    # 同じ seed なら 2 回呼んで完全一致（決定的）。定数列は依存が定義できない → 0.0。
    rng = np.random.default_rng(1)
    df = pl.DataFrame({"x": rng.normal(size=100), "c": [3.0] * 100, "y": rng.normal(size=100)})
    a = eda.mutual_information(df, target="y", task="regression", seed=7)
    b = eda.mutual_information(df, target="y", task="regression", seed=7)
    assert a.to_dicts() == b.to_dicts()
    assert {r["feature"]: r["mi"] for r in a.to_dicts()}["c"] == 0.0


def test_mutual_information_missing_target_errors() -> None:
    with pytest.raises(ValueError, match="目的変数|列"):
        eda.mutual_information(pl.DataFrame({"a": [1.0]}), target="nope", task="regression", seed=0)


def test_leakage_scan_flags_suspects_with_reasons() -> None:
    # 仕込み：y のコピー（float・r=1）・y を完全に決めるカテゴリ・id 列・y と内容一致の列。無害列は挙がらない。
    rng = np.random.default_rng(0)
    y = np.array([0, 1] * 50, dtype=np.int64)
    df = pl.DataFrame(
        {
            "y_copy": y.astype(np.float64),  # 目的変数のコピー → high_correlation（r=1.0）
            "pinned": np.where(y == 1, "P", "N"),  # カテゴリの target_mean が 0/1 に張り付く
            "idcol": np.arange(100),  # 一意数=行数の整数 → id_like
            "dup": y,  # 目的変数と内容一致（duplicate_columns では後に現れる y 側が column になる向き）
            "ok_num": rng.normal(size=100),  # 無害な数値
            "ok_cat": rng.choice(["a", "b", "c"], size=100),  # 無害なカテゴリ（各カテゴリの目的率 ≈ 0.5）
            "y": y,
        }
    )
    scan = eda.leakage_scan(df, target="y")
    reasons = {(r["column"], r["reason"]) for r in scan.to_dicts()}
    assert ("y_copy", "high_correlation") in reasons
    assert ("pinned", "category_target_pinned") in reasons
    assert ("idcol", "id_like") in reasons
    assert ("dup", "duplicate_of_target") in reasons
    flagged = {c for c, _ in reasons}
    assert "ok_num" not in flagged and "ok_cat" not in flagged  # 無害な列は挙がらない
    assert "y" not in flagged  # 目的変数自身は挙がらない


def test_leakage_scan_multiple_target_copies_all_flagged() -> None:
    # 目的変数のコピーが 2 列（s1, s2 とも target より前）。duplicate_columns は代表 1 本に畳むので
    # 素朴に (column, duplicate_of) を突き合わせると s1 しか挙がらない（推移律漏れ）。文字列 target なので
    # high_correlation でも救われない → duplicate グループの推移解決で s1・s2 の両方が挙がる必要がある。
    labels = np.array(["a", "b"] * 50)
    df = pl.DataFrame({"s1": labels, "s2": labels, "y": labels})
    reasons = {(r["column"], r["reason"]) for r in eda.leakage_scan(df, target="y", task="classification").to_dicts()}
    assert ("s1", "duplicate_of_target") in reasons
    assert ("s2", "duplicate_of_target") in reasons  # 2 つ目のコピーも漏らさない


def test_leakage_scan_string_classification_target_mutual_information() -> None:
    # 文字列ラベルの分類 target。leaker は target を完全に決める数値列（"dog"→1.0/"cat"→0.0）＝MI≈ln2。
    # high_correlation・pinned は数値 target 限定なので効かない。high_mutual_information（任意 target 型）で拾う。
    rng = np.random.default_rng(4)
    labels = np.array(["cat", "dog"] * 50)
    df = pl.DataFrame(
        {
            "leaker": (labels == "dog").astype(np.float64),  # target を完全に決める → MI 大
            "noise": rng.normal(size=100),  # 独立 → MI≈0
            "y": labels,
        }
    )
    scan = eda.leakage_scan(df, target="y", task="classification")
    reasons = {(r["column"], r["reason"]) for r in scan.to_dicts()}
    assert ("leaker", "high_mutual_information") in reasons
    assert "noise" not in {c for c, _ in reasons}  # 無害な独立列は挙がらない


def test_leakage_scan_clean_data_is_empty() -> None:
    # 独立な特徴だけ＝疑い列なし → 0 行。数え上げ 1 件だけのカテゴリ（target_mean が自明に 0/1）は根拠にしない。
    rng = np.random.default_rng(3)
    df = pl.DataFrame({"x": rng.normal(size=50), "y": (rng.normal(size=50) > 0).astype(np.int64)})
    assert eda.leakage_scan(df, target="y").height == 0


def test_leakage_scan_missing_target_errors() -> None:
    with pytest.raises(ValueError, match="目的変数|列"):
        eda.leakage_scan(pl.DataFrame({"a": [1]}), target="nope")


def test_notebook_is_thin_view() -> None:
    # marimo ビューは harness.ds の関数を呼ぶだけ（数値ロジックを持たない）の機械的近似：
    # eda を import している・sklearn を直接 import していない（正本＝src・ビューは薄い・DESIGN §4 判断1）。
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "notebooks" / "eda.py").read_text(encoding="utf-8")
    assert "from harness.ds import" in src and "eda" in src
    assert "sklearn" not in src  # 指標・学習のロジックはビューに書かない（正本の関数へ委譲）


def test_cli_profile_outputs_yaml(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # data profile は store.load 経由でテーブルを読み、YAML を出す（store をふさいで配線だけ確かめる）。
    import yaml

    from harness.ds import cli, store

    monkeypatch.setattr(store, "load", lambda root, table_id: pl.DataFrame({"y": [0, 0, 1]}))
    cli._data_profile("some_table", target="y", task="classification")
    out = yaml.safe_load(capsys.readouterr().out)
    assert out["table"] == "some_table"
    assert out["profile"]["n_rows"] == 3
    assert out["target"]["counts"] == {0: 2, 1: 1}  # 目的変数の要約も出る
