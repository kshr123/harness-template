"""agent lint（docs/agents/**/*.yaml の provider 実在検査）と、プロファイルの軽 import の検査。

lint は一時プロジェクトで検査する（deploy_lint のテストと同じ思想：実行せず構造だけを見る）。
軽 import は subprocess の素の Python で `import harness.agent` し、anthropic/fastapi/uvicorn/polars が
読み込まれないことを固定する（プロファイルのモジュールは重い依存を top で import しない規約＝DEC-0013）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from harness.agent import lint

_SPEC_TEMPLATE = """\
name: demo
provider: {provider}
model: dummy-model
system_prompt: そのまま返す
"""


def _write_spec(root: Path, provider: str) -> None:
    base = root / "docs" / "agents"
    base.mkdir(parents=True, exist_ok=True)
    (base / "demo.yaml").write_text(_SPEC_TEMPLATE.format(provider=provider), encoding="utf-8")


@pytest.mark.unit
def test_no_agents_dir_reports_nothing(tmp_path: Path) -> None:
    assert lint.run_checks(tmp_path) == []  # 宣言を持たないプロジェクト＝誤検知しない


@pytest.mark.unit
def test_unregistered_provider_is_an_error(tmp_path: Path) -> None:
    _write_spec(tmp_path, "no_such_provider")
    problems = lint.run_checks(tmp_path)
    assert len(problems) == 1
    assert problems[0].level == "error"
    assert "no_such_provider" in problems[0].message
    assert "demo.yaml" in problems[0].message  # どのファイルかを名指しする


@pytest.mark.unit
def test_registered_provider_passes(tmp_path: Path) -> None:
    _write_spec(tmp_path, "dummy")
    assert lint.run_checks(tmp_path) == []


def _write_raw(root: Path, body: str) -> None:
    base = root / "docs" / "agents"
    base.mkdir(parents=True, exist_ok=True)
    (base / "demo.yaml").write_text(body, encoding="utf-8")


@pytest.mark.unit
def test_malformed_yaml_is_an_error(tmp_path: Path) -> None:
    # 壊れた YAML は落とさず error として名指しする（読めない宣言を黙って通さない）。
    _write_raw(tmp_path, "provider: [unterminated\n")
    problems = lint.run_checks(tmp_path)
    assert len(problems) == 1
    assert problems[0].level == "error"
    assert "demo.yaml" in problems[0].message


@pytest.mark.unit
def test_empty_yaml_is_an_error(tmp_path: Path) -> None:
    # 空ファイル（safe_load → None）は dict でない＝error（provider を検査できない宣言を通さない）。
    _write_raw(tmp_path, "")
    problems = lint.run_checks(tmp_path)
    assert len(problems) == 1
    assert problems[0].level == "error"


@pytest.mark.unit
def test_missing_provider_key_is_an_error(tmp_path: Path) -> None:
    # provider キーそのものが無い宣言も error（None は PROVIDERS に無い）。
    _write_raw(tmp_path, "name: demo\nmodel: dummy-model\nsystem_prompt: x\n")
    problems = lint.run_checks(tmp_path)
    assert len(problems) == 1
    assert problems[0].level == "error"
    assert "provider" in problems[0].message


@pytest.mark.integration
def test_import_harness_agent_stays_light() -> None:
    # 素の Python で import harness.agent しても重い依存は読み込まれない（PROFILE 経路の軽さを固定）。
    code = (
        "import sys\n"
        "import harness.agent\n"
        "from harness.agent import lint\n"
        "assert harness.agent.PROFILE.name == 'agent', harness.agent.PROFILE\n"
        "assert harness.agent.PROFILE.pm_checks == (lint.run_checks,), harness.agent.PROFILE\n"
        "heavy = [m for m in ('anthropic', 'fastapi', 'uvicorn', 'polars', 'sklearn') if m in sys.modules]\n"
        "assert not heavy, f'import harness.agent が重い依存を読み込んだ: {heavy}'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
