"""stats プロファイルの依存（pymc/nutpie/arviz＋netCDF 保存）が使えることの検査（T-0211）。

verify 環境は `uv sync --all-extras`＝スタックは導入済みとして走る。stats を使わない複製（`profiles=[]`・素の
`uv sync`）では importorskip で skip（optional 依存の欠如＝バグの skip ではないので ISS 参照は不要・lightgbm
テストと同じ「all-extras 前提」の思想）。期待値は構成から：手で組んだ InferenceData を netCDF 保存→読込して
同じ変数・同じ値が戻ることを確かめる（保存ライブラリ h5netcdf＋h5py が 3.14 で動く証拠）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pymc")
pytest.importorskip("nutpie")
pytest.importorskip("arviz")
pytest.importorskip("h5py")

import arviz as az  # noqa: E402  importorskip の後で読む

pytestmark = pytest.mark.integration


def test_stats_stack_imports() -> None:
    """pymc/nutpie/pytensor/arviz が import できる＝スタックが 3.14 に載る（T-0211 の受け入れ）。"""
    import nutpie  # noqa: F401
    import pymc  # noqa: F401
    import pytensor  # noqa: F401


def test_inference_data_netcdf_roundtrip(tmp_path: Path) -> None:
    """InferenceData を netCDF 保存→読込して、同じ変数・同じ値が戻る（保存形式の一往復が動く）。

    2 chains × 50 draws の乱数を posterior に組み、netCDF へ書いて読み直す。値は構成した乱数と一致する
    （実装出力の写経でなく、入力そのものが期待値）。h5netcdf バックエンドが h5py を要求するため両方が要る。
    """
    rng = np.random.default_rng(0)
    posterior = {"mu": rng.normal(size=(2, 50)), "sigma": rng.normal(size=(2, 50))}
    idata = az.from_dict({"posterior": posterior})
    path = tmp_path / "idata.nc"
    idata.to_netcdf(str(path))
    loaded = az.from_netcdf(str(path))
    assert "mu" in loaded.posterior and "sigma" in loaded.posterior  # 変数が往復で残る
    assert np.allclose(np.asarray(loaded.posterior["mu"]), posterior["mu"])  # 値が保たれる（構成と一致）
