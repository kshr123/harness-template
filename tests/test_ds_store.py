"""store の照会口 fingerprint_of のテスト（保存済み指紋を再保存せずに引く）。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import polars as pl
import pytest

from harness.ds import store

pytestmark = pytest.mark.integration

_SCHEMA = {
    "id": "folds",
    "description": "fold 割当",
    "layer": "split",
    "scope": "project",
    "primary_key": ["id"],
    "columns": [
        {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
        {"name": "fold", "dtype": "Int64", "nullable": False},
    ],
}


def test_fingerprint_of_none_before_save_and_matches_after(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    proj.add_schema(_SCHEMA)
    df = pl.DataFrame({"id": [0, 1, 2], "fold": [0, 1, 0]})

    assert store.fingerprint_of(proj.root, "folds") is None  # 未保存なら None
    saved = store.save(proj.root, df, "folds")
    assert store.fingerprint_of(proj.root, "folds") == saved  # 保存後は save の返り値と一致
