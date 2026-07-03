"""E-0001 の端から端まで（e2e）スモーク。実験スクリプトそのものを subprocess で叩く。

これにより「雛形から乖離した実験」「テストだけ通る二重実装」が構造的に不可能になる——
verify（full で e2e が走る）が落ちるのは実験スクリプト本体が壊れたとき。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.e2e

_ROOT = Path(__file__).resolve().parents[1]  # harness-template リポの根
_TRAIN = _ROOT / "work" / "EP-06-ds-experiment-loop" / "E-0001-interaction-feature" / "code" / "train.py"


def _run(tmp_path: Path, variant: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONUTF8": "1"}  # Windows コンソールでも日本語・記号を出せるように
    return subprocess.run(
        [sys.executable, str(_TRAIN), "--variant", variant, "--test", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_ROOT),
    )


def test_e0001_smoke(tmp_path: Path) -> None:
    result = _run(tmp_path, "baseline")
    assert result.returncode == 0, result.stderr  # 端から端まで通って合否（0=閾値を満たす）
    metrics = tmp_path / "results" / "metrics_baseline.yaml"
    assert metrics.is_file()  # results が書き出される
    record = yaml.safe_load(metrics.read_text(encoding="utf-8"))
    assert record["fingerprints"]["folds"] and record["fingerprints"]["model"]  # 保存の指紋が結ばれる
    # fold 表（split 層）とモデルの manifest が実体として保存される。
    assert (tmp_path / "data" / "work" / "E-0001" / "split" / "e0001_folds.parquet").is_file()
    assert list((tmp_path / "data" / "work" / "E-0001" / "models" / "baseline").glob("*/manifest.yaml"))


def test_e0001_two_variants_share_folds(tmp_path: Path) -> None:
    # 同じ root で baseline→interaction を続けて実行＝同一分割で比較（核2の実地）。両 results の fold 指紋が一致。
    assert _run(tmp_path, "baseline").returncode == 0
    assert _run(tmp_path, "interaction").returncode == 0
    base = yaml.safe_load((tmp_path / "results" / "metrics_baseline.yaml").read_text(encoding="utf-8"))
    inter = yaml.safe_load((tmp_path / "results" / "metrics_interaction.yaml").read_text(encoding="utf-8"))
    assert base["fingerprints"]["folds"] == inter["fingerprints"]["folds"]  # 同一分割で比較した証拠
