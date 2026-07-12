"""プロファイル登録機構（harness.profiles）のテスト。

中核はプロファイルを import せず、.harness/config.toml の profiles（モジュールパスの一覧）から各モジュールの
PROFILE を集める。テストはこのリポジトリの実状態（config の profiles 値）を仮定せず、tmp_path 上に組み立てた
config か、有効集合を明示引数で渡して確かめる（テンプレート自身の設定値をハードコードしない＝T-0191）。
同梱プロファイルの「所有物」（Profile.test_globs）は、ソースの実在から導ける集合として確かめる（T-0192）。
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import pytest

from harness import profiles

pytestmark = pytest.mark.unit

# このリポに同梱されているプロファイル（ソースの実在＝可変領域でない）。discover はこれ以上を返してよい
# （将来プロファイルが増えても壊れないよう >= で確かめる）。
_SHIPPED = {"harness.ds", "harness.serve", "harness.agent", "harness.ops"}


def _write_config(root: Path, body: str) -> Path:
    """tmp_path 上に .harness/config.toml を書いて root を返す（他テストと同じ組み立て方）。"""
    cfg = root / ".harness" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(body, encoding="utf-8")
    return root


def test_load_profiles_wires_declared_profile(tmp_path: Path) -> None:
    # 一時 config が profiles = ["harness.ds"] を宣言したら ds だけが載り、テーブル定義検査が pm_checks に繋がる。
    # 期待値は「宣言した profiles」から導出（このリポの config 値は見ない）。
    from harness.ds import schema

    root = _write_config(tmp_path, 'profiles = ["harness.ds"]\n')
    loaded = profiles.load_profiles(root)
    assert [p.name for p in loaded] == ["ds"]
    assert schema.data_lint in loaded[0].pm_checks  # テーブル定義の検査が verify に繋がる


def test_empty_profiles_means_core_only(tmp_path: Path) -> None:
    # config が無い（＝profiles 既定は空）なら中核のみ。非 DS の案件はこの状態で動く。
    assert profiles.load_profiles(tmp_path) == []


def test_bogus_profile_module_raises_clear_error(tmp_path: Path) -> None:
    # 存在しないモジュールを指したら、どのプロファイルが悪いか名指しで失敗する。
    root = _write_config(tmp_path, 'profiles = ["harness.no_such_profile"]\n')
    with pytest.raises(ImportError, match="harness.no_such_profile"):
        profiles.load_profiles(root)


def test_module_without_profile_raises_clear_error(tmp_path: Path) -> None:
    # 実在するが PROFILE を持たないモジュールを指したら、そのモジュール名で明示的に失敗する。
    root = _write_config(tmp_path, 'profiles = ["harness.pm"]\n')
    with pytest.raises(ImportError, match="harness.pm"):
        profiles.load_profiles(root)


# --- 同梱プロファイルの発見と「無効なプロファイル」の判定（収集除外・mypy 除外の土台＝T-0192） ---


def test_discover_finds_shipped_profiles() -> None:
    # discover は config と無関係に src/harness/<name>/profile.py を持つ候補を全部返す（有効・無効を問わない）。
    root = Path(__file__).resolve().parents[1]
    discovered = profiles.discover_profiles(root)
    assert set(discovered) >= _SHIPPED
    assert all(name == discovered[f"harness.{name}"].name for name in ("ds", "serve", "agent", "ops"))


def test_disabled_profiles_is_shipped_minus_enabled() -> None:
    # enabled を明示すれば config を組み立てず判定できる。無効集合＝同梱 − 有効。
    root = Path(__file__).resolve().parents[1]
    shipped = {f"harness.{p.name}" for p in profiles.discover_profiles(root).values()}
    # 全部有効 → 無効は空（全プロファイル有効な当リポの verify と同じ状態＝除外なし）。
    assert profiles.disabled_profiles(root, enabled=shipped) == []
    # profiles=[] → 同梱プロファイルが全部「無効」＝それらのテストが収集・型検査から外れる対象になる。
    disabled = {f"harness.{p.name}" for p in profiles.disabled_profiles(root, enabled=[])}
    assert disabled == shipped
    # ds だけ有効 → 残りが無効。
    only_ds = {f"harness.{p.name}" for p in profiles.disabled_profiles(root, enabled=["harness.ds"])}
    assert "harness.ds" not in only_ds
    assert only_ds == shipped - {"harness.ds"}


def test_ds_profile_owns_its_optional_dependency_tests() -> None:
    # DS 依存（polars 等）をトップで import するテスト（素の uv sync では収集で ImportError になる代表例）を、
    # ds プロファイルが所有すること。この集合は「素の環境で収集が落ちるファイル」の実測から選んだ（T-0192 再現）。
    root = Path(__file__).resolve().parents[1]
    ds = profiles.discover_profiles(root)["harness.ds"]
    for name in (
        "test_ds_pipeline.py",
        "test_cli_predict.py",
        "test_forecast.py",
        "test_experiment_holdout.py",
        "test_promotion_characterization.py",
        "test_serve_app.py",
    ):
        assert any(fnmatch.fnmatch(name, glob) for glob in ds.test_globs), name


def test_stats_profile_shipped_and_owns_its_tests() -> None:
    # stats プロファイルが同梱され（ソースの実在）、test_stats_*.py を所有する。profiles=[] の複製では
    # この glob が収集除外・mypy 除外に載る（pymc を import する stats テストを素の環境から外す）。
    root = Path(__file__).resolve().parents[1]
    discovered = profiles.discover_profiles(root)
    assert "harness.stats" in discovered
    stats = discovered["harness.stats"]
    assert stats.name == "stats"
    assert any(fnmatch.fnmatch("test_stats_stack.py", glob) for glob in stats.test_globs)
    # profiles=[] なら stats は無効集合に入る＝そのテストが収集・型検査から外れる対象になる。
    disabled = {f"harness.{p.name}" for p in profiles.disabled_profiles(root, enabled=[])}
    assert "harness.stats" in disabled


def test_profile_test_globs_match_only_existing_files() -> None:
    # 所有 glob は実在するテストにだけ当たる（陳腐化検知：消えた/改名したテストを指す glob を error 化する）。
    tests_dir = Path(__file__).resolve().parent
    for module_path, profile in profiles.discover_profiles(tests_dir.parent).items():
        for glob in profile.test_globs:
            assert list(tests_dir.glob(glob)), f"{module_path} の test_globs {glob!r} に一致するテストが無い"
