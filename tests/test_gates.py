"""gates（昇格の判定）のテスト。

期待値は仕込んだ metrics・閾値・向きの算術から導く。detail の文言は照合しない（人が読む説明であり、
合否を決めるのは `passed` と `reason`）。
"""

from __future__ import annotations

import math

import pytest

from harness import gates, registry

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
    # reason は向きに依らない（小さいほど良い指標が上限を超えて落ちても同じ名で記録される）。
    assert result.reason == ("ok" if passed else "threshold_not_met")


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


def test_value_threshold_rejects_a_non_finite_value() -> None:
    # 発散は NaN だけで起きるのではない。inf >= 0.8 も -inf <= 0.5 も True なので、比較だけでは通ってしまう。
    # 「有限である」を合格条件に含めて初めて、発散した版が閾値を通り抜けない。
    assert gates.value_threshold(_ctx({"score": math.inf}), metric="score", limit=0.8).passed is False
    assert gates.value_threshold(_ctx({"loss": -math.inf}), metric="loss", limit=0.5).passed is False
    assert gates.value_threshold(_ctx({"score": math.nan}), metric="score", limit=0.0).reason == "not_finite"


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


def test_change_threshold_rejects_a_non_finite_candidate_even_without_a_baseline() -> None:
    # 初回昇格は比較対象が無いので改善量を問えないが、それは「何でも通す」ことではない。
    # 閾値を 1 つも宣言していない場合、ここが発散した版を止める最後の場所になる。
    for observed in (math.nan, math.inf, -math.inf):
        result = gates.change_threshold(_ctx({"score": observed}, None), metric="score", baseline="champion")
        assert result.passed is False, observed
        assert result.reason == "not_finite", observed


def test_change_threshold_names_a_non_finite_baseline_distinctly() -> None:
    # champion 側が壊れている（過去に混入した）状態。候補は悪くないので、reason で区別できないと
    # 「候補が悪い」と読み違える。切り戻しが要る状態であることを記録に残す。
    result = gates.change_threshold(_ctx({"score": 0.9}, {"score": math.nan}), metric="score", baseline="champion")
    assert result.passed is False and result.reason == "baseline_not_finite"


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


def test_evaluate_zero_specs_is_approved_but_not_judged() -> None:
    # 判定 0 件は all([])=True で approved に見えるが、judged=False で「判定していない」と区別できる（T-0199）。
    decision = gates.evaluate(_ctx({"score": 0.9}), [])
    assert decision.approved is True  # 後方互換（探索の passes(x, {}) は True のまま）
    assert decision.judged is False  # だが 1 件も判定していない
    assert decision.first_promotion is False  # 初回昇格の緩和も効いていない


def test_evaluate_first_promotion_is_named_when_no_baseline() -> None:
    # baseline（champion）が無い初回昇格では change_threshold が no_baseline を返す。その緩和を
    # first_promotion で名指しできる（暗黙にしない・T-0199）。judged は True（1 件は下している）。
    ctx = _ctx({"score": 0.9}, None)  # baseline なし＝初回
    decision = gates.evaluate(ctx, [{"kind": "change_threshold", "metric": "score", "baseline": "champion"}])
    assert decision.approved is True
    assert decision.judged is True
    assert decision.first_promotion is True
    # champion がある通常昇格では first_promotion は False。
    normal = gates.evaluate(
        _ctx({"score": 0.9}, {"score": 0.8}), [{"kind": "change_threshold", "metric": "score", "baseline": "champion"}]
    )
    assert normal.first_promotion is False


def test_evaluate_rejects_a_spec_without_a_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        gates.evaluate(_ctx({"score": 0.9}), [{"metric": "score", "limit": 0.1}])


def test_evaluate_rejects_an_unknown_gate_parameter_as_a_value_error() -> None:
    # 呼び手（CLI・config）は ValueError だけを捕まえる契約。引数の typo が TypeError で貫通すると
    # 非ゼロ終了でなくトレースバックになる。
    with pytest.raises(ValueError, match="bogus"):
        gates.evaluate(_ctx({"score": 0.9}), [{"kind": "value_threshold", "metric": "score", "limit": 0.1, "bogus": 1}])


def test_gate_results_record_the_parameters_they_were_given() -> None:
    # 判定ごとに引数が違う（value_threshold は limit・change_threshold は baseline と min_change）。
    # 昇格記録へそのまま書けるよう、単一の `limit` 欄でなく渡された引数を保持する。
    value = gates.value_threshold(_ctx({"score": 0.9}), metric="score", limit=0.8)
    assert value.params == {"limit": 0.8}
    change = gates.change_threshold(
        _ctx({"score": 0.9}, {"score": 0.8}), metric="score", baseline="champion", min_change=0.01
    )
    assert change.params == {"baseline": "champion", "min_change": 0.01}


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


def test_a_new_gate_cannot_be_registered_without_a_source() -> None:
    # 判定の名前は概念そのものの名前。出典なしに新しい名前を作れない（造語の誕生を登録時に止める）。
    def bogus(ctx: gates.GateContext) -> None:
        """説明文はあるが、名前の出典が無い。"""

    with pytest.raises(ValueError, match="出典"):
        gates.GATES.register("bogus_gate", bogus)
    assert "bogus_gate" not in gates.GATES  # 失敗した登録は残らない


def test_the_gates_catalog_shows_where_each_name_comes_from(capsys: pytest.CaptureFixture[str]) -> None:
    # 使う側が名前の由来をカタログから辿れる（元コードを読まずに使える、の一部）。
    registry.render_catalog(gates.GATES, show_params=True)
    out = capsys.readouterr().out
    for kind, entry in gates.GATES.items():
        assert entry.source, kind
        assert entry.source in out, kind  # 期待値は登録内容から導出（出力の写経ではない）
