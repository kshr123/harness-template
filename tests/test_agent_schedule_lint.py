"""schedule_lint（time-based routine 雛形 templates/schedule/ の構造 lint）のテスト。

期待値の導き方：自リポの実雛形を「生きた fixture」として tmp_path にコピーし（pyproject.toml も
一緒にコピーして [project.scripts] の実在チェックの基準をそろえる）、既知の構成（cron・
workflow_dispatch・停止コメント・停止見出し・permissions・uv run agent）を 1 箇所だけ壊す。
壊した値が名指しで error になることを確かめる（変異ガード）。数値・文言はテンプレートの構成から
導く（実装の出力をコピーした固定値ではない）。GitHub Actions の実行・ネットワークは使わない。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness.agent import schedule_lint

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates" / "schedule"


def _copy_templates(tmp_path: Path) -> Path:
    """実テンプレート一式＋pyproject.toml を一時プロジェクトへコピーし、その root を返す。

    pyproject.toml も一緒にコピーするのは、(h) の「uv run <script> が [project.scripts] に実在するか」
    の基準を自リポと揃え、無関係な変異テストで script 不在の余計な error が紛れ込まないようにするため。
    """
    shutil.copytree(TEMPLATES, tmp_path / "templates" / "schedule")
    shutil.copy(REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    return tmp_path


def _mutate(root: Path, rel: str, old: str, new: str) -> None:
    """テンプレートの 1 箇所を置換して壊す。old が無い＝fixture の前提が崩れているので失敗にする。"""
    path = root / "templates" / "schedule" / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture の前提が崩れている: {rel} に {old!r} が無い"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in schedule_lint.run_checks(root) if p.level == "error"]


# --- 入口の分岐（テンプレートの有無） ---


@pytest.mark.unit
def test_no_templates_dir_yields_no_problems(tmp_path: Path) -> None:
    # templates/schedule/ が無い＝コピーして使う先の案件。何も指摘しない（誤検知しない）。
    assert schedule_lint.run_checks(tmp_path) == []


@pytest.mark.integration
def test_real_repo_schedule_template_passes_clean() -> None:
    # 自リポの出荷雛形は 0 件で通る＝「生きた fixture」（verify のたびに腐りを検知する回帰の番人）。
    assert schedule_lint.run_checks(REPO_ROOT) == []


# --- 必須ファイル ---


@pytest.mark.unit
def test_missing_required_file_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    (root / "templates" / "schedule" / "README.md").unlink()
    assert any("README.md" in m and "必須" in m for m in _errors(root))


# --- YAML が壊れている ---


@pytest.mark.unit
def test_broken_yaml_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    (root / "templates" / "schedule" / "monitor.yml").write_text("on: [unclosed\n", encoding="utf-8")
    assert any("monitor.yml" in m and "YAML" in m for m in _errors(root))


# --- trigger（schedule.cron・workflow_dispatch） ---


@pytest.mark.unit
def test_missing_schedule_trigger_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "monitor.yml", '  schedule:\n    - cron: "17 6 * * 1"\n', "")
    assert any("cron" in m and ("schedule" in m or "trigger" in m) for m in _errors(root))


@pytest.mark.unit
def test_missing_workflow_dispatch_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "monitor.yml", "  workflow_dispatch: {}\n", "")
    assert any("workflow_dispatch" in m for m in _errors(root))


@pytest.mark.unit
def test_cron_wrong_field_count_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "monitor.yml", '"17 6 * * 1"', '"17 6 * * 1 *"')
    errors = _errors(root)
    assert any("cron" in m and "5" in m for m in errors)


# --- stop 宣言（停止コメント＋停止見出し） ---


@pytest.mark.unit
def test_missing_stop_comment_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(
        root,
        "monitor.yml",
        "# 停止（stop）＝ Actions 画面で Disable workflow（gh workflow disable でも可）、\n",
        "# 定期実行についての補足コメント。\n",
    )
    assert any("monitor.yml" in m and "停止" in m for m in _errors(root))


@pytest.mark.unit
def test_stop_comment_without_reference_is_error(tmp_path: Path) -> None:
    # (e) の後半＝停止コメントが runbook（README/docs）を指すことの検査を直接ピン留めする。
    # 「停止」の語は残し、参照先（README.md/docs/agent.md）への言及だけを外す＝前半をすり抜け後半が効く。
    root = _copy_templates(tmp_path)
    _mutate(
        root,
        "monitor.yml",
        "手順の正本は README.md と docs/agent.md の time-based 節。",
        "手順は各自で管理すること。",
    )
    errors = _errors(root)
    assert any("monitor.yml" in m and "参照していない" in m for m in errors)


@pytest.mark.unit
def test_readme_without_stop_section_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    readme = root / "templates" / "schedule" / "README.md"
    text = readme.read_text(encoding="utf-8")
    assert "## 停止（stop）" in text, "fixture の前提が崩れている: README.md に停止見出しが無い"
    readme.write_text(text.replace("## 停止（stop）", "## routine を止める手順"), encoding="utf-8")
    assert any("README.md" in m and "停止" in m for m in _errors(root))


# --- CLI サブコマンドの実在（h） ---


@pytest.mark.unit
def test_unknown_script_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "monitor.yml", "uv run agent monitor --file-issue", "uv run agentx monitor --file-issue")
    errors = _errors(root)
    assert any("agentx" in m for m in errors)


@pytest.mark.integration
def test_schedule_template_commands_resolve() -> None:
    # 雛形の `uv run agent <sub>` の <sub>（monitor）が typer app に実在するか＝サブコマンド腐り検知。
    # lint 本体に typer を持ち込まない分業（DEC-0013）なので、この確認はテスト側に置く。
    from harness.agent.cli import agent_app

    text = TEMPLATES.joinpath("monitor.yml").read_text(encoding="utf-8")
    assert "uv run agent monitor" in text
    names = {cmd.name for cmd in agent_app.registered_commands}
    assert "monitor" in names


# --- permissions / concurrency ---


@pytest.mark.unit
def test_missing_permissions_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    path = root / "templates" / "schedule" / "monitor.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace("permissions:\n  contents: read\n  issues: write\n", "")
    path.write_text(text, encoding="utf-8")
    assert any("permissions" in m for m in _errors(root))


@pytest.mark.unit
def test_missing_concurrency_is_info(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    path = root / "templates" / "schedule" / "monitor.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace("concurrency:\n  group: agent-monitor-routine\n  cancel-in-progress: false\n", "")
    path.write_text(text, encoding="utf-8")
    problems = schedule_lint.run_checks(root)
    infos = [p.message for p in problems if p.level == "info"]
    errors = [p.message for p in problems if p.level == "error"]
    assert any("concurrency" in m for m in infos)
    assert not any("concurrency" in m for m in errors)


# --- profile 結線 ---


@pytest.mark.unit
def test_agent_profile_includes_schedule_lint() -> None:
    from harness.agent.profile import PROFILE

    assert schedule_lint.run_checks in PROFILE.pm_checks
