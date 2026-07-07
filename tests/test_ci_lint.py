"""ci_lint（CI テンプレート templates/ci/ の構造 lint）のテスト。

期待値の導き方：自リポの実テンプレート（templates/ci/）を「生きた fixture」として tmp_path にコピーし、
既知の 1 箇所（verify step・python-version・--all-extras）を意図的に壊す→壊した箇所が名指しで error に
なることを確かめる（変異ガード。deploy_lint のテストと同型）。error の件数・文言は「何を壊したか」の
構成から導く（実装の出力をコピーした固定値ではない＝金メッキ禁止）。
GitHub Actions もネットワークも使わない（実行しない・構造検査のみ）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness.ops import ci_lint

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates" / "ci"
WORKFLOW = ".github/workflows/verify.yml"

# リポの正（pyproject の requires-python ">=3.14"）と同じ版を持つ最小 pyproject。
# 版の期待値はこの構成（3.14 と書いたこと）から導く。
_PYPROJECT = '[project]\nname = "copy-dest"\nversion = "0.1.0"\nrequires-python = ">=3.14"\n'


def _copy_templates(tmp_path: Path) -> Path:
    """実テンプレート一式＋最小 pyproject を一時プロジェクトへ置き、その root を返す。"""
    shutil.copytree(TEMPLATES, tmp_path / "templates" / "ci")
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return tmp_path


def _mutate(root: Path, old: str, new: str) -> None:
    """ワークフロー雛形の 1 箇所を置換して壊す。old が無い＝fixture の前提が崩れているので失敗にする。"""
    path = root / "templates" / "ci" / WORKFLOW
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture の前提が崩れている: {WORKFLOW} に {old!r} が無い"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in ci_lint.run_checks(root) if p.level == "error"]


# --- 入口の分岐（テンプレートの有無） ---


@pytest.mark.unit
def test_no_templates_ci_no_problems(tmp_path: Path) -> None:
    # templates/ci/ が無い＝テンプレートを同梱しないコピー先の案件。誤検知しない（指摘 0 件）。
    assert ci_lint.run_checks(tmp_path) == []


@pytest.mark.integration
def test_repo_template_passes() -> None:
    # 自リポの出荷テンプレートは 0 件で通る＝「生きた fixture」（verify のたびに腐りを検知する回帰の番人）。
    assert ci_lint.run_checks(REPO_ROOT) == []


# --- 必須ファイル ---


@pytest.mark.unit
def test_missing_workflow_file_flagged(tmp_path: Path) -> None:
    # templates/ci/ は在るが verify.yml が無い＝複製先がゲート無しで始まる構成→名指しの error。
    (tmp_path / "templates" / "ci").mkdir(parents=True)
    errors = _errors(tmp_path)
    assert any(WORKFLOW in m for m in errors)


# --- verify step（ゲートの本体） ---


@pytest.mark.unit
def test_missing_verify_step_flagged(tmp_path: Path) -> None:
    # verify step を意図的に抜く（run を無関係なコマンドへ置換）→壊したのは 1 箇所なので error は 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, "uv run verify", "echo done")
    errors = _errors(root)
    assert len(errors) == 1
    assert "uv run verify" in errors[0]


# --- Python 版の整合（雛形＝リポの正） ---


@pytest.mark.unit
def test_python_version_mismatch_flagged(tmp_path: Path) -> None:
    # 雛形の版だけを 3.13 へずらす（pyproject は 3.14 のまま）→両方の版を名指しで error 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, 'python-version: "3.14"', 'python-version: "3.13"')
    errors = _errors(root)
    assert len(errors) == 1
    assert "3.13" in errors[0] and "3.14" in errors[0]


@pytest.mark.unit
def test_unpinned_python_version_flagged(tmp_path: Path) -> None:
    # python-version の指定そのものを消す（別の with キーへ置換）→版の乖離を検査できない構成＝error。
    root = _copy_templates(tmp_path)
    _mutate(root, 'python-version: "3.14"', "enable-cache: true")
    errors = _errors(root)
    assert any("python-version" in m for m in errors)


@pytest.mark.unit
def test_without_pyproject_version_check_skipped(tmp_path: Path) -> None:
    # コピー先に pyproject が無い＝リポの正を導出できない→版検査は行わない（誤検知しない）。他は満たすので 0 件。
    shutil.copytree(TEMPLATES, tmp_path / "templates" / "ci")
    assert ci_lint.run_checks(tmp_path) == []


# --- uv sync の extras（verify 環境は全部入り＝AGENTS の規約） ---


@pytest.mark.unit
def test_missing_all_extras_flagged(tmp_path: Path) -> None:
    # uv sync から --all-extras だけを外す（step 自体は残す）→規約違反の 1 箇所＝error 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, "uv sync --all-extras", "uv sync")
    errors = _errors(root)
    assert len(errors) == 1
    assert "--all-extras" in errors[0]


# --- 壊れた YAML ---


@pytest.mark.unit
def test_broken_yaml_is_error_not_crash(tmp_path: Path) -> None:
    # YAML として読めない雛形＝内容検査に進めない構成→クラッシュせず error で報告。
    root = _copy_templates(tmp_path)
    (root / "templates" / "ci" / WORKFLOW).write_text("jobs: [unclosed\n", encoding="utf-8")
    errors = _errors(root)
    assert any(WORKFLOW in m and "YAML" in m for m in errors)
