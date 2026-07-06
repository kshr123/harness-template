"""storage（保存の4作法の共通部品）のユニットテスト。

期待値はテストデータの構成から導出できるものだけ（sha256 は入力バイト列から計算・
manifest のバイト形式は yaml.safe_dump の引数から導出）。schema の fail-loud 化
（非 file: の metadata URI でフォールバックしない）もここで確かめる。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from harness import storage
from harness.ds import schema

pytestmark = pytest.mark.unit


def test_atomic_write_commits_and_returns_fingerprint(tmp_path: Path) -> None:
    """atomic_write は確定後のファイルの指紋を返す（＝fingerprint(path) と一致・入力から導出可）。"""
    path = tmp_path / "out.bin"

    def writer(tmp: Path) -> None:
        tmp.write_bytes(b"hello")

    fp = storage.atomic_write(path, writer)
    assert path.read_bytes() == b"hello"
    assert fp == storage.fingerprint(path)
    assert fp == hashlib.sha256(b"hello").hexdigest()  # 期待値は入力バイト列から導出
    assert list(tmp_path.iterdir()) == [path]  # 一時ファイルの残骸なし


def test_atomic_write_cleans_tmp_and_reraises_on_failure(tmp_path: Path) -> None:
    """writer が例外を投げたら、一時ファイルを消して同じ例外を再送出する（部分書き込みを残さない）。"""
    path = tmp_path / "out.bin"

    def writer(tmp: Path) -> None:
        tmp.write_bytes(b"partial")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        storage.atomic_write(path, writer)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []  # tmp も残っていない


def test_resolve_uri_file_scheme_maps_under_root(tmp_path: Path) -> None:
    assert storage.resolve_uri(tmp_path, "file:data") == tmp_path / "data"
    assert storage.resolve_uri(tmp_path, "file:docs/data") == tmp_path / "docs" / "data"


def test_resolve_uri_rejects_non_file_scheme(tmp_path: Path) -> None:
    """非 file: の URI は UnsupportedURIError（黙ったフォールバックはしない）。"""
    with pytest.raises(storage.UnsupportedURIError, match="s3"):
        storage.resolve_uri(tmp_path, "s3://bucket/data")


def test_manifest_roundtrip_with_japanese_values(tmp_path: Path) -> None:
    """write_manifest→read_manifest が日本語の値ごと往復し、バイト形式も従来と同一であること。"""
    path = tmp_path / "t.manifest.yaml"
    manifest = {"table_id": "合成データ", "fingerprint": "abc", "inputs": ["原本"], "code": None}
    storage.write_manifest(path, manifest)
    assert storage.read_manifest(path) == manifest
    # 既存ファイルとバイト一致を保つ（従来の書式＝safe_dump(allow_unicode=True, sort_keys=False)）。
    expected = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
    assert path.read_text(encoding="utf-8") == expected


def test_verify_fingerprint_passes_match_and_rejects_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_text("data", encoding="utf-8")
    storage.verify_fingerprint(path, hashlib.sha256(b"data").hexdigest())  # 一致は素通り
    with pytest.raises(ValueError, match="指紋"):
        storage.verify_fingerprint(path, "0" * 64)


def test_schema_project_dir_fails_loud_on_non_file_metadata_uri(tmp_path: Path) -> None:
    """schema は非 file: の metadata URI で UnsupportedURIError（旧：docs/data へ黙ってフォールバック）。

    store/models と同じ fail-loud に統一する（T-0047 の意図した変更）。
    """
    cfg = tmp_path / ".harness" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[metadata]\nuri = "s3:bucket/meta"\n', encoding="utf-8")
    with pytest.raises(storage.UnsupportedURIError, match="s3"):
        schema.load_schemas(tmp_path)
