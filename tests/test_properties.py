"""property テスト（hypothesis）：核の性質を広い入力で固定する（例示テストの補完）。

- passes の fail-closed（NaN は向きによらず必ず不合格・有限値は向きどおり）
- psi の非負・同一分布 ≈ 0・平行移動で増える（2 点比較の弱い単調性）
- fixed_split の決定性・被覆と排他・行順への不変性
- fold 被覆（全行がちょうど 1 回 valid＝oof_mask 全 True 相当。層化あり/なし）
- エンコーダ不変量（scale：NaN 無し・平均≈0・分散≈1／missing_flags：0/1 のみ・NaN 位置と一致）

乱数は hypothesis が管理（derandomize=True で決定的）。期待値は性質（不変条件）そのもので、実装出力のコピーは無い。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import polars as pl
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from harness.ds import cv, data
from harness.ds.eda import psi
from harness.ds.eval import passes
from harness.ds.pipeline import ENCODERS

pytestmark = pytest.mark.unit

# 有限 float（NaN・inf を含めない側の入力）。psi・scale 用は桁を抑えて浮動小数の桁落ちを性質と混ぜない。
_finite = st.floats(allow_nan=False, allow_infinity=False, width=64)
_moderate = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, width=64)
_salt = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", max_size=12)


# ---------------------------------------------------------------- passes（fail-closed）
@given(limit=_finite, a=_finite, b=_finite)
@settings(deadline=None, derandomize=True, max_examples=100)
def test_passes_nan_is_always_fail_closed(limit: float, a: float, b: float) -> None:
    # NaN はどんな閾値・どちらの向き（roc_auc=大きいほど良い / log_loss=小さいほど良い）でも必ず不合格。
    for name in ("roc_auc", "log_loss"):
        assert passes({name: float("nan")}, {name: limit}) is False
    # 他の指標が確実に合格でも、NaN が 1 つあれば全体は不合格（素通りしない）。
    value, threshold = min(a, b), max(a, b)  # log_loss は value <= threshold で必ず合格の組
    metrics = {"roc_auc": float("nan"), "log_loss": value}
    assert passes(metrics, {"roc_auc": limit, "log_loss": threshold}) is False
    # 測っていない指標（metrics に無い名前）も不合格＝満たしたと見なさない。
    assert passes({}, {"roc_auc": limit}) is False


@given(value=_finite, limit=_finite)
@settings(deadline=None, derandomize=True, max_examples=100)
def test_passes_finite_values_follow_metric_direction(value: float, limit: float) -> None:
    # 有限値なら合否は向きどおり：higher_is_better（roc_auc）は >=・lower（log_loss）は <=。
    assert passes({"roc_auc": value}, {"roc_auc": limit}) is (value >= limit)
    assert passes({"log_loss": value}, {"log_loss": limit}) is (value <= limit)


# ---------------------------------------------------------------- psi（非負・同一分布 0・移動で増える）
@given(
    train=st.lists(_moderate, min_size=1, max_size=200),
    test=st.lists(_moderate, min_size=1, max_size=200),
    bins=st.integers(min_value=2, max_value=20),
)
@settings(deadline=None, derandomize=True, max_examples=100)
def test_psi_is_nonnegative(train: list[float], test: list[float], bins: int) -> None:
    value = psi(pl.Series("v", train, dtype=pl.Float64), pl.Series("v", test, dtype=pl.Float64), bins=bins)
    assert math.isfinite(value)
    assert value >= 0.0


@given(values=st.lists(_moderate, min_size=5, max_size=200, unique=True))
@settings(deadline=None, derandomize=True, max_examples=100)
def test_psi_zero_on_identity_and_grows_when_shifted(values: list[float]) -> None:
    # 同一配列同士は PSI ≈ 0。全幅より大きく平行移動（全質量が train の最大より右へ）すると必ず増える（2 点比較）。
    s = pl.Series("v", values, dtype=pl.Float64)
    same = psi(s, s)
    shift = (max(values) - min(values)) + 1.0
    moved = pl.Series("v", [v + shift for v in values], dtype=pl.Float64)
    assert same <= 1e-12
    assert psi(s, moved) > same


# ---------------------------------------------------------------- fixed_split（決定性・被覆と排他）
@given(
    ids=st.lists(st.integers(min_value=-(2**62), max_value=2**62), min_size=1, max_size=300, unique=True),
    salt=_salt,
    pcts=st.tuples(st.integers(0, 60), st.integers(0, 60)).filter(lambda t: t[0] + t[1] < 100),
)
@settings(deadline=None, derandomize=True, max_examples=100)
def test_fixed_split_is_deterministic_partition(ids: list[int], salt: str, pcts: tuple[int, int]) -> None:
    valid_pct, test_pct = pcts
    df = pl.DataFrame({"id": pl.Series(ids, dtype=pl.Int64)})
    first = data.fixed_split(df, salt, valid_pct=valid_pct, test_pct=test_pct)
    second = data.fixed_split(df, salt, valid_pct=valid_pct, test_pct=test_pct)
    # 決定的：同じ入力・同じ salt なら 2 回とも完全一致。
    for name in data.SPLITS:
        assert first[name].equals(second[name])
    # 被覆と排他：サイズの合計 = 全行、かつ id の和集合 = 全 id ⇒ 各行がちょうど 1 つの分割に入る。
    parts = {name: set(first[name]["id"].to_list()) for name in data.SPLITS}
    assert sum(first[name].height for name in data.SPLITS) == len(ids)
    assert set().union(*parts.values()) == set(ids)
    # 行の順序に依らない：逆順の df でも各 id の所属は同じ（安定分割の核）。
    reversed_split = data.fixed_split(df.reverse(), salt, valid_pct=valid_pct, test_pct=test_pct)
    assert {name: set(reversed_split[name]["id"].to_list()) for name in data.SPLITS} == parts
    # 公開契約どおりの所属：test=[0,test_pct)・valid=[test_pct,+valid_pct)・train=残り（_bucket と pct を照合）。
    # 決定性・被覆だけでは「全 train の定数分割」「salt/pct 無視」変異が通ってしまうため、所属そのものを固定する。
    for name, id_set in parts.items():
        for i in id_set:
            b = data._bucket(i, salt)
            expected = "test" if b < test_pct else ("valid" if b < test_pct + valid_pct else "train")
            assert name == expected, f"id {i}（bucket {b}）は {expected} のはずが {name}"


@given(
    ids=st.lists(st.integers(min_value=-(2**63), max_value=2**63 - 1), min_size=20, max_size=60, unique=True),
    salts=st.tuples(_salt, _salt).filter(lambda t: t[0] != t[1]),
)
@settings(deadline=None, derandomize=True, max_examples=60)
def test_bucket_range_deterministic_and_salt_sensitive(ids: list[int], salts: tuple[str, str]) -> None:
    salt_a, salt_b = salts
    for i in ids:
        bucket = data._bucket(i, salt_a)
        assert 0 <= bucket < 100  # 範囲：複数 id を引くことで % 101 等の範囲外変異を踏む確率を上げる
        assert data._bucket(i, salt_a) == bucket  # 決定的（同じ id・salt なら同じ）
    # salt 感度：salt を変えれば少なくとも 1 つの id のバケットが変わる（20+ id で偶然全一致はほぼ 0）。
    # 「salt 無視」「定数を返す」変異はここで反例になる（範囲・決定性だけでは通ってしまう）。
    assert any(data._bucket(i, salt_a) != data._bucket(i, salt_b) for i in ids)


# ---------------------------------------------------------------- fold 被覆（全行がちょうど 1 回 valid）
@given(
    n=st.integers(min_value=12, max_value=80),
    n_folds=st.integers(min_value=2, max_value=6),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    stratify=st.booleans(),
)
@settings(deadline=None, derandomize=True, max_examples=60)
def test_fold_indices_cover_every_row_exactly_once(n: int, n_folds: int, seed: int, stratify: bool) -> None:
    # n >= 12 >= 2*n_folds なので層化でも各クラス数 >= n_folds（StratifiedKFold の前提）を満たす。
    df = pl.DataFrame(
        {"id": np.arange(n, dtype=np.int64), "y": (np.arange(n, dtype=np.int64) % 2)}  # 2 クラスを交互に
    )
    folds = cv.make_folds(df, n_folds=n_folds, seed=seed, stratify_by="y" if stratify else None)
    pairs = cv.fold_indices(df, folds)
    assert len(pairs) == n_folds
    # 全 fold の valid を連結すると 0..n-1 の順列＝重複なし・漏れなし（oof_mask 全 True 相当）。
    all_valid = np.concatenate([valid for _, valid in pairs])
    assert np.array_equal(np.sort(all_valid), np.arange(n, dtype=np.int64))
    for train, valid in pairs:
        assert np.intersect1d(train, valid).size == 0  # train/valid は互いに素（リーク無し）
        assert np.array_equal(np.union1d(train, valid), np.arange(n, dtype=np.int64))  # 合わせて全行


# ---------------------------------------------------------------- エンコーダ不変量（scale・missing_flags）
@st.composite
def _matrix_with_nans(draw: st.DrawFn) -> NDArray[np.float64]:
    """(n_rows, n_cols) の float64 行列に NaN を混ぜて返す（縮退の除外は呼び手の assume で行う）。"""
    n_rows = draw(st.integers(min_value=4, max_value=30))
    n_cols = draw(st.integers(min_value=1, max_value=4))
    size = n_rows * n_cols
    values = draw(st.lists(st.floats(-100, 100, allow_nan=False, width=64), min_size=size, max_size=size))
    mask = draw(st.lists(st.booleans(), min_size=size, max_size=size))
    x = np.array(values, dtype=np.float64).reshape(n_rows, n_cols)
    x[np.array(mask, dtype=np.bool_).reshape(n_rows, n_cols)] = np.nan
    return x


@given(x=_matrix_with_nans())
@settings(deadline=None, derandomize=True, max_examples=60)
def test_scale_output_has_no_nan_and_is_standardized(x: NDArray[np.float64]) -> None:
    # 縮退（列が実質定数・観測 2 点未満）は対象外＝assume で除外。核の性質（NaN 無し・平均 0・分散 1）は緩めない。
    for j in range(x.shape[1]):
        finite = x[:, j][~np.isnan(x[:, j])]
        assume(finite.size >= 2)
        filled = np.where(np.isnan(x[:, j]), np.median(finite), x[:, j])
        assume(float(filled.std()) > 1e-3)  # 補完後も分散が実質ある列だけ（桁落ちを性質と混ぜない）
    encoder: Any = ENCODERS.resolve("scale").factory(0)  # SimpleImputer(median) + StandardScaler
    out = np.asarray(encoder.fit_transform(x), dtype=np.float64)
    assert out.shape == x.shape
    assert np.isfinite(out).all()  # NaN 穴は必ず塞がる（下流の kNN・線形が落ちない）
    np.testing.assert_allclose(out.mean(axis=0), 0.0, atol=1e-6)  # 各列 平均 ≈ 0
    np.testing.assert_allclose(out.std(axis=0), 1.0, rtol=1e-6, atol=1e-6)  # 各列 標準偏差 ≈ 1


@given(x=_matrix_with_nans())
@settings(deadline=None, derandomize=True, max_examples=60)
def test_missing_flags_are_binary_and_match_nan_positions(x: NDArray[np.float64]) -> None:
    encoder: Any = ENCODERS.resolve("missing_flags").factory(0)  # MissingIndicator(features="all")
    out = np.asarray(encoder.fit_transform(x))
    assert out.shape == x.shape  # features="all" ＝出力列数は入力列数と一致（列が欠けない）
    assert set(np.unique(out.astype(np.int64)).tolist()) <= {0, 1}  # 0/1 のみ
    assert np.array_equal(out.astype(np.bool_), np.isnan(x))  # フラグは NaN の位置とセル単位で一致
