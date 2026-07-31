"""CI 設定（.github/workflows/ci.yaml）の退行を止める検査。

Windows CI ジョブは cp932 コンソール・パス区切り等の OS 差を止める意図的な投資。誰かが matrix から
windows-latest を落としても気づけるよう、両 OS で verify が走る構成を機械で固定する（退行を止めるラチェット）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

_CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yaml"


def _verify_job() -> Any:
    spec: Any = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    return spec["jobs"]["verify"]


def test_ci_runs_verify_on_linux_and_windows() -> None:
    # verify ジョブは OS matrix で ubuntu と windows の両方を回す（Windows 差の検出＝意図した投資を守る）。
    oses = _verify_job()["strategy"]["matrix"]["os"]
    assert "ubuntu-latest" in oses
    assert "windows-latest" in oses  # 落とすと Windows の退行（cp932・パス）を CI が見逃す


def test_ci_uses_the_shared_verify_command() -> None:
    # CI はローカルと同じ `uv run verify`（完了の定義を一致させる）＝別コマンドに差し替えない。
    runs = [step.get("run", "") for step in _verify_job()["steps"]]
    assert any("uv run verify" in r for r in runs)
    assert any("uv sync --all-extras" in r for r in runs)  # optional 依存のテストを skip しない規約


def test_ci_runs_browser_tests_since_verify_excludes_them() -> None:
    # 描画の browser テストは既定の verify から除外（Chrome を毎回起動しない）ので、merge 前に CI が
    # 必ず走らせる＝どこにも走らない黙った空白を作らない（fail-closed をローカル skip から CI 必須へ移す）。
    steps = _verify_job()["steps"]
    browser = [s for s in steps if "pytest" in s.get("run", "") and "-m browser" in s.get("run", "")]
    assert browser, "CI の verify ジョブに `pytest -m browser` が無い"
    # Chrome 欠如を skip（緑の空振り）でなく fail にする env を必須にする＝唯一の必須実行点が空振りしない。
    assert any(str(s.get("env", {}).get("HARNESS_REQUIRE_BROWSER", "")) == "1" for s in browser), (
        "browser 実行 step に HARNESS_REQUIRE_BROWSER=1 が無い（Chrome 欠如を skip で緑にしてしまう）"
    )
