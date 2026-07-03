"""合成データの生成と固定分割（データ漏れの防止）。

- 外部ダウンロードに頼らず、決め打ちの種から再現できる合成データを作る（どの手元でも同じ結果）。
- 分割は「行ごとの安定した鍵（id のハッシュ）」で決める。行の順序やデータ量が変わっても各行の所属は動かない。
  同じ入力・同じ salt なら必ず同じ分割になり、3つの分割に同じ行は重複しない（各 id は1つの分割だけ）。
- 分割の割合（valid_pct・test_pct）は引数で外から与える。案件ごとに変えてよい（コードに固定しない）。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

SPLITS = ("train", "valid", "test")

DataSource = Callable[..., pl.DataFrame]


def generate_synthetic(n: int = 2000, seed: int = 0) -> pl.DataFrame:
    """決め打ちの種から二値分類の合成データを作る（同じ種なら必ず同じデータ）。

    x1・x2 から線形の規則＋雑音でラベル y を決める。学習可能だが完全には当てられない難度にしてある。
    """
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    noise = rng.normal(scale=0.5, size=n)
    logit = 1.5 * x1 - 2.0 * x2 + noise
    y = (logit > 0.0).astype("int64")
    return pl.DataFrame(
        {
            "id": np.arange(n, dtype="int64"),
            "x1": x1,
            "x2": x2,
            "y": y,
        }
    )


def _synthetic_source(root: Path, *, n: int, seed: int, **_ignored: Any) -> pl.DataFrame:  # noqa: ANN401
    """合成データ（デモ・雛形の既定）。n 件を seed で決定的に生成する。config: {kind: synthetic}。"""
    return generate_synthetic(n=n, seed=seed)


def _table_source(root: Path, *, table_id: str, **_ignored: Any) -> pl.DataFrame:  # noqa: ANN401
    """store の保存済みテーブルを table_id で読む（実データの実験用）。config: {kind: table, table_id: <ID>}。"""
    from harness.ds import store

    df: pl.DataFrame = store.load(root, table_id)  # store.load は Any 返し＝明示的に受ける
    return df


# config の data 節 kind → 入力の作り方。実データを足すときはここに 1 行（例：CSV/DB 直結）。
DATA_SOURCES: dict[str, DataSource] = {
    "synthetic": _synthetic_source,
    "table": _table_source,
}


def load_dataset(root: Path, spec: Mapping[str, Any], *, n: int, seed: int) -> pl.DataFrame:
    """config の data 節（{kind, ...params}）から実験の入力 DataFrame を得る。

    kind 未指定は synthetic（雛形がそのまま動く）。n・seed は synthetic のときだけ効く
    （table のときは無視され table_id で読む）。kind は `uv run data list`（table）等から選ぶ。
    """
    kind = spec.get("kind", "synthetic")
    if kind not in DATA_SOURCES:
        raise ValueError(f"未知のデータ源 '{kind}'（{sorted(DATA_SOURCES)} のいずれか）")
    # n・seed は明示引数で渡す（実験の規模・種は top-level が持つ）。data 節に n/seed を書いても重複させない。
    params = {k: v for k, v in spec.items() if k not in ("kind", "n", "seed")}
    return DATA_SOURCES[kind](root, n=n, seed=seed, **params)


def _bucket(id_value: int, salt: str) -> int:
    """id を 0〜99 の安定したバケットに落とす（salt を変えると分割をやり直せる）。"""
    digest = hashlib.sha256(f"{salt}:{id_value}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


def fixed_split(
    df: pl.DataFrame,
    salt: str = "v1",
    *,
    valid_pct: int = 20,
    test_pct: int = 20,
) -> dict[str, pl.DataFrame]:
    """id の安定したハッシュで train/valid/test に固定分割する。

    - test：バケットが [0, test_pct)
    - valid：バケットが [test_pct, test_pct + valid_pct)
    - train：残り
    構成上、各 id はちょうど1つの分割に入る（重複しない）。同じ入力・同じ salt なら必ず同じ結果。
    """
    if valid_pct < 0 or test_pct < 0 or valid_pct + test_pct >= 100:
        raise ValueError("valid_pct・test_pct は 0 以上で、合計は 100 未満にすること")

    buckets = np.array([_bucket(int(i), salt) for i in df["id"].to_list()], dtype="int64")
    df = df.with_columns(pl.Series("_bucket", buckets))
    test = df.filter(pl.col("_bucket") < test_pct)
    valid = df.filter((pl.col("_bucket") >= test_pct) & (pl.col("_bucket") < test_pct + valid_pct))
    train = df.filter(pl.col("_bucket") >= test_pct + valid_pct)
    return {name: part.drop("_bucket") for name, part in (("train", train), ("valid", valid), ("test", test))}
