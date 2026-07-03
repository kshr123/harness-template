"""部品カタログ（BLOCKS/ENCODERS）の発見性の検査。

レジストリの全項目に説明文（docstring）があることを固定する。説明文が無い＝一覧に載れない
＝エージェントが元コードを読まずに使えない＝「部品は入口まで作って完了」（DEC-0009）に反する。
"""

from __future__ import annotations

import inspect

import pytest

from harness.cli import _data_blocks, _data_encoders
from harness.ds.features import BLOCKS
from harness.ds.pipeline import ENCODERS

pytestmark = pytest.mark.unit


def test_blocks_have_docstrings() -> None:
    for kind, cls in BLOCKS.items():
        assert inspect.getdoc(cls), f"BLOCKS['{kind}'] に docstring が無い（カタログに載れない）"


def test_encoders_have_docstrings() -> None:
    for kind, factory in ENCODERS.items():
        assert inspect.getdoc(factory), f"ENCODERS['{kind}'] に docstring が無い（カタログに載れない）"


def test_catalog_commands_run(capsys: pytest.CaptureFixture[str]) -> None:
    _data_blocks()
    _data_encoders()
    out = capsys.readouterr().out
    # レジストリの項目が一覧に出る（エージェントが1コマンドで発見できる）。
    assert "columns" in out
    assert "onehot" in out
    assert "target" in out
