"""データ基盤のテスト：合成データの再現性と、固定分割のデータ漏れ防止。

作る側（ds.data）と確かめる側（このテスト）を分け、再現性・重複なし・網羅を機械で保証する。
"""

from __future__ import annotations

import polars as pl
import pytest

from harness.ds import data

pytestmark = pytest.mark.unit


def test_generate_is_reproducible() -> None:
    # 同じ種なら必ず同じデータ（再現性）。
    assert data.generate_synthetic(n=500, seed=0).equals(data.generate_synthetic(n=500, seed=0))
    # 違う種なら中身が変わる。
    assert not data.generate_synthetic(n=500, seed=0).equals(data.generate_synthetic(n=500, seed=1))


def test_fixed_split_is_deterministic() -> None:
    df = data.generate_synthetic(n=1000, seed=0)
    a = data.fixed_split(df)
    b = data.fixed_split(df)
    for name in data.SPLITS:
        assert a[name].equals(b[name])


def test_splits_do_not_overlap_and_cover_all() -> None:
    df = data.generate_synthetic(n=1000, seed=0)
    parts = data.fixed_split(df)
    ids = {name: set(parts[name]["id"].to_list()) for name in data.SPLITS}
    # 3つの分割に同じ id が重複しない（データ漏れの防止）。
    assert ids["train"].isdisjoint(ids["valid"])
    assert ids["train"].isdisjoint(ids["test"])
    assert ids["valid"].isdisjoint(ids["test"])
    # すべての行がどれかの分割に入る（取りこぼしなし）。
    assert ids["train"] | ids["valid"] | ids["test"] == set(df["id"].to_list())


def test_split_assignment_is_stable_when_rows_added() -> None:
    # データ量が増えても、既存の行の所属は動かない（id ごとの安定した鍵で決めているため）。
    small = data.generate_synthetic(n=500, seed=0)
    large = data.generate_synthetic(n=1000, seed=0)
    small_parts = data.fixed_split(small)
    large_parts = data.fixed_split(large)
    small_ids = pl.concat([small_parts["test"]])["id"].to_list()
    large_test_ids = set(large_parts["test"]["id"].to_list())
    for i in small_ids:
        assert i in large_test_ids
