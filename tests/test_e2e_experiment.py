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

pytestmark = pytest.mark.e2e

_ROOT = Path(__file__).resolve().parents[1]  # harness-template リポの根
_TRAIN = _ROOT / "work" / "EP-06-ds-experiment-loop" / "E-0001-interaction-feature" / "code" / "train.py"


def test_e0001_smoke(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONUTF8": "1"}  # Windows コンソールでも日本語・記号を出せるように
    result = subprocess.run(
        [sys.executable, str(_TRAIN), "--variant", "baseline", "--test", "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, result.stderr  # 端から端まで通って合否（0=閾値を満たす）
    assert (tmp_path / "metrics_baseline.yaml").is_file()  # results が書き出される
