"""EDA の構造化レポートのテスト：期待値はデータ構成から導出する（金メッキ禁止）。

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


def test_psi_identical_is_zero() -> None:
    s = pl.Series("v", [float(i) for i in range(100)])
    assert eda.psi(s, s) == pytest.approx(0.0, abs=1e-9)  # 同一分布 → 0


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


def test_category_target_summary() -> None:
    # A は目的が全 1・B は全 0 → target_mean が 1.0 / 0.0。
    df = pl.DataFrame({"cat": ["A", "A", "A", "B", "B"], "y": [1, 1, 1, 0, 0]})
    rows = {r["value"]: r for r in eda.category_target_summary(df, target="y").to_dicts()}
    assert rows["A"]["target_mean"] == pytest.approx(1.0)
    assert rows["B"]["target_mean"] == pytest.approx(0.0)
    assert rows["A"]["count"] == 3


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

    from harness import cli
    from harness.ds import store

    monkeypatch.setattr(store, "load", lambda root, table_id: pl.DataFrame({"y": [0, 0, 1]}))
    cli._data_profile("some_table", target="y", task="classification")
    out = yaml.safe_load(capsys.readouterr().out)
    assert out["table"] == "some_table"
    assert out["profile"]["n_rows"] == 3
    assert out["target"]["counts"] == {0: 2, 1: 1}  # 目的変数の要約も出る
