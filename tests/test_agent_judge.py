"""LLM-judge（`agent/judge.py`）と `llm_judge` 登録（`agent/eval.py`）の検査（T-0096・無ネットワーク）。

期待値はすべて dummy 台本・cassette フィクスチャ・閾値の構成から導く（実装出力のコピーはしない）。
"""

from __future__ import annotations

import json
import math
import socket
from pathlib import Path
from typing import Any

import pytest

from harness.agent.eval import AGENT_METRICS, JudgeEntry
from harness.agent.goal import goal_from_mapping
from harness.agent.judge import (
    JUDGE_SYSTEM_PROMPT,
    RubricJudge,
    judge_messages,
    judge_user_text,
    make_rubric_judge,
    parse_judge_score,
)
from harness.agent.providers import PROVIDERS
from harness.agent.spec import AgentSpec

_JUDGE_SPEC = AgentSpec(name="judge-smoke", provider="dummy", model="dummy-model", system_prompt=JUDGE_SYSTEM_PROMPT)


def _cut_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """socket 生成を失敗にする（judge テストの verify は無ネットワーク契約）。"""

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("テストがネットワーク接続を試みた（judge の verify は無ネットワーク契約）")

    monkeypatch.setattr(socket, "socket", _refuse)


# --- parse_judge_score（fail closed：裸の [0,1] 全文一致だけ許す） ---


@pytest.mark.unit
def test_parse_judge_score_accepts_only_bare_unit_interval() -> None:
    assert parse_judge_score("0") == 0.0
    assert parse_judge_score("1") == 1.0
    assert parse_judge_score("0.75") == 0.75
    assert parse_judge_score(" 0.5 ") == 0.5  # strip は許容


@pytest.mark.unit
def test_parse_judge_score_unparseable_is_nan_fail_closed() -> None:
    for text in ("1.5", "-0.1", "0.8 です", "", "nan"):
        assert math.isnan(parse_judge_score(text)), f"{text!r} は NaN であるべき（fail closed）"


# --- judge_user_text（テンプレの意味的契約：rubric と candidate の両方を必ず含む） ---


@pytest.mark.unit
def test_judge_user_text_includes_both_rubric_and_candidate() -> None:
    # rubric/candidate を落とすと judge が盲目採点になる＝テンプレの意味的契約を直接固定する
    # （期待値は入力の構成から導出＝センチネルの出現。ハードコード期待値ではない）。
    text = judge_user_text("__RUBRIC_SENTINEL__", "__CANDIDATE_SENTINEL__")
    assert "__RUBRIC_SENTINEL__" in text
    assert "__CANDIDATE_SENTINEL__" in text


# --- RubricJudge（dummy 台本・cassette フィクスチャ） ---


@pytest.mark.integration
def test_rubric_judge_scores_from_dummy_script_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    rubric = "手順が3段になっている"
    candidate = "1. 2. 3."
    provider = PROVIDERS.resolve("dummy").factory(0, replies={judge_user_text(rubric, candidate): "0.8"})
    judge = RubricJudge(provider=provider, spec=_JUDGE_SPEC)

    assert judge(rubric, candidate) == 0.8  # 0.8 は台本の構成そのもの

    # 台本に無い入力（別の candidate）はハッシュ由来のテキスト＝parse_judge_score が NaN にする。
    assert math.isnan(judge(rubric, "台本に無い候補"))


@pytest.mark.integration
def test_rubric_judge_replays_cassette_fixture_no_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    from harness.agent.cassette import cassette, cassette_key

    rubric = "手順が3段になっている"
    candidate = "1. 2. 3."
    key = cassette_key(
        model=_JUDGE_SPEC.model,
        system_prompt=JUDGE_SYSTEM_PROMPT,
        messages=judge_messages(rubric, candidate),
        tools=[],
    )
    record = {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "0.72"}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    path = tmp_path / "judge-cassette.json"
    path.write_text(json.dumps({key: record}, ensure_ascii=False), encoding="utf-8")
    judge = RubricJudge(provider=cassette(0, path=path), spec=_JUDGE_SPEC)

    assert judge(rubric, candidate) == 0.72  # フィクスチャの構成そのもの

    # 記録に無いキー（別 candidate）は fail closed の ValueError（dummy へフォールバックしない）。
    with pytest.raises(ValueError, match="cassette に記録が無い"):
        judge(rubric, "記録に無い候補")


# --- JudgeEntry（.fn は案内つき ValueError）・登録（カタログ） ---


@pytest.mark.unit
def test_llm_judge_entry_fn_raises_binding_guidance() -> None:
    entry = AGENT_METRICS["llm_judge"]
    assert isinstance(entry, JudgeEntry)
    with pytest.raises(ValueError, match="束ね"):
        _ = entry.fn


@pytest.mark.unit
def test_llm_judge_registered_with_description() -> None:
    assert "llm_judge" in AGENT_METRICS
    entry = AGENT_METRICS["llm_judge"]
    assert entry.description  # docstring 1 行目から自動（空は登録できない）
    assert entry.higher_is_better is True
    assert entry.tasks == ("rubric",)


@pytest.mark.unit
def test_make_rubric_judge_binds_provider_and_spec_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    provider = PROVIDERS.resolve("dummy").factory(0, replies={judge_user_text("基準", "候補"): "0.4"})
    judge = make_rubric_judge(provider=provider, spec=_JUDGE_SPEC)
    assert judge("基準", "候補") == 0.4  # 台本の構成そのもの


# --- goal_from_mapping（宣言の検証・spec_from_mapping と同型・extra forbid） ---


@pytest.mark.unit
def test_goal_from_mapping_unknown_key_raises() -> None:
    with pytest.raises(ValueError, match="未知のキー"):
        goal_from_mapping({"expected": "正解", "yolo": 1})
    with pytest.raises(ValueError, match="未知のキー"):
        goal_from_mapping(
            {
                "expected": "基準",
                "metrics": ["llm_judge"],
                "thresholds": {"llm_judge": 0.7},
                "judge": {"provider": "dummy", "model": "dummy-model", "yolo": 1},
            }
        )


@pytest.mark.unit
def test_goal_from_mapping_judge_metric_requires_judge_section() -> None:
    # judge 系 metric なのに judge: 節が無い → ValueError
    with pytest.raises(ValueError, match="judge"):
        goal_from_mapping({"expected": "基準", "metrics": ["llm_judge"], "thresholds": {"llm_judge": 0.7}})
    # judge: 節はあるが metrics が exact_match のみ（judge 系無し）→ ValueError（片方だけは禁止）
    with pytest.raises(ValueError, match="judge"):
        goal_from_mapping(
            {
                "expected": "正解",
                "metrics": ["exact_match"],
                "thresholds": {"exact_match": 1.0},
                "judge": {"provider": "dummy", "model": "dummy-model"},
            }
        )
    # judge 系×純関数系の併用 → ValueError（expected の意味が二重になる）
    with pytest.raises(ValueError, match="併用"):
        goal_from_mapping(
            {
                "expected": "基準",
                "metrics": ["llm_judge", "exact_match"],
                "thresholds": {"llm_judge": 0.7, "exact_match": 1.0},
                "judge": {"provider": "dummy", "model": "dummy-model"},
            }
        )
