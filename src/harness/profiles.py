"""プロファイル（中核への上乗せ）の登録機構。

中核（pm・issues・checks）はプロファイルのコードを import しない。.harness/config.toml の
`profiles`（モジュールパスの一覧・例 `["harness.ds"]`）を読み、各モジュールが公開する
`PROFILE` を集めて検査に繋ぐ。非 DS の案件は profiles を空にする（または行ごと消す）だけで
DS の検査が外れる（checks.py の手動編集は不要・DEC-0004 のプロファイル境界）。
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from harness import pm
from harness.config import load_config

# プロジェクト管理の検査の型（root を受けて指摘の一覧を返す）。checks.py もこれを使う。
PmCheck = Callable[[Path], list[pm.Problem]]


@dataclass(frozen=True)
class Profile:
    """プロファイルの宣言。各プロファイルはモジュール直下に `PROFILE` として 1 つ公開する。"""

    name: str
    pm_checks: tuple[PmCheck, ...] = ()


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
