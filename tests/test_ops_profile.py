"""ops プロファイル（harness.ops）の結線と軽 import のテスト。

- 結線：profiles に "harness.ops" を宣言した config（tmp_path 上に組み立てる）経由で load_profiles が ops を返し、
  pm_checks に ci_lint.run_checks が入る＝verify の pm 検査に乗る。期待値は宣言した config と profile.py の構成
  （何を登録したか）から導出する（このリポの config 値はハードコードしない＝T-0191）。
- 軽 import：subprocess の素の Python で `import harness.ops` しても重い依存（fastapi・uvicorn・
  polars・sklearn・anthropic）が sys.modules に入らないことを固定する（プロファイルのモジュールは
  重い依存を top で import しない規約。serve/agent の同種テストと同型）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from harness import profiles


@pytest.mark.integration
def test_load_profiles_includes_ops(tmp_path: Path) -> None:
    # profiles に "harness.ops" を宣言した config で load_profiles が ops を載せ、ci_lint が verify に繋がる。
    cfg = tmp_path / ".harness" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('profiles = ["harness.ops"]\n', encoding="utf-8")
    loaded = {p.name: p for p in profiles.load_profiles(tmp_path)}
    assert "ops" in loaded
    from harness.ops import ci_lint

    assert ci_lint.run_checks in loaded["ops"].pm_checks


@pytest.mark.unit
def test_ops_profile_light_import() -> None:
    # 素の Python で import harness.ops しても重い依存は読み込まれない（PROFILE 経路の軽さを固定）。
    code = (
        "import sys\n"
        "import harness.ops\n"
        "from harness.ops import ci_lint\n"
        "assert harness.ops.PROFILE.name == 'ops', harness.ops.PROFILE\n"
        "assert harness.ops.PROFILE.pm_checks == (ci_lint.run_checks,), harness.ops.PROFILE\n"
        "heavy = [m for m in ('fastapi', 'uvicorn', 'polars', 'sklearn', 'anthropic') if m in sys.modules]\n"
        "assert not heavy, f'import harness.ops が重い依存を読み込んだ: {heavy}'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
