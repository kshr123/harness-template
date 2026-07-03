"""教師なしビュー（notebooks/unsupervised.py・marimo）の端から端までスモーク。

marimo の純 Python を `python notebooks/unsupervised.py` でヘッドレス実行し「例外なく通る」だけを検査する
（図の画素・描画結果は比較しない）。数値の正しさは src 側の unit/integration が持つ。これで「実行される
雛形は腐らない」水路（eda ビューと同型）に教師なしビューを載せる。
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
_NOTEBOOK = _ROOT / "notebooks" / "unsupervised.py"

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


def _run(root: Path, *, color: str = "", columns: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "HARNESS_UNSUP_TABLE": "synthetic",
        "HARNESS_UNSUP_COLOR": color,
        "HARNESS_UNSUP_COLUMNS": columns,
    }
    return subprocess.run([sys.executable, str(_NOTEBOOK)], capture_output=True, text=True, env=env, cwd=str(root))


def test_unsupervised_notebook_runs_headless(make_project: Callable[..., object]) -> None:
    project = make_project()
    root: Path = project.root  # type: ignore[attr-defined]
    project.add_schema(_SCHEMA)  # type: ignore[attr-defined]
    store.save(root, data.generate_synthetic(n=80, seed=0), "synthetic")

    # 色分けなし（既定・id を除いた数値列で埋め込み/クラスタ/異常が通る）。
    done = _run(root)
    assert done.returncode == 0, done.stderr
    # 目的変数で色分け（色分け経路も落ちない）。
    assert _run(root, color="y").returncode == 0
    # 列を明示（--columns 相当の経路）。
    assert _run(root, columns="x1,x2").returncode == 0
