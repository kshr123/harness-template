"""この開発基盤の新構造（1リポジトリ＝1案件）が保たれているかの自己テスト。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_new_structure_layout() -> None:
    # 案件レベルの文書は docs/、課題は issues/、置き場切り替えは .harness/config.toml。
    assert Path("docs/charter.md").is_file()
    assert Path("docs/requirements").is_dir()
    assert Path("docs/data").is_dir()
    assert Path("issues").is_dir()
    # docs/decisions/（決定記録 DEC）は EP-26 で廃止＝現在のルールに畳んだ（経緯は git）。
    assert Path(".harness/config.toml").is_file()
    # projects/ の層は廃止した。
    assert not Path("projects").exists()


# templates/ 直下の資産（ディレクトリ）→ それを腐らせない検査のオーナー（モジュール参照 or テストファイル）。
# 資産を足したらこの表にも 1 行足す（T-0137＝ラチェット）。値＝(オーナー参照, 理由)。
# coverage_lint._EXEMPT・ci_lint._WORKFLOWS と同型（理由必須・fail closed）。
_TEMPLATE_OWNERS: dict[str, tuple[str, str]] = {
    "ci": ("harness.ops.ci_lint", "CI/verify 雛形の構造検査"),
    "schedule": ("harness.agent.schedule_lint", "定期実行雛形の構造検査"),
    "serve": ("harness.serve.deploy_lint", "配信雛形の構造検査"),
    "experiment": ("tests/test_e2e_experiment.py", "実験雛形の実行スモーク"),
}


@pytest.mark.unit
def test_templates_have_owner_checks() -> None:
    # リポ根（test_new_structure_layout に倣う：pytest はリポ根から実行される想定）。
    root = Path.cwd()
    templates_dir = root / "templates"

    actual = {d.name for d in templates_dir.iterdir() if d.is_dir()}
    expected = set(_TEMPLATE_OWNERS)

    unregistered = actual - expected
    missing_assets = expected - actual
    assert not unregistered and not missing_assets, (
        "templates/ の資産集合とオーナー表 _TEMPLATE_OWNERS のキー集合が不一致。"
        f" 未登録ディレクトリ（オーナーを足すこと）: {sorted(unregistered)}。"
        f" 表にあるが実体が無い（削除の取り残し）: {sorted(missing_assets)}。"
    )

    for name, (ref, reason) in _TEMPLATE_OWNERS.items():
        assert reason.strip(), f"_TEMPLATE_OWNERS[{name!r}] の理由が空。オーナーには人が読める理由が必須"
        if ref.startswith("harness."):
            assert importlib.util.find_spec(ref) is not None, (
                f"_TEMPLATE_OWNERS[{name!r}] のオーナー参照 {ref!r} が import できない（腐り検知）"
            )
        else:
            assert ref.startswith("tests/") and ref.endswith(".py"), (
                f"_TEMPLATE_OWNERS[{name!r}] のオーナー参照 {ref!r} は harness.* か tests/*.py のどちらでもない"
            )
            assert (root / ref).is_file(), f"_TEMPLATE_OWNERS[{name!r}] のオーナー参照 {ref!r} が存在しない（腐り検知）"
