"""テーブル定義（メタデータ）の正本 YAML を読み、静的検査と実データ検証を組み立てる。

- 正本は宣言的な YAML。共有は `docs/data/<id>.yaml`、実験スコープは `work/<単位ID>/data/<id>.yaml`。
- 検証の実行器は正本から導出する（列の型・NULL可否・一意・取りうる値・範囲を polars で確かめる）。
  より本格的な検証が要る案件は、同じ正本から pandera 等を組み立てて差し替えられる（実行器は導出物）。
- polars は実データを扱う save/load/validate でだけ使う（遅延取り込み）。静的検査は polars 無しで動く。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness.config import load_config
from harness.pm import Problem

# polars の型名（この集合以外は data-lint が失敗にする）。
POLARS_DTYPES = {
    "Int8", "Int16", "Int32", "Int64",
    "UInt8", "UInt16", "UInt32", "UInt64",
    "Float32", "Float64", "Boolean", "String",
    "Date", "Datetime", "Time", "Duration",
}  # fmt: skip


class Layer(Enum):
    """データの層。分ける基準は保存の規律の違い。

    StrEnum ではなく素の Enum にする（メンバー名 split が str.split と衝突するため）。値は文字列。
    """

    raw = "raw"
    processed = "processed"
    split = "split"


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    dtype: str  # polars の型名
    nullable: bool = True
    unique: bool = False
    description: str | None = None
    unit: str | None = None
    allowed_values: list[Any] | None = None
    range: dict[str, float] | None = None  # {"min": .., "max": ..}
    checks: list[str] = Field(default_factory=list)


class Lineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: list[str] = Field(default_factory=list)  # 入力テーブルのID
    code: str | None = None  # 変換関数の参照
    work: str | None = None  # 作業単位のID
    method: str | None = None  # split の分割方法


class TableSchema(BaseModel):
    """1 テーブルの定義（正本 YAML）。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    layer: Layer
    scope: str = "project"  # project または作業単位ID
    role: str | None = None  # cleaned / feature / prediction / evaluation …（人が探すための分類）
    source: str | None = None  # raw の出所
    primary_key: list[str] = Field(default_factory=list)
    relations: list[dict[str, str]] = Field(default_factory=list)
    lineage: Lineage | None = None
    partition_by: list[str] = Field(default_factory=list)
    columns: list[Column]
    checks: list[str] = Field(default_factory=list)


def _project_dir(root: Path) -> Path:
    """共有スコープのテーブル定義の置き場（config の metadata.uri。ローカルのみ）。"""
    uri = load_config(root).metadata.uri
    return root / uri[len("file:") :] if uri.startswith("file:") else root / "docs" / "data"


def load_schemas(root: Path, problems: list[Problem] | None = None) -> list[TableSchema]:
    """共有（docs/data）と実験スコープ（work/**/data）のテーブル定義をすべて読む。"""
    paths: list[Path] = []
    pdir = _project_dir(root)
    if pdir.is_dir():
        paths.extend(sorted(pdir.glob("*.yaml")))
    work = root / "work"
    if work.is_dir():
        paths.extend(sorted(work.glob("**/data/*.yaml")))
    out: list[TableSchema] = []
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            out.append(TableSchema.model_validate(raw))
        except ValidationError as exc:
            if problems is not None:
                problems.append(Problem("error", f"{path.name}: テーブル定義が不正: {exc.error_count()} 件"))
    return out


def data_lint(root: Path) -> list[Problem]:
    """テーブル定義の静的検査（実データは見ない）。ID重複・型名・系譜・越境参照などを見る。"""
    problems: list[Problem] = []
    schemas = load_schemas(root, problems)
    by_id: dict[str, TableSchema] = {}
    for s in schemas:
        if s.id in by_id:
            problems.append(Problem("error", f"{s.id}: テーブルIDが重複している"))
        by_id[s.id] = s

    for s in schemas:
        col_names = {c.name for c in s.columns}
        for c in s.columns:
            if c.dtype not in POLARS_DTYPES:
                problems.append(Problem("error", f"{s.id}.{c.name}: 型 '{c.dtype}' は polars の型名でない"))
        for key in s.primary_key:
            if key not in col_names:
                problems.append(Problem("error", f"{s.id}: primary_key の '{key}' が列に無い"))
        if s.layer in (Layer.processed, Layer.split) and s.lineage is None:
            problems.append(Problem("error", f"{s.id}: {s.layer.value} だが lineage が無い"))
        if s.layer is Layer.raw and s.source is None:
            problems.append(Problem("info", f"{s.id}: raw だが source（出所）が無い"))
        if s.lineage is not None:
            for inp in s.lineage.inputs:
                dep = by_id.get(inp)
                if dep is None:
                    problems.append(Problem("error", f"{s.id}: lineage の入力 '{inp}' が見つからない"))
                elif dep.scope != "project" and dep.scope != s.scope:
                    problems.append(
                        Problem("error", f"{s.id}: 越境参照（scope {s.scope} が {inp} の scope {dep.scope} を参照）")
                    )
    return problems


def validate(df: Any, schema: TableSchema) -> list[str]:  # noqa: ANN401  df は polars.DataFrame
    """実データ（polars DataFrame）を定義に照らして確かめる。違反のメッセージを返す（空＝合格）。"""
    errs: list[str] = []
    present = set(df.columns)
    for col in schema.columns:
        if col.name not in present:
            errs.append(f"列 {col.name} が無い")
            continue
        series = df[col.name]
        if str(series.dtype) != col.dtype:
            errs.append(f"{col.name} の型が {series.dtype}（定義は {col.dtype}）")
        if not col.nullable and series.null_count() > 0:
            errs.append(f"{col.name} に NULL がある（nullable=false）")
        if col.unique and series.n_unique() != series.len():
            errs.append(f"{col.name} が一意でない（unique=true）")
        if col.allowed_values is not None:
            bad = set(series.drop_nulls().to_list()) - set(col.allowed_values)
            if bad:
                errs.append(f"{col.name} に許可外の値 {sorted(bad)}")
        if col.range is not None and series.drop_nulls().len() > 0:
            if "min" in col.range and series.min() < col.range["min"]:
                errs.append(f"{col.name} が下限 {col.range['min']} を下回る")
            if "max" in col.range and series.max() > col.range["max"]:
                errs.append(f"{col.name} が上限 {col.range['max']} を超える")
    return errs
