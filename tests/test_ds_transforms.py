"""ターゲット変換 transforms.py のテスト（純粋・numpy のみ）。

期待値はテストデータの構成から導出できるものだけを書く（実装出力のコピーはしない）：
- 往復（inverse_transform∘transform）が元に戻ることを hypothesis の生成入力で確かめる。
- 数式から定まる事実（log1p(0)=0・標準化後は平均0/分散1・std=0 は 1 とみなす）だけを固定値にする。
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from harness.ds.transforms import Identity, Log1p, StandardScale, TargetTransform

pytestmark = pytest.mark.unit

# 生成する配列（1〜50 要素）。桁が大きすぎると往復の丸め誤差が増えるので範囲を抑える。
_SHAPE = st.integers(min_value=1, max_value=50)
_ANY = arrays(np.float64, _SHAPE, elements=st.floats(-1e4, 1e4, allow_nan=False, allow_infinity=False))
_NONNEG = arrays(np.float64, _SHAPE, elements=st.floats(0.0, 1e4, allow_nan=False, allow_infinity=False))


def test_all_transforms_satisfy_protocol() -> None:
    # 3 実装とも TargetTransform の契約（transform / inverse_transform）を構造的に満たす。
    for t in (Identity(), Log1p(), StandardScale()):
        assert isinstance(t, TargetTransform)


@given(y=_ANY)
def test_identity_roundtrip(y: np.ndarray) -> None:
    t = Identity()
    np.testing.assert_array_equal(t.inverse_transform(t.transform(y)), y)


@given(y=_NONNEG)
def test_log1p_roundtrip_on_nonnegative(y: np.ndarray) -> None:
    # 非負域では inverse_transform(transform(y)) ≈ y（往復で元へ戻る）。
    t = Log1p()
    np.testing.assert_allclose(t.inverse_transform(t.transform(y)), y, rtol=1e-9, atol=1e-9)


def test_log1p_zero_maps_to_zero() -> None:
    # log(1+0)=0（数式から定まる）。
    assert Log1p().transform(np.array([0.0]))[0] == 0.0


def test_log1p_inverse_clips_negative_to_zero() -> None:
    # 逆変換で負に振れた値は 0 に切り上げる（非負ターゲットの下限を守る）。
    result = Log1p().inverse_transform(np.array([-10.0, -1.0, 0.0]))
    assert result[0] == 0.0
    assert result[1] == 0.0
    assert result[2] == 0.0  # expm1(0)=0


@given(y=_ANY)
def test_standard_scale_roundtrip(y: np.ndarray) -> None:
    t = StandardScale().fit(y)
    np.testing.assert_allclose(t.inverse_transform(t.transform(y)), y, rtol=1e-9, atol=1e-9)


def test_standard_scale_uses_fitted_stats_not_input() -> None:
    # fit した統計（別配列）で変換する。入力から再計算するリーク実装ならズレて検知できる。
    t = StandardScale().fit(np.array([0.0, 10.0]))  # mean=5, std=5
    np.testing.assert_allclose(t.transform(np.array([0.0, 5.0, 10.0])), [-1.0, 0.0, 1.0])
    # 往復も別の配列 b で成り立つ（保存した mean・std を使うことの担保）。
    b = np.array([2.0, 7.0, 42.0])
    np.testing.assert_allclose(t.inverse_transform(t.transform(b)), b, rtol=1e-9, atol=1e-9)


def test_standard_scale_standardizes_to_zero_mean_unit_std() -> None:
    # fit した配列を transform すると平均0・分散1（標準化の定義）。
    t = StandardScale().fit(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    z = t.transform(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert z.mean() == pytest.approx(0.0, abs=1e-12)
    assert z.std() == pytest.approx(1.0, abs=1e-12)


def test_standard_scale_constant_array_uses_unit_std() -> None:
    # 定数配列（std=0）は 0 除算を避けるため std=1 とみなし、transform は 0 配列になる。
    t = StandardScale().fit(np.array([5.0, 5.0, 5.0]))
    np.testing.assert_array_equal(t.transform(np.array([5.0, 5.0, 5.0])), np.zeros(3))


def test_standard_scale_requires_fit_before_transform() -> None:
    with pytest.raises(RuntimeError, match="fit"):
        StandardScale().transform(np.array([1.0, 2.0, 3.0]))


def test_standard_scale_requires_fit_before_inverse() -> None:
    with pytest.raises(RuntimeError, match="fit"):
        StandardScale().inverse_transform(np.array([1.0, 2.0, 3.0]))
