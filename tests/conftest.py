"""テスト共通の下ごしらえ（フィクスチャ）。

一時プロジェクト（`.harness/config.toml`・テーブル定義YAML・`work/` の作業単位）を組み立てる工場を提供する。
実データやサーバは使わない（ローカル完結）。テストに書く数値は、ここで作るテストデータの構成から
導出できるものだけにする（実装の出力をコピーした固定値は書かない）。
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import frontmatter
import pytest
import yaml

from harness import profiles
from harness.testing import check_collected_items

# Windows のコンソール（cp932）でも、**この**テストプロセスが日本語・記号の検査文言を素直に出せるよう
# utf-8 に固定する（cli.py と同じ作法）。対象は当プロセスの実端末出力だけ（capture 下では reconfigure を
# 持たない stream もあるので getattr で守る＝その場合は何もしない no-op）。
# 注意：これは pytester が起こす**別プロセス**には届かない。サブプロセスの日本語出力を親テストが utf-8 で
# 読めるようにするのは test_conventions の PYTHONUTF8=1 フィクスチャの役目（CI で実測して分けた）。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8")

# T-0202: pytester フィクスチャ（自分の collect フックを実テストで確かめる pytest 標準ツール）を有効化する。
# 既定は無効なので、root の conftest.py で明示的に opt-in する必要がある。
pytest_plugins = ["pytester"]

# T-0192: テストをプロファイルの持ち物にする。無効なプロファイル（.harness/config.toml の profiles に
# 載っていない＝そのプロファイルの optional 依存が入っていない）が所有するテストを収集から外す。
# 非 DS の案件（profiles=[]）は polars・fastapi 等が無くても pytest 収集が通る（トップレベル import で 45 errors
# にならない）。当リポは全プロファイル有効なので除外は空＝全テストが従来どおり収集される。ファイルは移動・改名
# しない（work/ の verified_by 参照を壊さない）＝所有は Profile.test_globs の宣言だけで表す。
_REPO_ROOT = Path(__file__).resolve().parents[1]
collect_ignore_glob = sorted(
    {glob for profile in profiles.disabled_profiles(_REPO_ROOT) for glob in profile.test_globs}
)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """収集フック。論理の正本は harness.testing.check_collected_items（T-0210）＝ここは委譲だけ。

    -m の絞り込みより先に（tryfirst）全収集テストを見て、選ばれる段階に関わらず付け忘れ／理由の無い
    skip・slow を止める。抽出や判定をここに書き足さない（テスト側に写しを作ると、本体が退化しても
    写しを守るテストが緑のまま通ってしまう）。中身の説明は check_collected_items の docstring を見る。
    """
    check_collected_items(items)


# 既定の置き場設定（ローカルのみ）。config.py の既定と同じ形にしておく。
DEFAULT_CONFIG = """\
[data]
default_backend = "local"

[data.backends.local]
uri = "file:data"

[data.layer]

[issues]
backend = "file:issues"

[metadata]
uri = "file:docs/data"
"""


def _write_item(path: Path, meta: Mapping[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body)
    post.metadata.update(dict(meta))
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


class Project:
    """組み立てた一時プロジェクトの根（root）と、中身を後から足す手当て。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def add_item(self, rel: str, meta: Mapping[str, Any], body: str = "") -> Path:
        """作業単位（frontmatter 付き .md）を書く。rel は work/ からでなく root からの相対。"""
        path = self.root / rel
        _write_item(path, meta, body)
        return path

    def add_schema(self, table: Mapping[str, Any], *, scope_dir: str = "docs/data") -> Path:
        """テーブル定義 YAML を書く（既定は共有スコープ docs/data）。"""
        path = self.root / scope_dir / f"{table['id']}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(dict(table), allow_unicode=True, sort_keys=False), encoding="utf-8")
        return path

    def add_file(self, rel: str, content: str) -> Path:
        """任意のファイル（テスト本体・結果記録など）を書く。"""
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


@pytest.fixture(autouse=True)
def _clear_shadow_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """SERVE_SHADOW_* が開発者シェルに残っていても serve テストを汚染しないよう既定で落とす（T-0113）。"""
    for var in ("SERVE_SHADOW_NAME", "SERVE_SHADOW_WORK", "SERVE_SHADOW_VERSION"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def make_project(tmp_path: Path) -> Callable[..., Project]:
    """一時プロジェクトを作る工場。呼ぶたびに tmp_path 下の別ディレクトリに作る（複数作っても衝突しない）。"""
    counter = {"n": 0}

    def _make(*, config: str | None = DEFAULT_CONFIG) -> Project:
        counter["n"] += 1
        root = tmp_path / f"proj{counter['n']}"
        (root / "work").mkdir(parents=True, exist_ok=True)
        if config is not None:
            cfg = root / ".harness" / "config.toml"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(config, encoding="utf-8")
        return Project(root)

    return _make
