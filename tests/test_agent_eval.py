"""採点器（exact_match）と合否ゲート（agent.eval.passes）の単体検査。

期待値はすべて構成から導く（金メッキ禁止）。passes は ds.eval.passes と同じ fail-closed 規約
（NaN は不合格・未登録の閾値名は ValueError・向きはレジストリ）を持つことを固定する（L-009）。
"""

from __future__ import annotations

import math

import pytest

from harness.agent.eval import AGENT_METRICS, exact_match, passes


@pytest.mark.unit
def test_exact_match_is_one_only_on_equality() -> None:
    assert exact_match("pong", "pong") == 1.0  # 一致＝1.0
    assert exact_match("pong", "PONG") == 0.0  # 大文字小文字も別物＝0.0
    assert exact_match("", "") == 1.0  # 空同士も一致


@pytest.mark.unit
def test_passes_true_when_threshold_met() -> None:
    # exact_match は higher_is_better＝0.5 以上で合格。2/3≈0.667 は 0.5 を満たす・0.9 は満たさない。
    assert passes({"exact_match": 2 / 3}, {"exact_match": 0.5}) is True
    assert passes({"exact_match": 2 / 3}, {"exact_match": 0.9}) is False


@pytest.mark.unit
def test_passes_nan_fails_closed() -> None:
    # NaN はどの比較も False＝必ず不合格（発散を関門で止める。ds.eval.passes と同じ fail closed）。
    assert passes({"exact_match": math.nan}, {"exact_match": 0.5}) is False


@pytest.mark.unit
def test_passes_missing_metric_is_failure() -> None:
    # 閾値はあるのに測っていない指標＝満たしたと見なさない（不合格）。
    assert passes({}, {"exact_match": 0.5}) is False


@pytest.mark.unit
def test_passes_unknown_threshold_name_raises() -> None:
    # thresholds に未登録の名（typo 等）は黙って不合格にせず ValueError で止める。
    with pytest.raises(ValueError, match="未登録の採点器"):
        passes({"exact_match": 1.0}, {"no_such_metric": 0.5})


@pytest.mark.unit
def test_exact_match_registered_in_catalog() -> None:
    assert "exact_match" in AGENT_METRICS  # `uv run agent metrics` に載る（DEC-0009）
