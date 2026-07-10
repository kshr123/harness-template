"""EDA ビュー（notebooks/eda.py・marimo）の端から端までスモーク。

marimo の純 Python を `python notebooks/eda.py` でヘッドレス実行し「例外なく通る」だけを検査する
（図の画素・描画結果は比較しない＝図があってもテストは壊れない）。数値の正しさは src 側の unit/integration
が持つ。これで「実行される雛形は腐らない」水路（E-0001 と同型）に marimo ビューを載せる。DESIGN §3・§4 判断1。
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from harness.ds import data, store

pytestmark = pytest.mark.e2e

_ROOT = Path(__file__).resolve().parents[1]
_NOTEBOOK = _ROOT / "notebooks" / "eda.py"

_SCHEMA = {
    "id": "synthetic",
    "description": "スモーク用の合成データ",
    "layer": "raw",
    "role": "cleaned",
    "primary_key": ["id"],
    "columns": [
        {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
        {"name": "x1", "dtype": "Float64", "nullable": False},
        {"name": "x2", "dtype": "Float64", "nullable": False},
        {"name": "y", "dtype": "Int64", "nullable": False, "allowed_values": [0, 1]},
    ],
}


def _run(root: Path, *, target: str, test: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "HARNESS_EDA_TRAIN": "synthetic",
        "HARNESS_EDA_TARGET": target,
        "HARNESS_EDA_TEST": test,
    }
    return subprocess.run(
        [sys.executable, str(_NOTEBOOK)], capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(root)
    )


def test_eda_notebook_runs_headless(make_project: Callable[..., object]) -> None:
    project = make_project()
    root: Path = project.root  # type: ignore[attr-defined]
    project.add_schema(_SCHEMA)  # type: ignore[attr-defined]
    # 比較用の 2 表目（同じ定義で別 ID）。
    project.add_schema({**_SCHEMA, "id": "synthetic_test"})  # type: ignore[attr-defined]
    store.save(root, data.generate_synthetic(n=60, seed=0), "synthetic")
    store.save(root, data.generate_synthetic(n=40, seed=1), "synthetic_test")

    # 目的変数あり（分類の要約セルも通る）。
    done = _run(root, target="y")
    assert done.returncode == 0, done.stderr
    # 目的変数なし（要約セルを飛ばす経路も落ちない）。
    assert _run(root, target="").returncode == 0
    # test 指定（train/test 比較セルも通る）。
    assert _run(root, target="y", test="synthetic_test").returncode == 0
