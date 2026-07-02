"""合成データの生成と固定分割（データ漏れの防止）。

- 外部ダウンロードに頼らず、決め打ちの種から再現できる合成データを作る（どの手元でも同じ結果）。
- 分割は「行ごとの安定した鍵（id のハッシュ）」で決める。行の順序やデータ量が変わっても各行の所属は動かない。
  同じ入力・同じ salt なら必ず同じ分割になり、3つの分割に同じ行は重複しない（各 id は1つの分割だけ）。
- 分割の割合（valid_pct・test_pct）は引数で外から与える。案件ごとに変えてよい（コードに固定しない）。
"""

from __future__ import annotations

import hashlib

import numpy as np
import polars as pl

SPLITS = ("train", "valid", "test")


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
