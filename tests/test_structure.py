"""この開発基盤の新構造（1リポジトリ＝1案件）が保たれているかの自己テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_new_structure_layout() -> None:
    # 案件レベルの文書は docs/、課題は issues/、置き場切り替えは .harness/config.toml。
    assert Path("docs/charter.md").is_file()
    assert Path("docs/requirements").is_dir()
    assert Path("docs/data").is_dir()
    assert Path("docs/decisions").is_dir()
    assert Path("issues").is_dir()
    assert Path(".harness/config.toml").is_file()
    # projects/ の層は廃止した。
    assert not Path("projects").exists()
