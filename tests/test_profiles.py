"""プロファイル登録機構（harness.profiles）のテスト。

中核はプロファイルを import せず、.harness/config.toml の profiles（モジュールパスの一覧）から
各モジュールの PROFILE を集める。このリポジトリは profiles = ["harness.ds"] なので、
DS プロファイル（data_lint）が載ることを固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import profiles

pytestmark = pytest.mark.unit


def test_load_profiles_returns_ds_profile_for_this_repo() -> None:
    # このリポジトリの config は profiles = ["harness.ds", "harness.serve", "harness.agent"]。3 つとも載る。
    root = Path(__file__).resolve().parents[1]
    loaded = profiles.load_profiles(root)
    assert [p.name for p in loaded] == ["ds", "serve", "agent"]
    from harness.agent import lint as agent_lint
    from harness.ds import schema
    from harness.serve import deploy_lint

    by_name = {p.name: p for p in loaded}
    assert schema.data_lint in by_name["ds"].pm_checks  # テーブル定義の検査が verify に繋がる
    assert deploy_lint.run_checks in by_name["serve"].pm_checks  # 配信テンプレートの構造 lint が繋がる
    assert agent_lint.run_checks in by_name["agent"].pm_checks  # エージェント宣言の構造 lint が繋がる


def test_empty_profiles_means_core_only(tmp_path: Path) -> None:
    # config が無い（＝profiles 既定は空）なら中核のみ。非 DS の案件はこの状態で動く。
    assert profiles.load_profiles(tmp_path) == []


def test_bogus_profile_module_raises_clear_error(tmp_path: Path) -> None:
    # 存在しないモジュールを指したら、どのプロファイルが悪いか名指しで失敗する。
    cfg = tmp_path / ".harness" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('profiles = ["harness.no_such_profile"]\n', encoding="utf-8")
    with pytest.raises(ImportError, match="harness.no_such_profile"):
        profiles.load_profiles(tmp_path)


def test_module_without_profile_raises_clear_error(tmp_path: Path) -> None:
    # 実在するが PROFILE を持たないモジュールを指したら、そのモジュール名で明示的に失敗する。
    cfg = tmp_path / ".harness" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('profiles = ["harness.pm"]\n', encoding="utf-8")
    with pytest.raises(ImportError, match="harness.pm"):
        profiles.load_profiles(tmp_path)
