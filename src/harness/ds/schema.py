"""テーブル定義（メタデータ）の正本 YAML を読み、静的検査と実データ検証を組み立てる。

- 正本は宣言的な YAML。共有は `docs/data/<id>.yaml`、実験スコープは `work/<単位ID>/data/<id>.yaml`。
- 検証の実行器は正本から導出する（列の型・NULL可否・一意・取りうる値・範囲・checks（SQL 式）を polars で確かめる）。
  pandera は検討の上で不採用（DEC-0011）。YAML を正本のまま、checks は polars の sql_expr で
  ネイティブに評価する（新規依存ゼロ）。より本格的な検証が要る案件は差し替え可能（実行器は導出物）。
- polars は実データを扱う save/load/validate でだけ使う（遅延取り込み）。静的検査は polars 無しで動く。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness import storage
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
    """共有スコープのテーブル定義の置き場（config の metadata.uri をローカルパスに解決）。

    非 file: の URI は UnsupportedURIError で止める（store/models と同じ fail-loud）。
    以前は docs/data へ黙ってフォールバックしていたが、設定ミスを隠すため廃止した（T-0047）。
    """
    return storage.resolve_uri(root, load_config(root).metadata.uri)


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


def _eval_checks(df: Any, checks: list[str], *, where: str, errs: list[str]) -> None:  # noqa: ANN401
    """checks（SQL 式の文字列）を実データに対して評価し、違反を errs に積む。

    - 式は polars の sql_expr で評価する（pandera は検討の上で不採用＝DEC-0011。
      YAML を正本のまま、新規依存ゼロでネイティブに評価する）。
    - NULL は違反に数えない（NULL 可否は nullable の責務。式が NULL になった行は合格扱い）。
    - 不正な式・存在しない列の参照は、例外で落とさず違反メッセージにして続行する。
    """
    import polars as pl

    for check in checks:
        try:
            expr = pl.sql_expr(check)
        except Exception as exc:  # noqa: BLE001  polars の例外階層に依存しない（fail-loud はメッセージで）
            errs.append(f"{where}: check '{check}' が式として不正: {exc}")
            continue
        try:
            bad = df.filter(~expr.fill_null(True)).height
        except Exception as exc:  # noqa: BLE001  存在しない列の参照・非ブール式などは評価時に判明する
            errs.append(f"{where}: check '{check}' が評価できない: {exc}")
            continue
        if bad > 0:
            errs.append(f"{where}: check '{check}' に違反 {bad} 行")


def validate(df: Any, schema: TableSchema) -> list[str]:  # noqa: ANN401  df は polars.DataFrame
    """実データ（polars DataFrame）を定義に照らして確かめる。違反のメッセージを返す（空＝合格）。"""
    import polars as pl

    errs: list[str] = []
    present = set(df.columns)
    for col in schema.columns:
        if col.name not in present:
            errs.append(f"列 {col.name} が無い")
            continue
        series = df[col.name]
        # 文字列比較だとパラメタ付きの型（Datetime(time_unit=..) 等）が素の宣言名と一致しない。
        # polars の型として構造的に比べる（クラス vs インスタンスの同値判定がパラメタを吸収する）。
        expected = getattr(pl, col.dtype, None)
        if expected is None or series.dtype != expected:
            errs.append(f"{col.name} の型が {series.dtype}（定義は {col.dtype}）")
        is_float = series.dtype.is_float()
        if not col.nullable and series.null_count() > 0:
            errs.append(f"{col.name} に NULL がある（nullable=false）")
        # NaN は null ではないので null_count に載らない。nullable=false の float 列では違反にする。
        if not col.nullable and is_float and series.is_nan().any():
            errs.append(f"{col.name} に NaN がある（nullable=false）")
        if col.unique:
            # n_unique は null を 1 つの値として数えるため、null の個数で判定が変わる。非 NULL の中だけで見る。
            dn = series.drop_nulls()
            if dn.n_unique() != dn.len():
                errs.append(f"{col.name} が一意でない（unique=true）")
        if col.allowed_values is not None:
            bad = set(series.drop_nulls().to_list()) - set(col.allowed_values)
            if bad:
                errs.append(f"{col.name} に許可外の値 {sorted(bad)}")
        if col.range is not None:
            # NaN は min/max の比較をすり抜けるため、null に落としてから範囲を見る。
            vals = (series.fill_nan(None) if is_float else series).drop_nulls()
            if vals.len() > 0:
                if "min" in col.range and vals.min() < col.range["min"]:
                    errs.append(f"{col.name} が下限 {col.range['min']} を下回る")
                if "max" in col.range and vals.max() > col.range["max"]:
                    errs.append(f"{col.name} が上限 {col.range['max']} を超える")
    # 複合 primary_key は列ごとの unique では守れない。組としての重複をデータで確かめる。
    if schema.primary_key and all(k in present for k in schema.primary_key):
        if df.select(schema.primary_key).is_duplicated().any():
            errs.append(f"primary_key {schema.primary_key} が重複している")
    # checks（SQL 式）の評価。列の checks も df 全体に対して評価する（列またぎの式を書けるように）。
    for col in schema.columns:
        _eval_checks(df, col.checks, where=col.name, errs=errs)
    _eval_checks(df, schema.checks, where=schema.id, errs=errs)
    return errs
