"""データ実体の保存と読み込み（ローカルbackend）。保存＝検証済みだけ。

save(df, table_id) が定義に照らして検証し、通ったデータだけを parquet に書き、マニフェスト
（指紋・入力・コード・作業単位）を残す。物理位置は config の保存先URIとテーブルの層・scope から解決する。
S3・DWH のアダプタは後続で足す（この段階はローカルのみ。インターフェースは固定）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from harness.config import load_config
from harness.ds import schema as sch


def _local_base(root: Path, layer: str) -> Path:
    uri = load_config(root).data.uri_for(layer)
    if not uri.startswith("file:"):
        raise NotImplementedError(f"保存先 '{uri}' は未対応（この段階はローカルのみ）")
    return root / uri[len("file:") :]


def _resolve(root: Path, s: sch.TableSchema) -> Path:
    base = _local_base(root, s.layer.value)
    if s.scope == "project":
        return base / s.layer.value / f"{s.id}.parquet"
    return base / "work" / s.scope / s.layer.value / f"{s.id}.parquet"


def _schema_for(root: Path, table_id: str) -> sch.TableSchema:
    for s in sch.load_schemas(root):
        if s.id == table_id:
            return s
    raise ValueError(f"テーブル定義 {table_id} が見つからない（docs/data か work/*/data に置く）")


def save(root: Path, df: Any, table_id: str, *, code: str | None = None, work: str | None = None) -> str:  # noqa: ANN401
    """検証してから保存する。定義を満たさないデータは保存できない。指紋を返す。"""
    s = _schema_for(root, table_id)
    errs = sch.validate(df, s)
    if errs:
        raise ValueError(f"{table_id}: 検証に失敗: " + "；".join(errs))
    path = _resolve(root, s)
    if s.layer is sch.Layer.split and path.exists():
        raise ValueError(f"{table_id}: split 層は同じIDへの再書き込みを許さない（分割を切り直さない）")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.write_parquet(tmp)  # 完全に書いてから名前を付け替える（部分書き込みの防止）
    tmp.replace(path)
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "table_id": table_id,
        "layer": s.layer.value,
        "scope": s.scope,
        "fingerprint": fingerprint,
        "code": code,
        "work": work,
        "inputs": s.lineage.inputs if s.lineage else [],
    }
    (path.parent / f"{s.id}.manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
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
    return str(yaml.safe_load(manifest.read_text(encoding="utf-8"))["fingerprint"])
