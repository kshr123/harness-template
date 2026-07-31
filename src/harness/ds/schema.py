"""テーブル定義（メタデータ）の正本 YAML を読み、静的検査と実データ検証を組み立てる。

- 正本は宣言的な YAML。共有は `docs/data/<id>.yaml`、実験スコープは `work/<単位ID>/data/<id>.yaml`、
  雛形提供は `templates/<雛形>/data/<id>.yaml`（雛形が持ち歩く schema。T-0141）。
- 検証の実行器は正本から導出する（列の型・NULL可否・一意・取りうる値・範囲・checks（SQL 式）を polars で確かめる）。
  pandera は検討の上で不採用。YAML を正本のまま、checks は polars の sql_expr で
  ネイティブに評価する（新規依存ゼロ）。より本格的な検証が要る案件は差し替え可能（実行器は導出物）。
- polars は実データを扱う save/load/validate でだけ使う（遅延取り込み）。静的検査は polars 無しで動く。
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from harness import storage
from harness.config import load_config
from harness.pm import Problem

# role（人が探すための分類）の既知語彙。自由記述ではなく閉じた集合にする。
# 目的変数の同乗（リーク）を止める安全検査を role の文字列一致に載せているため、綴り違い・亜種
# （"features"・"feature_store"）を許すと検査が黙って素通りする＝fail-open になる。既知語彙に
# 固定して未知 role を load 時に ValidationError で弾く＝構文で typo を不可能にする（保証(a)）。
# 新しい役割を使う案件は、この集合に 1 行足す（＝どこを直せばよいかが 1 か所に集まる）。
KNOWN_ROLES = frozenset({"raw", "cleaned", "feature", "split", "prediction", "evaluation"})

# polars の型名（この集合以外は TableSchema のバリデータが構築時に失敗にする＝(a) 構造で不可能にする）。
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

    @field_validator("dtype")
    @classmethod
    def _dtype_is_polars(cls, v: str) -> str:
        """dtype を polars の型名に固定する（構築時に弾く＝不正な型を持つスキーマを作れなくする）。"""
        if v not in POLARS_DTYPES:
            raise ValueError(f"型 '{v}' は polars の型名でない（既知: {sorted(POLARS_DTYPES)}）")
        return v


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
    target_column: str | None = None  # このテーブルが持つ目的変数の列名（宣言はラベルの出所側の 1 か所だけでする）

    @field_validator("role")
    @classmethod
    def _role_is_known(cls, v: str | None) -> str | None:
        """role を既知語彙に固定する（未知 role は typo/亜種の温床＝リーク検査の fail-open 源）。"""
        if v is not None and v not in KNOWN_ROLES:
            raise ValueError(f"role '{v}' は未知（既知: {sorted(KNOWN_ROLES)}）。新しい役割は KNOWN_ROLES に足す")
        return v

    @model_validator(mode="after")
    def _columns_consistent(self) -> TableSchema:
        """列との整合＝スキーマが**内部的に矛盾しない**ことを構築時に弾く（列に無い primary_key・target_column）。

        ここに置くのは「オブジェクトとして壊れている」規則だけ。派生層の lineage 必須は**リポの受け入れ方針**
        （well-formed なオブジェクトでも方針で拒む）なので data_lint に残す＝方針検査を構築ゲートに載せて
        store.save のような無関係な経路まで巻き込まない。スキーマ間の規則（ID 重複・lineage 参照・越境）も data_lint。
        """
        col_names = {c.name for c in self.columns}
        for key in self.primary_key:
            if key not in col_names:
                raise ValueError(f"primary_key の '{key}' が列に無い")
        if self.target_column is not None and self.target_column not in col_names:
            raise ValueError(f"target_column '{self.target_column}' が列に無い")
        return self


def _project_dir(root: Path) -> Path:
    """共有スコープのテーブル定義の置き場（config の metadata.uri をローカルパスに解決）。

    非 file: の URI は UnsupportedURIError で止める（store/models と同じ fail-loud）。
    以前は docs/data へ黙ってフォールバックしていたが、設定ミスを隠すため廃止した（T-0047）。
    """
    return storage.resolve_uri(root, load_config(root).metadata.uri)


def load_schemas(root: Path, problems: list[Problem] | None = None) -> list[TableSchema]:
    """共有（docs/data）・実験スコープ（work/**/data）・雛形提供（templates/**/data）のテーブル定義をすべて読む。"""
    paths: list[Path] = []
    pdir = _project_dir(root)
    if pdir.is_dir():
        paths.extend(sorted(pdir.glob("*.yaml")))
    work = root / "work"
    if work.is_dir():
        paths.extend(sorted(work.glob("**/data/*.yaml")))
    templates = root / "templates"
    if templates.is_dir():
        paths.extend(sorted(templates.glob("**/data/*.yaml")))
    out: list[TableSchema] = []
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            out.append(TableSchema.model_validate(raw))
        except ValidationError as exc:
            if problems is not None:
                # 各違反の具体的な理由をそのまま出す（「N 件」だけだと直す場所が分からない）。
                for err in exc.errors():
                    problems.append(Problem("error", f"{path.name}: テーブル定義が不正: {err['msg']}"))
    return out


def data_lint(root: Path) -> list[Problem]:
    """テーブル定義の静的検査（実データは見ない）。オブジェクトの well-formedness 以外を見る。

    単一スキーマの**内部矛盾**（型名・列に無い primary_key／target_column）は `TableSchema` の
    バリデータが構築時に弾き、`load_schemas` がそれを problems に載せる（(a) 構造で不可能にする）。
    ここに残すのは (1) リポの受け入れ方針（派生層は lineage 必須・raw の source）と、(2) 他スキーマを
    要する規則（ID 重複・lineage 参照先の実在・越境参照）＝どちらも「壊れたオブジェクト」ではないので構築ゲートに
    載せない。
    """
    problems: list[Problem] = []
    schemas = load_schemas(root, problems)
    by_id: dict[str, TableSchema] = {}
    for s in schemas:
        if s.id in by_id:
            problems.append(Problem("error", f"{s.id}: テーブルIDが重複している"))
        by_id[s.id] = s

    for s in schemas:
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

    - 式は polars の sql_expr で評価する（pandera は検討の上で不採用。
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


def declared_target_columns(schemas: list[TableSchema]) -> set[str]:
    """どこかのテーブルが target_column として宣言した目的変数の列名の集合（ラベルの出所側の宣言）。"""
    return {s.target_column for s in schemas if s.target_column is not None}


def forbidden_feature_columns(schemas: list[TableSchema], *, own_primary_key: Sequence[str] = ()) -> set[str]:
    """特徴量テーブル（role="feature"）に同乗してはいけない列名の集合。

    目的変数の同乗（リークの中でも最悪の形＝良い指標つきで出荷される）を発生源で塞ぐための集合作り。
    集合は「テーブル定義 YAML に宣言された名前」から機械的に導く（書く人の自己申告に依存しない）：
    - 目的変数の列名：どこかのテーブルが target_column として宣言した名前（ラベルの出所側の宣言 1 か所）。
    - ID 列名：どこかのテーブルが primary_key として宣言した名前（結合キーとして意図的に持つ列の名前）。
    own_primary_key（特徴量テーブル自身の primary_key）は除く：自分の結合キーとして持つのは正当な用途で、
    「同乗」（意図せず紛れ込む）ではない。
    """
    names: set[str] = set(declared_target_columns(schemas))
    for s in schemas:
        names.update(s.primary_key)
    return names - set(own_primary_key)


def validate(df: Any, schema: TableSchema, *, all_schemas: list[TableSchema] | None = None) -> list[str]:  # noqa: ANN401  df は polars.DataFrame
    """実データ（polars DataFrame）を定義に照らして確かめる。違反のメッセージを返す（空＝合格）。

    all_schemas を渡したとき、目的変数・ID 列（forbidden_feature_columns）が df に同乗していないかも確かめる
    （T-0205：発生源の封鎖。one-hot 等で動的に増える列があるため「宣言外の列を一律 error」にはできない＝
    有限に列挙できる集合だけを狙い撃ちする）。発火の条件は 2 つ：
    - role="feature"：目的変数・ID 列の両方を禁止列に（特徴量テーブルは X だけを持つべき）。
    - role 未設定の派生テーブル（processed/split）：目的変数だけを狙い撃ち（分類漏れでも最悪のリークは止める。
      ID 列は派生テーブルに正当に相乗りするので対象外）。自分自身が宣言した target_column は除く。

    塞げる fail-open と、塞げないもの（正直に書く）：role の既知語彙固定〔KNOWN_ROLES〕が typo・亜種を load 時に
    弾き、role 未設定の枝が「分類し忘れ」を拾う。ただし y を持ってよい既知 role（cleaned/split/raw 等）を
    **わざと**特徴量テーブルに付けた場合は、この検査を通り抜ける（既知 role は「この中身は意図的」という
    書き手の宣言＝role を分類の軸に据える設計上の限界。綴り違いではなく別語彙を選ぶ誤りまでは構文で防げない）。
    """
    import polars as pl

    errs: list[str] = []
    present = set(df.columns)
    if all_schemas is not None:
        if schema.role == "feature":
            forbidden = forbidden_feature_columns(all_schemas, own_primary_key=schema.primary_key)
            hint = "目的変数・ID 列は特徴量テーブル（role=feature）に含めない"
        elif schema.role is None and schema.layer in (Layer.processed, Layer.split):
            own_target = {schema.target_column} if schema.target_column else set()
            forbidden = declared_target_columns(all_schemas) - own_target
            hint = "未分類の派生テーブルに他テーブルの目的変数が同乗している。role か target_column を明示する"
        else:
            forbidden = set()
            hint = ""
        leaked = sorted(forbidden & present)
        if leaked:
            errs.append(f"禁止列 {leaked} が同乗している（{hint}。宣言は他テーブルの target_column / primary_key）")
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
