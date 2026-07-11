"""データ実体の保存と読み込み（ローカルbackend）。保存＝検証済みだけ。

save(df, table_id) が定義に照らして検証し、通ったデータだけを parquet に書き、マニフェスト
（指紋・入力・コード・作業単位）を残す。物理位置は config の保存先URIとテーブルの層・scope から解決する。
保存の仕組み（URI解決・原子的書き込み・指紋・manifest）は harness.storage を使い、
このモジュールは方針（検証・split 層の再書き込み拒否・未保存なら None）だけを持つ。
S3・DWH のアダプタは後続で足す（この段階はローカルのみ。インターフェースは固定）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness import storage
from harness.config import load_config
from harness.ds import schema as sch


def _resolve(root: Path, s: sch.TableSchema) -> Path:
    base = storage.resolve_uri(root, load_config(root).data.uri_for(s.layer.value))
    if s.scope == "project":
        return base / s.layer.value / f"{s.id}.parquet"
    return base / "work" / s.scope / s.layer.value / f"{s.id}.parquet"


def _schema_for(root: Path, table_id: str) -> sch.TableSchema:
    for s in sch.load_schemas(root):
        if s.id == table_id:
            return s
    raise ValueError(f"テーブル定義 {table_id} が見つからない（docs/data か work/*/data に置く）")


def save(root: Path, df: Any, table_id: str, *, code: str | None = None, work: str | None = None) -> str:  # noqa: ANN401
    """検証してから保存する。定義を満たさないデータは保存できない。指紋を返す。

    全テーブル定義を渡して検証する（sch.validate の all_schemas）＝role="feature" のテーブルは、他テーブルが
    宣言した目的変数・ID 列（target_column／primary_key）の同乗を ValueError で止める（T-0205）。
    """
    all_schemas = sch.load_schemas(root)
    matches = [x for x in all_schemas if x.id == table_id]
    if not matches:
        raise ValueError(f"テーブル定義 {table_id} が見つからない（docs/data か work/*/data に置く）")
    s = matches[0]
    errs = sch.validate(df, s, all_schemas=all_schemas)
    if errs:
        raise ValueError(f"{table_id}: 検証に失敗: " + "；".join(errs))
    path = _resolve(root, s)
    if s.layer is sch.Layer.split and path.exists():
        raise ValueError(f"{table_id}: split 層は同じIDへの再書き込みを許さない（分割を切り直さない）")
    path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = storage.atomic_write(path, df.write_parquet)
    manifest = {
        "table_id": table_id,
        "layer": s.layer.value,
        "scope": s.scope,
        "fingerprint": fingerprint,
        "code": code,
        "work": work,
        "inputs": s.lineage.inputs if s.lineage else [],
    }
    # manifest は実体の後に書く（存在＝保存完了の印）。
    storage.write_manifest(path.parent / f"{s.id}.manifest.yaml", manifest)
    return fingerprint


def load(root: Path, table_id: str) -> Any:  # noqa: ANN401  polars.DataFrame を返す
    """管理下のテーブルを読む（場所は設定が解決する。URIは書かせない）。"""
    import polars as pl

    s = _schema_for(root, table_id)
    path = _resolve(root, s)
    if not path.is_file():
        raise FileNotFoundError(f"{table_id} の実体が無い（先に save する）: {path}")
    return pl.read_parquet(path)


def fingerprint_of(root: Path, table_id: str) -> str | None:
    """保存済みテーブルの指紋（manifest の値）。未保存なら None。

    split 層の「再保存拒否」と実験スクリプトの再実行を両立させるための照会口
    （在れば load して同一性を確かめ、指紋は再保存せずにこれで引く）。
    """
    s = _schema_for(root, table_id)
    manifest = _resolve(root, s).parent / f"{s.id}.manifest.yaml"
    if not manifest.is_file():
        return None
    return str(storage.read_manifest(manifest)["fingerprint"])
