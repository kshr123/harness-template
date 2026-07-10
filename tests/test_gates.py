"""gates（昇格の判定）のテスト。

期待値は仕込んだ metrics・閾値・向きの算術から導く。detail の文言は照合しない（人が読む説明であり、
合否を決めるのは `passed` と `reason`）。
"""

from __future__ import annotations

import math

import pytest

from harness import gates

pytestmark = pytest.mark.unit

_UP = {"score": True}  # 大きいほど良い
_DOWN = {"loss": False}  # 小さいほど良い


def _ctx(candidate: dict[str, float], baseline: dict[str, float] | None = None, **kwargs: object) -> gates.GateContext:
    directions = dict(_UP) | dict(_DOWN)
    return gates.GateContext(candidate=candidate, baseline=baseline, directions=directions, **kwargs)  # type: ignore[arg-type]


# --- value_threshold ---


@pytest.mark.parametrize(
    ("observed", "limit", "passed"),
    [(0.80, 0.80, True), (0.81, 0.80, True), (0.79, 0.80, False)],  # 大きいほど良い＝下限（同値は合格）
)
def test_value_threshold_uses_a_lower_bound_when_higher_is_better(observed: float, limit: float, passed: bool) -> None:
    result = gates.value_threshold(_ctx({"score": observed}), metric="score", limit=limit)
    assert result.passed is passed
    assert result.reason == ("ok" if passed else "below_limit")


@pytest.mark.parametrize(
    ("observed", "limit", "passed"),
    [(0.50, 0.50, True), (0.49, 0.50, True), (0.51, 0.50, False)],  # 小さいほど良い＝上限
)
def test_value_threshold_uses_an_upper_bound_when_lower_is_better(observed: float, limit: float, passed: bool) -> None:
    result = gates.value_threshold(_ctx({"loss": observed}), metric="loss", limit=limit)
    assert result.passed is passed


def test_value_threshold_is_fail_closed_for_nan() -> None:
    # NaN >= x も NaN <= x も False（合格条件を正の形で問うため）。向きに依らず不合格。
    assert gates.value_threshold(_ctx({"score": math.nan}), metric="score", limit=0.0).passed is False
    assert gates.value_threshold(_ctx({"loss": math.nan}), metric="loss", limit=1.0).passed is False


def test_value_threshold_treats_an_unmeasured_metric_as_a_failure() -> None:
    result = gates.value_threshold(_ctx({}), metric="score", limit=0.0)
    assert result.passed is False and result.reason == "not_measured" and result.observed is None


# --- change_threshold ---


def test_change_threshold_requires_a_strict_improvement_by_default() -> None:
    # 既定 min_change=0.0・厳密な不等号。同点（改善量 0.0）は昇格させない。
    better = gates.change_threshold(_ctx({"score": 0.91}, {"score": 0.90}), metric="score", baseline="champion")
    tie = gates.change_threshold(_ctx({"score": 0.90}, {"score": 0.90}), metric="score", baseline="champion")
    worse = gates.change_threshold(_ctx({"score": 0.89}, {"score": 0.90}), metric="score", baseline="champion")
    assert (better.passed, tie.passed, worse.passed) == (True, False, False)
    assert tie.reason == "no_improvement"


def test_change_threshold_normalizes_improvement_by_direction() -> None:
    # loss は小さいほど良い＝0.40 は 0.50 より 0.10 改善している（符号は向きに依存しない）。
    result = gates.change_threshold(_ctx({"loss": 0.40}, {"loss": 0.50}), metric="loss", baseline="champion")
    assert result.passed is True
    assert result.observed == 0.40 and result.baseline == 0.50


def test_change_threshold_min_change_is_the_same_sign_for_both_directions() -> None:
    # 「0.05 以上の改善」を要求する。score は +0.05、loss は −0.05 の動きだが、どちらも改善量 0.05。
    # 厳密な不等号なので、ちょうど 0.05 は不合格・0.06 は合格。
    for candidate, base, metric in [
        ({"score": 0.95}, {"score": 0.90}, "score"),
        ({"loss": 0.45}, {"loss": 0.50}, "loss"),
    ]:
        exact = gates.change_threshold(_ctx(candidate, base), metric=metric, baseline="champion", min_change=0.05)
        assert exact.passed is False, metric
    for candidate, base, metric in [
        ({"score": 0.96}, {"score": 0.90}, "score"),
        ({"loss": 0.44}, {"loss": 0.50}, "loss"),
    ]:
        beyond = gates.change_threshold(_ctx(candidate, base), metric=metric, baseline="champion", min_change=0.05)
        assert beyond.passed is True, metric


def test_change_threshold_is_fail_closed_for_nan_on_either_side() -> None:
    nan_candidate = gates.change_threshold(
        _ctx({"score": math.nan}, {"score": 0.9}), metric="score", baseline="champion"
    )
    nan_baseline = gates.change_threshold(
        _ctx({"score": 0.9}, {"score": math.nan}), metric="score", baseline="champion"
    )
    assert nan_candidate.passed is False and nan_baseline.passed is False


def test_change_threshold_passes_when_there_is_no_baseline() -> None:
    # 初回昇格には比較対象が無い＝この判定は課さない（閾値の判定だけで決まる）。
    result = gates.change_threshold(_ctx({"score": 0.1}, None), metric="score", baseline="champion")
    assert result.passed is True and result.reason == "no_baseline"


def test_change_threshold_fails_when_the_candidate_lacks_the_metric_even_without_a_baseline() -> None:
    # 候補が測っていない指標では、比較対象の有無に関わらず昇格を認めない（baseline 不在より先に見る）。
    result = gates.change_threshold(_ctx({"loss": 0.1}, None), metric="score", baseline="champion")
    assert result.passed is False and result.reason == "not_measured"


def test_change_threshold_fails_when_the_baseline_lacks_the_metric() -> None:
    result = gates.change_threshold(_ctx({"score": 0.9}, {"loss": 0.1}), metric="score", baseline="champion")
    assert result.passed is False and result.reason == "baseline_not_measured"


def test_change_threshold_rejects_an_unsupported_baseline() -> None:
    with pytest.raises(ValueError, match="previous_version"):
        gates.change_threshold(_ctx({"score": 0.9}, {"score": 0.8}), metric="score", baseline="previous_version")


# --- 向きの解決 ---


def test_unresolved_direction_is_an_error_not_a_silent_failure() -> None:
    ctx = gates.GateContext(candidate={"unknown": 1.0}, baseline=None, directions={})
    with pytest.raises(ValueError, match="unknown"):
        gates.value_threshold(ctx, metric="unknown", limit=0.0)


# --- evaluate（全件集めてから合否） ---


def test_evaluate_collects_every_failure_not_just_the_first() -> None:
    ctx = _ctx({"score": 0.10, "loss": 0.90}, {"score": 0.50})
    decision = gates.evaluate(
        ctx,
        [
            {"kind": "value_threshold", "metric": "score", "limit": 0.80},  # 落ちる
            {"kind": "value_threshold", "metric": "loss", "limit": 0.50},  # 落ちる
            {"kind": "change_threshold", "metric": "score", "baseline": "champion"},  # 落ちる
        ],
    )
    assert decision.approved is False
    assert len(decision.results) == 3
    assert len(decision.failures) == 3  # 最初の 1 件で止めない


def test_evaluate_is_approved_only_when_every_gate_passes() -> None:
    ctx = _ctx({"score": 0.90}, {"score": 0.80})
    specs: list[gates.GateSpec] = [
        {"kind": "value_threshold", "metric": "score", "limit": 0.80},
        {"kind": "change_threshold", "metric": "score", "baseline": "champion"},
    ]
    assert gates.evaluate(ctx, specs).approved is True
    assert gates.evaluate(_ctx({"score": 0.70}, {"score": 0.80}), specs).approved is False


def test_evaluate_rejects_an_unknown_gate_kind() -> None:
    with pytest.raises(ValueError, match="gates"):  # 未知 kind のエラーは Registry.resolve が出す（候補＋カタログ案内）
        gates.evaluate(_ctx({"score": 0.9}), [{"kind": "nope", "metric": "score", "limit": 0.1}])


def test_value_threshold_specs_expands_a_threshold_mapping() -> None:
    specs = gates.value_threshold_specs({"score": 0.8, "loss": 0.2})
    assert specs == [
        {"kind": "value_threshold", "metric": "score", "limit": 0.8},
        {"kind": "value_threshold", "metric": "loss", "limit": 0.2},
    ]


# --- レジストリの規約 ---


def test_every_gate_is_registered_with_a_description_from_its_docstring() -> None:
    assert sorted(gates.GATES) == ["change_threshold", "value_threshold"]
    for kind, entry in gates.GATES.items():
        first_line = (entry.factory.__doc__ or "").strip().splitlines()[0]
        assert entry.description == first_line, kind
        assert entry.description  # 説明の無い項目は登録できない（Registry の規約）
