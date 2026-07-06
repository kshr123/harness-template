"""保存の4作法（URI解決・原子的書き込み・sha256指紋・manifest）の共通部品（中核）。

store.py（データ）・models.py（学習済みモデル）・schema.py（テーブル定義の置き場）に
複製されていた仕組みをここへ1本化する。方針（何を検証するか・いつ拒否するか・manifest に
何を書くか）は呼び手が持ち、この部品は仕組みだけを提供する（policy-free）。
依存は stdlib＋yaml のみ（polars/sklearn を持ち込まない＝中核を汚さない）。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml


class UnsupportedURIError(NotImplementedError):
    """非 file: の URI。黙ったフォールバックはしない（保存先の取り違えを fail-loud で止める）。"""


def resolve_uri(root: Path, uri: str) -> Path:
    """'file:<相対パス>' を root 配下の実パスに解決する。他スキームは UnsupportedURIError。"""
    if not uri.startswith("file:"):
        raise UnsupportedURIError(f"保存先 '{uri}' は未対応（この段階はローカルのみ）")
    return root / uri[len("file:") :]


def fingerprint(path: Path) -> str:
    """ファイルの sha256 指紋。hashlib.file_digest でストリーム計算する（全読みしない）。"""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def atomic_write(path: Path, writer: Callable[[Path], None]) -> str:
    """writer に一時パスへ書かせ、完全に書けてから tmp→replace で確定する（部分書き込みの防止）。

    確定後のファイルの指紋（sha256）を返す。writer が例外を投げたら一時ファイルを消して再送出する。
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        writer(tmp)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    return fingerprint(path)


def write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    """manifest（YAML）を原子的に書く。実体の後に書く＝保存完了の印、は呼び手の作法。

    書式は従来と同一（yaml.safe_dump(allow_unicode=True, sort_keys=False)）＝既存ファイルとバイト一致。
    """

    def _write(tmp: Path) -> None:
        tmp.write_text(yaml.safe_dump(dict(manifest), allow_unicode=True, sort_keys=False), encoding="utf-8")

    atomic_write(path, _write)


def read_manifest(path: Path) -> dict[str, Any]:
    """manifest（YAML）を読んで dict で返す。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(data)


def verify_fingerprint(path: Path, expected: str) -> None:
    """指紋を照合し、不一致は ValueError（改変・破損した実体を読ませない）。"""
    actual = fingerprint(path)
    if actual != expected:
        raise ValueError(f"{path}: 指紋が一致しない（実体が改変・破損）")
