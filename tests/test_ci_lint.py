"""ci_lint（CI テンプレート templates/ci/ の構造 lint の器）のテスト。

期待値の導き方：一時プロジェクトに何を置くか（置かないか）の構成から導く（金メッキ禁止）。
- templates/ci/ を置かない → 検査対象外＝指摘 0 件（コピーして使う先の案件で誤検知しない）。
- templates/ci/ を置くが、骨組みの必須ファイル一覧（_REQUIRED）は空タプル → 指摘 0 件。
- _REQUIRED に 1 件足して（monkeypatch）そのファイルを置かない → その名前を名指しで error 1 件
  （T-0111 が _REQUIRED を育てたとき欠落検査が働くことを、器の時点で固定する）。
GitHub Actions もネットワークも使わない（実行しない・構造検査のみ＝deploy_lint 同型）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.ops import ci_lint

pytestmark = pytest.mark.unit


def test_no_templates_ci_no_problems(tmp_path: Path) -> None:
    # templates/ci/ が無い＝テンプレートを同梱しないコピー先の案件。誤検知しない（指摘 0 件）。
    assert ci_lint.run_checks(tmp_path) == []


def test_templates_ci_present_skeleton_requires_nothing(tmp_path: Path) -> None:
    # 骨組みの _REQUIRED は空タプル＝templates/ci/ が在っても要求するファイルが無く指摘 0 件。
    (tmp_path / "templates" / "ci").mkdir(parents=True)
    assert ci_lint.run_checks(tmp_path) == []


def test_missing_required_file_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 必須ファイルを 1 件要求し（構成側で注入）そのファイルを置かない＝名指しの error が 1 件。
    (tmp_path / "templates" / "ci").mkdir(parents=True)
    monkeypatch.setattr(ci_lint, "_REQUIRED", (".github/workflows/verify.yml",))
    problems = ci_lint.run_checks(tmp_path)
    assert [p.level for p in problems] == ["error"]
    assert ".github/workflows/verify.yml" in problems[0].message
