"""変更に応じたスコープ振り分け（`harness.scope.route`）のテスト。

期待値は「どのファイルを変えたか」から導く（振り分けは git に依存しない純粋関数）。プロファイルの写像は
実リポの durable な構造（`src/harness/<profile>/profile.py`）から取る＝可変領域ではない。核の主張は
「分類できない・検査インフラ・中核の変更は全実行に落ちる（fail-closed）／散文だけなら不変条件のみ」。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import scope

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]


def test_docs_only_runs_invariants_only() -> None:
    # 散文だけ＝不変条件のみ（ruff も mypy も pytest も Chrome も回さない）。
    plan = scope.route(REPO, ["docs/serve.md", "README.md", ".claude/skills/verify/SKILL.md", "work/EP-1/item.md"])
    assert not plan.full
    assert not plan.run_ruff and not plan.run_mypy
    assert plan.pytest_files == ()


def test_empty_diff_runs_invariants_only() -> None:
    plan = scope.route(REPO, [])
    assert not plan.full and not plan.run_ruff and not plan.run_mypy and plan.pytest_files == ()


def test_verification_infrastructure_forces_full() -> None:
    # スコープの土台を触ったらスコープで判断できない＝全実行に落とす。
    for f in (
        "checks.toml",
        "pyproject.toml",
        "uv.lock",
        "tests/conftest.py",
        "tests/_headless.py",
        "src/harness/checks.py",
        "src/harness/scope.py",
        "src/harness/profiles.py",
        ".harness/config.toml",
        ".github/workflows/ci.yaml",
    ):
        assert scope.route(REPO, [f]).full, f


def test_core_source_forces_full() -> None:
    # src/harness/*.py（直下）は全プロファイルが import する中核＝全実行。
    assert scope.route(REPO, ["src/harness/pm.py"]).full


def test_unclassified_source_forces_full() -> None:
    # プロファイルにも中核にも当たらない .py は安全側で全実行（fail-closed の過近似）。
    assert scope.route(REPO, ["src/harness/ds/models.py", "src/weird/other.py"]).full


def test_profile_source_scopes_to_that_profile() -> None:
    # ds のソース変更 → ruff+mypy＋ds のテストだけ（全実行にはしない・Chrome も deliver でなければ回さない）。
    plan = scope.route(REPO, ["src/harness/ds/models.py"])
    assert not plan.full
    assert plan.run_ruff and plan.run_mypy
    assert plan.pytest_files, "ds のテストが選ばれていない"
    assert "tests/test_ds_models.py" in plan.pytest_files
    assert all(f.startswith("tests/") for f in plan.pytest_files)


def test_profile_test_file_scopes_to_that_profile() -> None:
    plan = scope.route(REPO, ["tests/test_ds_models.py"])
    assert not plan.full and plan.run_mypy
    assert "tests/test_ds_models.py" in plan.pytest_files


def test_non_profile_test_file_runs_just_that_file() -> None:
    # 中核テスト（どのプロファイルも所有しない）は、その 1 本だけ回す。
    plan = scope.route(REPO, ["tests/test_doclint.py"])
    assert not plan.full and plan.run_ruff and plan.run_mypy
    assert plan.pytest_files == ("tests/test_doclint.py",)


def test_core_source_wins_over_docs() -> None:
    # 混在（散文＋中核）でも中核が勝って全実行。
    assert scope.route(REPO, ["docs/serve.md", "src/harness/pm.py"]).full


def test_python_under_prose_dirs_is_not_prose() -> None:
    # templates/** や work/**/code の .py は実行コード＝散文扱いにしない（ruff/型/テストの対象なので全実行に落とす）。
    assert scope.route(REPO, ["templates/serve/app.py"]).full
    assert scope.route(REPO, ["work/EP-1/code/train.py"]).full
