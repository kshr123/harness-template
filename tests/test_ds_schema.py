"""テーブル定義の静的検査・実データ検証・保存の入口のテスト。"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from harness.ds import data, schema, store

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
