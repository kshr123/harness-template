"""テスト共通の下ごしらえ（フィクスチャ）。

一時プロジェクト（`.harness/config.toml`・テーブル定義YAML・`work/` の作業単位）を組み立てる工場を提供する。
実データやサーバは使わない（ローカル完結）。テストに書く数値は、ここで作るテストデータの構成から
導出できるものだけにする（実装の出力をコピーした固定値は書かない）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import frontmatter
import pytest
import yaml

from harness.testing import unmarked


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """ピラミッドの目印（unit/integration/e2e）が無いテストは collect でエラーにする（迷子テストを塞ぐ）。

    -m の絞り込みより先に（tryfirst）全収集テストを見て、選ばれる段階に関わらず付け忘れを止める。
    """
    bad = unmarked((item.nodeid, {m.name for m in item.iter_markers()}) for item in items)
    if bad:
        raise pytest.UsageError("ピラミッドの目印(unit/integration/e2e)が無いテスト: " + ", ".join(bad))


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
