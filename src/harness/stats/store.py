"""InferenceData（事後分布）の保存・読込。正本は netCDF（点推定へ潰さない）。

保存の 4 作法（URI 解決・原子的書き込み・sha256 指紋・manifest）は `harness.storage` の共通部品を使う
（ds の store.py・models.py と同じ土台）。方針（版は再利用しない・manifest は最後＝完了の印・load は指紋照合
してから読む）はここが持つ。形式は manifest の `format` 文字列で分岐する拡張ポイント（今は netcdf のみ。
可搬形式が要るときにここへ枝を足す）。arviz は関数内で遅延 import する（`import harness.stats.store` は未導入
でも成功する）。**点推定の指標へ潰す保存はしない**＝事後分布・不確実性を丸ごと残す。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness import storage
from harness.promotion import MANIFEST_FILE  # 台帳の形式を共有する（版ディレクトリの manifest.yaml＝promotion が読む）

INFERENCE_FILE = "inference.nc"
VERSION_FORMAT = "%Y%m%dT%H%M%S%fZ"
# manifest の format 文字列 → 読み書きの分岐（拡張ポイント）。今は netCDF のみ。
_SUPPORTED_FORMATS = ("netcdf",)


def entity_dir(root: Path, *, name: str) -> Path:
    """この名前の推論結果の置き場（ds の models と別名前空間＝models/stats/<name>）。"""
    return root / "models" / "stats" / name


def save_inference(
    root: Path,
    idata: Any,  # noqa: ANN401  arviz.InferenceData
    *,
    name: str,
    version: str | None = None,
    format: str = "netcdf",
    metrics: Mapping[str, float] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> str:
    """InferenceData を netCDF＋manifest で保存する。版ディレクトリが既にあれば拒否（版は再利用しない）。

    version 省略時は UTC のタイムスタンプ。metrics（elpd_loo 等の採用に使う指標）は manifest の `metrics` に
    載る（promotion が baseline として読む鍵と同じ）。provenance（model kind・sampler・seed 等）は由来書き。
    返り値は実体（.nc）の sha256 指紋。format は今 netcdf のみ（未対応は ValueError）。
    """
    if format not in _SUPPORTED_FORMATS:
        raise ValueError(f"未対応の保存形式 '{format}'（対応: {list(_SUPPORTED_FORMATS)}）")
    resolved_version = version if version is not None else datetime.now(UTC).strftime(VERSION_FORMAT)
    version_dir = entity_dir(root, name=name) / resolved_version
    try:
        version_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(f"同じ版 {resolved_version} が既にある（版は再利用しない）") from exc

    fingerprint = storage.atomic_write(version_dir / INFERENCE_FILE, lambda p: idata.to_netcdf(str(p)))
    manifest = {
        "name": name,
        "version": resolved_version,
        "format": format,
        "fingerprint": fingerprint,
        "file_name": INFERENCE_FILE,
        "created": datetime.now(UTC).isoformat(),
        "metrics": dict(metrics) if metrics else {},  # promotion._version_metrics が baseline として読む鍵
        "provenance": dict(provenance) if provenance else {},
    }
    # manifest は最後に書く（存在＝保存完了の印）。原子的に書く（storage.write_manifest）。
    storage.write_manifest(version_dir / MANIFEST_FILE, manifest)
    return fingerprint


def _versions(name_dir: Path) -> list[str]:
    """manifest がある版だけを昇順で返す（途中で落ちた孤児ディレクトリを最新扱いしない）。"""
    if not name_dir.is_dir():
        return []
    return sorted(d.name for d in name_dir.iterdir() if d.is_dir() and (d / MANIFEST_FILE).is_file())


def load_inference(root: Path, *, name: str, version: str | None = None) -> tuple[Any, dict[str, Any]]:
    """保存済み InferenceData を読む。version=None は最新（版の降順 1 件）。指紋照合してから読む。

    manifest の format で分岐（未対応形式は ValueError）。実体の指紋が manifest と一致しなければ ValueError
    （改変・破損した .nc を読ませない＝fail closed）。返り値は (InferenceData, manifest)。
    """
    name_dir = entity_dir(root, name=name)
    resolved_version = version
    if resolved_version is None:
        versions = _versions(name_dir)
        if not versions:
            raise ValueError(f"'{name}' の保存済み推論が無い（{name_dir}）")
        resolved_version = versions[-1]  # 版はタイムスタンプ＝辞書順の最後が最新
    version_dir = name_dir / resolved_version
    manifest_path = version_dir / MANIFEST_FILE
    if not manifest_path.is_file():
        raise ValueError(f"manifest が無い（未保存・保存が途中で落ちた）: {manifest_path}")
    manifest = storage.read_manifest(manifest_path)
    fmt = manifest["format"]
    if fmt not in _SUPPORTED_FORMATS:
        raise ValueError(f"未対応の保存形式 '{fmt}'（対応: {list(_SUPPORTED_FORMATS)}）")
    nc_path = version_dir / manifest["file_name"]
    storage.verify_fingerprint(nc_path, manifest["fingerprint"])  # 改変・破損は ValueError（fail closed）

    import arviz as az

    return az.from_netcdf(str(nc_path)), manifest
