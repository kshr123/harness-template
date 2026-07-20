"""プロファイル（中核への上乗せ）の登録機構。

中核（pm・issues・checks）はプロファイルのコードを import しない。.harness/config.toml の
`profiles`（モジュールパスの一覧・例 `["harness.ds"]`）を読み、各モジュールが公開する
`PROFILE` を集めて検査に繋ぐ。非 DS の案件は profiles を空にする（または行ごと消す）だけで
DS の検査が外れる（checks.py の手動編集は不要のプロファイル境界）。
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from harness import pm
from harness.config import load_config

# プロジェクト管理の検査の型（root を受けて指摘の一覧を返す）。checks.py もこれを使う。
PmCheck = Callable[[Path], list[pm.Problem]]


@dataclass(frozen=True)
class Profile:
    """プロファイルの宣言。各プロファイルはモジュール直下に `PROFILE` として 1 つ公開する。

    検査（`pm_checks`）だけでなく、そのプロファイルが所有するテスト（`test_globs`＝tests/ からの glob）も
    同じ宣言に束ねる。非 DS の案件（`profiles = []`）では、無効なプロファイルの `test_globs` を
    収集除外（tests/conftest.py の collect_ignore_glob）と mypy の対象除外（checks.py）が使い、optional 依存
    （polars・fastapi 等）を import するテスト・ソースを収集/型検査から外す。持ち物は 1 か所（この宣言）に
    集める＝2 つ目の台帳を作らない（pm_checks と同じ束ね方）。"""

    name: str
    pm_checks: tuple[PmCheck, ...] = ()
    # このプロファイルが所有するテストファイル（tests/ からの glob）。無効時に収集・型検査から外す集合。
    test_globs: tuple[str, ...] = ()


def load_profiles(root: Path) -> list[Profile]:
    """config の profiles に列挙されたモジュールを import し、各 PROFILE を集める。

    import できない・PROFILE が無い場合は、どのプロファイルが悪いかを名指しで失敗にする
    （黙って検査が抜け落ちるのを防ぐ）。
    """
    result: list[Profile] = []
    for module_path in load_config(root).profiles:
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise ImportError(
                f"プロファイル '{module_path}' を import できない（.harness/config.toml の profiles を確認）: {exc}"
            ) from exc
        profile = getattr(module, "PROFILE", None)
        if not isinstance(profile, Profile):
            raise ImportError(f"プロファイル '{module_path}' がモジュール直下に PROFILE を公開していない")
        result.append(profile)
    return result


def discover_profiles(root: Path) -> dict[str, Profile]:
    """このリポに同梱された全プロファイル候補（`src/harness/<name>/profile.py` を持つ）を集める。

    `load_profiles` は config の `profiles` に**載っている**（有効な）ものだけを返すのに対し、これは有効・無効を
    問わず候補すべてを返す（module_path→PROFILE）。無効なプロファイルの持ち物（テスト・ソース）を、収集除外や
    mypy の対象除外が知るために使う。プロファイルのモジュールは軽い（重い依存を top で import しない規約＝
    test_ops_profile 等で固定）ので、extra 未導入の環境でも import できる。
    """
    result: dict[str, Profile] = {}
    pkg_dir = root / "src" / "harness"
    for profile_py in sorted(pkg_dir.glob("*/profile.py")):
        module_path = f"harness.{profile_py.parent.name}"
        module = importlib.import_module(module_path)
        profile = getattr(module, "PROFILE", None)
        if isinstance(profile, Profile):
            result[module_path] = profile
    return result


def profile_names(root: Path) -> tuple[str, ...]:
    """同梱プロファイルの名前（`src/harness/<name>/profile.py` を持つディレクトリ名）を名前順で返す。

    import せずディレクトリ構造だけから導く（軽い・副作用なし）。プロファイル一覧を要する検査・散文が
    手書きの列挙でなくこの 1 か所から引くための単一の出どころ（`discover_profiles` は PROFILE を import して
    有効/無効を判定する用途で、名前だけならこの走査で足りる）。新しいプロファイルを足すと自動で集合に入る。
    """
    pkg_dir = root / "src" / "harness"
    if not pkg_dir.is_dir():
        return ()
    return tuple(sorted(p.parent.name for p in pkg_dir.glob("*/profile.py")))


def disabled_profiles(root: Path, enabled: Iterable[str] | None = None) -> list[Profile]:
    """同梱されているが有効化されていないプロファイル（＝ソースはあるが `profiles` に載っていない）。

    `enabled` を渡さなければ config（`.harness/config.toml` の profiles）から読む。渡せば、それを有効集合として
    使う（テストが config を組み立てずに判定を確かめられるように・全部入りの当リポでは空を返す）。
    """
    enabled_set = set(load_config(root).profiles if enabled is None else enabled)
    return [profile for module_path, profile in discover_profiles(root).items() if module_path not in enabled_set]
