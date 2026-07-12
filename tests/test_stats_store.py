"""InferenceData の保存・読込の検査（T-0215）。

期待値は構成から：手で組んだ InferenceData を保存→読込して、同じ変数・同じ値が戻る。指紋照合（改変検知）・
版の非再利用・format 分岐（未対応は拒否）・manifest の由来書きも確かめる。MCMC は使わず（速い）az.from_dict で
最小の idata を組む。stats を使わない複製では importorskip で skip。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("arviz")
pytest.importorskip("h5py")

import arviz as az  # noqa: E402

from harness.stats import store  # noqa: E402

pytestmark = pytest.mark.integration


def _tiny_idata() -> object:
    rng = np.random.default_rng(0)
    return az.from_dict({"posterior": {"mu": rng.normal(size=(2, 50)), "sigma": rng.normal(size=(2, 50))}})


def test_save_load_roundtrip_preserves_posterior(tmp_path: Path) -> None:
    idata = _tiny_idata()
    mu_before = np.asarray(idata.posterior["mu"])  # type: ignore[attr-defined]
    store.save_inference(tmp_path, idata, name="m", version="v1", provenance={"model": "linear", "seed": 0})
    loaded, manifest = store.load_inference(tmp_path, name="m", version="v1")
    assert np.allclose(np.asarray(loaded.posterior["mu"]), mu_before)  # 値が往復で保たれる（構成と一致）
    assert manifest["format"] == "netcdf" and manifest["provenance"]["model"] == "linear"  # 由来書きが残る


def test_load_latest_when_version_omitted(tmp_path: Path) -> None:
    store.save_inference(tmp_path, _tiny_idata(), name="m", version="20260713T000001000000Z")
    store.save_inference(tmp_path, _tiny_idata(), name="m", version="20260713T000002000000Z")  # 新しい版
    _, manifest = store.load_inference(tmp_path, name="m")  # version 省略＝最新
    assert manifest["version"] == "20260713T000002000000Z"  # 辞書順の最後＝最新


def test_version_is_not_reused(tmp_path: Path) -> None:
    store.save_inference(tmp_path, _tiny_idata(), name="m", version="v1")
    with pytest.raises(ValueError, match="版"):
        store.save_inference(tmp_path, _tiny_idata(), name="m", version="v1")  # 同じ版は拒否


def test_tampered_file_is_rejected_on_load(tmp_path: Path) -> None:
    store.save_inference(tmp_path, _tiny_idata(), name="m", version="v1")
    nc = tmp_path / "models" / "stats" / "m" / "v1" / store.INFERENCE_FILE
    nc.write_bytes(nc.read_bytes() + b"tampered")  # 実体を改変
    with pytest.raises(ValueError, match="指紋"):
        store.load_inference(tmp_path, name="m", version="v1")  # 指紋不一致で拒否（fail closed）


def test_unsupported_format_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="未対応の保存形式"):
        store.save_inference(tmp_path, _tiny_idata(), name="m", version="v1", format="bogus")


def test_missing_inference_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="保存済み推論が無い"):
        store.load_inference(tmp_path, name="absent")
