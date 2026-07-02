"""置き場の切り替え設定のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from harness import config


def test_defaults_when_no_file(tmp_path: Path) -> None:
    c = config.load_config(tmp_path)
    assert c.data.default_backend == "local"
    assert c.data.uri_for("raw") == "file:data"
    assert c.issues.backend == "file:issues"
    assert c.metadata.uri == "file:docs/data"


def test_reads_file_and_layer_override(tmp_path: Path) -> None:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "config.toml").write_text(
        '[data]\ndefault_backend = "local"\n'
        '[data.backends.local]\nuri = "file:data"\n'
        '[data.backends.object]\nuri = "s3://b/p"\n'
        '[data.layer]\nraw = "object"\n'
        '[issues]\nbackend = "github:me/repo"\n',
        encoding="utf-8",
    )
    c = config.load_config(tmp_path)
    assert c.data.uri_for("raw") == "s3://b/p"  # 層の上書きが効く
    assert c.data.uri_for("processed") == "file:data"  # 上書きが無い層は既定
    assert c.issues.backend == "github:me/repo"


def test_broken_config_is_error(tmp_path: Path) -> None:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "config.toml").write_text("[data]\nunknown_field = 1\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        config.load_config(tmp_path)
