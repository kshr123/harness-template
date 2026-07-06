"""テーブル定義の静的検査・実データ検証・保存の入口のテスト。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from harness.ds import data, schema, store

pytestmark = pytest.mark.unit

SYNTHETIC = """id: synthetic
description: 合成データ
layer: raw
source: generate_synthetic
primary_key: [id]
columns:
  - {name: id, dtype: Int64, nullable: false, unique: true}
  - {name: x1, dtype: Float64, nullable: false}
  - {name: x2, dtype: Float64, nullable: false}
  - {name: y, dtype: Int64, nullable: false, allowed_values: [0, 1]}
"""


def _write(root: Path, name: str, content: str) -> None:
    d = root / "docs" / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(content, encoding="utf-8")


def test_data_lint_clean(tmp_path: Path) -> None:
    _write(tmp_path, "synthetic", SYNTHETIC)
    assert not [p for p in schema.data_lint(tmp_path) if p.level == "error"]


def test_data_lint_bad_dtype(tmp_path: Path) -> None:
    _write(tmp_path, "t", "id: t\ndescription: x\nlayer: raw\ncolumns:\n  - {name: a, dtype: Integer}\n")
    assert any("polars の型名でない" in p.message for p in schema.data_lint(tmp_path))


def test_data_lint_processed_needs_lineage(tmp_path: Path) -> None:
    _write(tmp_path, "t", "id: t\ndescription: x\nlayer: processed\ncolumns:\n  - {name: a, dtype: Int64}\n")
    assert any("lineage が無い" in p.message for p in schema.data_lint(tmp_path))


def test_data_lint_missing_input(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "t",
        "id: t\ndescription: x\nlayer: processed\nlineage: {inputs: [nope]}\ncolumns:\n  - {name: a, dtype: Int64}\n",
    )
    assert any("見つからない" in p.message for p in schema.data_lint(tmp_path))


def test_validate_accepts_generated_and_catches_violations(tmp_path: Path) -> None:
    _write(tmp_path, "synthetic", SYNTHETIC)
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["synthetic"]
    assert schema.validate(data.generate_synthetic(n=100, seed=0), s) == []
    bad = pl.DataFrame({"id": [1, 1], "x1": [0.0, 1.0], "x2": [0.0, 1.0], "y": [0, 2]})
    errs = schema.validate(bad, s)
    assert any("一意でない" in e for e in errs)
    assert any("許可外の値" in e for e in errs)


def test_validate_datetime_and_duration_dtypes(tmp_path: Path) -> None:
    """パラメタ付きの Datetime/Duration 列が、素の型名の宣言と一致すること（時系列の保存経路）。"""
    _write(
        tmp_path,
        "ts",
        "id: ts\ndescription: 時系列\nlayer: raw\ncolumns:\n"
        "  - {name: t, dtype: Datetime, nullable: false}\n"
        "  - {name: d, dtype: Duration, nullable: false}\n",
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["ts"]
    df = pl.DataFrame(
        {
            "t": [datetime(2026, 1, 1), datetime(2026, 1, 2)],
            "d": [timedelta(hours=1), timedelta(hours=2)],
        }
    )
    assert schema.validate(df, s) == []


def test_validate_nan_violates_nullable_false(tmp_path: Path) -> None:
    """NaN は null ではないが、nullable=false の float 列では違反として扱うこと。"""
    _write(
        tmp_path,
        "f",
        "id: f\ndescription: x\nlayer: raw\ncolumns:\n  - {name: v, dtype: Float64, nullable: false}\n",
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["f"]
    assert schema.validate(pl.DataFrame({"v": [1.0, float("nan")]}), s) != []
    assert schema.validate(pl.DataFrame({"v": [1.0, 2.0]}), s) == []


def test_validate_range_fires_even_with_nan(tmp_path: Path) -> None:
    """NaN が混ざっていても、範囲外の実値（2.0 > max 1.0）は違反になること。"""
    _write(
        tmp_path,
        "r",
        "id: r\ndescription: x\nlayer: raw\ncolumns:\n  - {name: v, dtype: Float64, range: {max: 1.0}}\n",
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["r"]
    errs = schema.validate(pl.DataFrame({"v": [float("nan"), 2.0]}), s)
    assert any("上限" in e for e in errs)


def test_validate_composite_primary_key(tmp_path: Path) -> None:
    """複合 primary_key の重複行は違反、組として一意なら合格すること。"""
    _write(
        tmp_path,
        "pk",
        "id: pk\ndescription: x\nlayer: raw\nprimary_key: [a, b]\ncolumns:\n"
        "  - {name: a, dtype: Int64}\n  - {name: b, dtype: Int64}\n",
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["pk"]
    ok = pl.DataFrame({"a": [1, 1, 2], "b": [1, 2, 1]})
    assert schema.validate(ok, s) == []
    dup = pl.DataFrame({"a": [1, 1, 2], "b": [2, 2, 1]})
    assert any("primary_key" in e for e in schema.validate(dup, s))


def test_validate_unique_allows_multiple_nulls(tmp_path: Path) -> None:
    """unique=true は非 NULL の中でだけ判定する（NULL が 2 つあっても合格）こと。"""
    _write(
        tmp_path,
        "u",
        "id: u\ndescription: x\nlayer: raw\ncolumns:\n  - {name: v, dtype: Int64, unique: true}\n",
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["u"]
    assert schema.validate(pl.DataFrame({"v": [1, 2, None, None]}), s) == []
    dup = pl.DataFrame({"v": [1, 1, None, None]})
    assert any("一意でない" in e for e in schema.validate(dup, s))


def test_validate_column_check_counts_violations(tmp_path: Path) -> None:
    """列の checks（SQL 式）が実際に評価され、違反行数（負の 2 行）が報告されること。"""
    _write(
        tmp_path,
        "c",
        'id: c\ndescription: x\nlayer: raw\ncolumns:\n  - {name: amount, dtype: Float64, checks: ["amount >= 0"]}\n',
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["c"]
    # 4 行のうち負が 2 行（-1.0 と -2.5）→ 違反は 2 行
    bad = pl.DataFrame({"amount": [10.0, -1.0, -2.5, 3.0]})
    errs = schema.validate(bad, s)
    assert any("check 'amount >= 0' に違反 2 行" in e for e in errs)
    # 全行が非負なら合格（従来どおり空リスト）
    assert schema.validate(pl.DataFrame({"amount": [0.0, 1.0]}), s) == []


def test_validate_table_check_cross_column(tmp_path: Path) -> None:
    """テーブルレベルの checks で列またぎの条件（amount >= fee）を確かめられること。"""
    _write(
        tmp_path,
        "tc",
        "id: tc\ndescription: x\nlayer: raw\n"
        'checks: ["amount >= fee"]\ncolumns:\n'
        "  - {name: amount, dtype: Float64}\n  - {name: fee, dtype: Float64}\n",
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["tc"]
    # 3 行のうち amount < fee が 2 行（1<3 と 2<5）→ 違反は 2 行
    bad = pl.DataFrame({"amount": [10.0, 1.0, 2.0], "fee": [0.0, 3.0, 5.0]})
    errs = schema.validate(bad, s)
    assert any("tc: check 'amount >= fee' に違反 2 行" in e for e in errs)
    ok = pl.DataFrame({"amount": [10.0, 3.0], "fee": [0.0, 3.0]})
    assert schema.validate(ok, s) == []


def test_validate_check_null_is_not_violation(tmp_path: Path) -> None:
    """checks の評価で NULL は違反に数えない（NULL 可否は nullable の責務）こと。"""
    _write(
        tmp_path,
        "n",
        'id: n\ndescription: x\nlayer: raw\ncolumns:\n  - {name: amount, dtype: Float64, checks: ["amount >= 0"]}\n',
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["n"]
    # NULL 1 行・負 1 行（-4.0）→ 違反は 1 行だけ（NULL は数えない）
    errs = schema.validate(pl.DataFrame({"amount": [1.0, None, -4.0]}), s)
    assert any("check 'amount >= 0' に違反 1 行" in e for e in errs)
    # NULL だけなら checks 違反は無い
    assert schema.validate(pl.DataFrame({"amount": [1.0, None]}), s) == []


def test_validate_check_invalid_expression_does_not_crash(tmp_path: Path) -> None:
    """式として不正な check・存在しない列を参照する check が、例外でなく違反メッセージになること。"""
    _write(
        tmp_path,
        "iv",
        "id: iv\ndescription: x\nlayer: raw\n"
        'checks: ["not a valid @@ expr", "nope > 0"]\ncolumns:\n'
        "  - {name: amount, dtype: Float64}\n",
    )
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["iv"]
    errs = schema.validate(pl.DataFrame({"amount": [1.0]}), s)
    assert any("'not a valid @@ expr' が式として不正" in e for e in errs)
    assert any("'nope > 0'" in e and ("が式として不正" in e or "が評価できない" in e) for e in errs)


def test_validate_empty_checks_behaves_as_before(tmp_path: Path) -> None:
    """checks を書かない定義（通常ケース）は従来どおり合格すること（退行ガード）。"""
    _write(tmp_path, "synthetic", SYNTHETIC)
    s = {x.id: x for x in schema.load_schemas(tmp_path)}["synthetic"]
    assert s.checks == [] and all(c.checks == [] for c in s.columns)
    assert schema.validate(data.generate_synthetic(n=100, seed=0), s) == []


def test_save_writes_validated_and_load_roundtrips(tmp_path: Path) -> None:
    _write(tmp_path, "synthetic", SYNTHETIC)
    df = data.generate_synthetic(n=50, seed=0)
    store.save(tmp_path, df, "synthetic")
    assert (tmp_path / "data" / "raw" / "synthetic.parquet").is_file()
    assert (tmp_path / "data" / "raw" / "synthetic.manifest.yaml").is_file()
    assert store.load(tmp_path, "synthetic").equals(df)


def test_save_rejects_invalid_data(tmp_path: Path) -> None:
    _write(tmp_path, "synthetic", SYNTHETIC)
    bad = pl.DataFrame({"id": [1, 1], "x1": [0.0, 0.0], "x2": [0.0, 0.0], "y": [0, 0]})
    with pytest.raises(ValueError):
        store.save(tmp_path, bad, "synthetic")


def test_split_layer_refuses_rewrite(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "sp",
        "id: sp\ndescription: 分割\nlayer: split\n"
        "lineage: {inputs: [], method: hash}\ncolumns:\n  - {name: id, dtype: Int64}\n",
    )
    df = pl.DataFrame({"id": [1, 2, 3]})
    store.save(tmp_path, df, "sp")
    with pytest.raises(ValueError):
        store.save(tmp_path, df, "sp")
