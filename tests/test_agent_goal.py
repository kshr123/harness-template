"""agent の goal-based 停止ゲート（`GoalGate`／`run_agent_to_goal`）と `run_agent` の続行口。

**無ネットワークが契約**（DEC-0015）。期待値はすべて dummy の台本（replies）の構成から導出する
（実装出力のコピーで固定しない）。続行文の台本鍵は実装の既定値 `DEFAULT_CONTINUE_PROMPT` をそのまま使う
（テストが独自の文字列を決め打ちしない＝実装と噛み合わなくなる心配がない）。
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

from harness.agent.goal import DEFAULT_CONTINUE_PROMPT, Goal, GoalGate, run_agent_to_goal
from harness.agent.providers import PROVIDERS, build_messages
from harness.agent.runtime import run_agent
from harness.agent.spec import AgentSpec
from harness.loops import StopDecision

_SPEC = AgentSpec(name="goal-smoke", provider="dummy", model="dummy-model", system_prompt="そのまま返す")


def _cut_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """socket 生成を失敗にする（テスト中にネットワークへ出ようとしたら即座に落とす）。"""

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("テストがネットワーク接続を試みた（goal ループの verify は無ネットワーク契約・DEC-0015）")

    monkeypatch.setattr(socket, "socket", _refuse)


@pytest.mark.integration
def test_goal_loop_continues_until_gate_passes_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    # 1 サイクル目「問い」→「下書き」（不一致）／続行文の鍵→「正解」（一致）＝ cycles==2・goal_met を導出できる。
    provider = PROVIDERS.resolve("dummy").factory(0, replies={"問い": "下書き", DEFAULT_CONTINUE_PROMPT: "正解"})
    gate = GoalGate(goal=Goal(expected="正解", thresholds={"exact_match": 1.0}))

    run = run_agent_to_goal(_SPEC, "問い", provider=provider, gate=gate, seed=0)

    assert run.cycles == 2
    assert run.stop_reason == "goal_met"
    assert run.final.output == "正解"
    assert len(run.gate_reasons) == 2
    assert run.gate_reasons[0].startswith("goal_not_met")
    assert run.gate_reasons[1] == "goal_met"


@pytest.mark.integration
def test_goal_loop_carries_conversation_across_cycles_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # goal ループの中核の約束「会話履歴を保ったまま続行する」を直接ピン留めする（MUT3＝prior_messages=() 化で
    # 必ず RED）。dummy は「最後の user テキスト」で決定的に応答する＝同じ台本・同じ seed なら、単発の
    # サイクル 1 実行とループ内サイクル 1 の会話全量は一致する。DummyProvider は frozen・状態を持たない純関数
    # だが、依頼どおり呼び出しごとに provider を作り直して台本の枯渇の懸念を排す。
    _cut_network(monkeypatch)
    replies = {"問い": "下書き", DEFAULT_CONTINUE_PROMPT: "正解"}  # サイクル 1 不一致→続行文で一致（cycles==2）
    gate = GoalGate(goal=Goal(expected="正解", thresholds={"exact_match": 1.0}))

    c1 = run_agent(_SPEC, "問い", provider=PROVIDERS.resolve("dummy").factory(0, replies=replies), seed=0)
    loop = run_agent_to_goal(
        _SPEC, "問い", provider=PROVIDERS.resolve("dummy").factory(0, replies=replies), gate=gate, seed=0
    )

    assert loop.cycles == 2  # 続行が起きたこと（1 サイクルで終わっていない）を先に固定する
    # 最終サイクル（サイクル 2）の messages 先頭が、サイクル 1 の会話全量そのもの＝履歴がまたいで引き継がれた証明。
    # prior_messages を () に潰すと先頭が continue_prompt の user になり、この前方一致が壊れて RED になる。
    assert loop.final.messages[: len(c1.messages)] == c1.messages
    # 引き継いだ末尾に「続行文の user＋正解の assistant」が積まれている（台本の構成から導出）。
    continue_user = build_messages(DEFAULT_CONTINUE_PROMPT)
    answer_assistant = {"role": "assistant", "content": [{"type": "text", "text": "正解"}]}
    assert loop.final.messages[len(c1.messages) :] == (*continue_user, answer_assistant)


@pytest.mark.integration
def test_goal_loop_stops_at_max_cycles_backstop(monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    # 台本に仕込み無し＝常にハッシュ由来のテキスト（"dummy:" 始まり）で期待「正解」に一致しえない構成。
    provider = PROVIDERS.resolve("dummy").factory(0, replies={})
    gate = GoalGate(goal=Goal(expected="正解", thresholds={"exact_match": 1.0}))

    run = run_agent_to_goal(_SPEC, "問い", provider=provider, gate=gate, seed=0, max_cycles=3)

    assert run.cycles == 3  # 黙って回り続けず max_cycles で必ず打ち切る
    assert run.stop_reason == "max_cycles"
    assert len(run.gate_reasons) == 3
    assert all(reason.startswith("goal_not_met") for reason in run.gate_reasons)


@pytest.mark.unit
def test_goal_loop_max_cycles_below_one_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    provider = PROVIDERS.resolve("dummy").factory(0)
    gate = GoalGate(goal=Goal(expected="正解", thresholds={"exact_match": 1.0}))
    with pytest.raises(ValueError, match="max_cycles"):
        run_agent_to_goal(_SPEC, "問い", provider=provider, gate=gate, seed=0, max_cycles=0)


@pytest.mark.unit
def test_goal_gate_reports_score_on_mismatch() -> None:
    gate = GoalGate(goal=Goal(expected="正解", thresholds={"exact_match": 1.0}))
    decision = gate.check(output="下書き", iteration=1)
    assert isinstance(decision, StopDecision)
    assert decision.stop is False
    assert decision.reason == "goal_not_met: exact_match=0.000"  # 不一致 exact_match=0.0 の構成から導出


@pytest.mark.unit
def test_goal_gate_reports_goal_met_on_match() -> None:
    gate = GoalGate(goal=Goal(expected="正解", thresholds={"exact_match": 1.0}))
    decision = gate.check(output="正解", iteration=1)
    assert decision.stop is True
    assert decision.reason == "goal_met"


@pytest.mark.unit
def test_goal_gate_unknown_metric_raises_with_candidates() -> None:
    goal = Goal(expected="正解", metrics=("no_such_metric",), thresholds={"exact_match": 1.0})
    gate = GoalGate(goal=goal)
    with pytest.raises(ValueError, match="no_such_metric"):
        gate.check(output="正解", iteration=1)


@pytest.mark.unit
def test_goal_gate_unknown_threshold_name_raises_fail_closed() -> None:
    # metrics には exact_match のみ載せるが、thresholds は未登録名＝passes 側の ValueError（fail closed）。
    goal = Goal(expected="正解", thresholds={"not_registered": 1.0})
    gate = GoalGate(goal=goal)
    with pytest.raises(ValueError, match="not_registered"):
        gate.check(output="正解", iteration=1)


@pytest.mark.unit
def test_prior_messages_continue_conversation_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    provider = PROVIDERS.resolve("dummy").factory(0, replies={"続き": "了解"})
    first = run_agent(_SPEC, "最初", provider=provider, seed=0)
    second = run_agent(_SPEC, "続き", provider=provider, seed=0, prior_messages=first.messages)

    assert second.output == "了解"  # 台本鍵＝最後の user テキストで観測できる
    assert second.messages[: len(first.messages)] == first.messages  # [*prior, 新 user, …] の前半が一致
    new_user = tuple(build_messages("続き"))
    new_assistant = ({"role": "assistant", "content": [{"type": "text", "text": "了解"}]},)
    assert second.messages[len(first.messages) :] == new_user + new_assistant


@pytest.mark.unit
def test_prior_messages_default_matches_existing_behavior_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # 省略時（既定 ()）は従来どおり＝後方互換の直接確認（既存 runtime テストが無修正で緑であることの補強）。
    _cut_network(monkeypatch)
    provider = PROVIDERS.resolve("dummy").factory(0, replies={"最初": "了解"})
    run = run_agent(_SPEC, "最初", provider=provider, seed=0)
    expected = (*build_messages("最初"), {"role": "assistant", "content": [{"type": "text", "text": "了解"}]})
    assert run.messages == expected  # 省略時（既定 ()）は build_messages(user_input) から始まる＝従来どおり


@pytest.mark.integration
def test_goal_loop_composes_with_tool_round_trip_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # サイクル 1 が calculator 往復（tool_use→tool_result）の末に不一致→サイクル 2 で goal_met
    # （run_agent 丸ごと再利用の証明。台本は `agent run --test` の calculator 例と同じ構成）。
    _cut_network(monkeypatch)
    tool_spec = AgentSpec(
        name="goal-tools",
        provider="dummy",
        model="dummy-model",
        system_prompt="計算はツールで行う",
        tools=("calculator",),
    )
    provider = PROVIDERS.resolve("dummy").factory(
        0,
        replies={
            "2と3を足して": {"tool_use": {"name": "calculator", "input": {"a": 2, "b": 3, "op": "add"}}},
            "tool_result:5": "答えは 5",  # ツール往復の答え（期待「5」とは不一致＝サイクル 1 は未達）
            DEFAULT_CONTINUE_PROMPT: "5",  # 続行文への直答（一致）
        },
    )
    gate = GoalGate(goal=Goal(expected="5", thresholds={"exact_match": 1.0}))

    run = run_agent_to_goal(tool_spec, "2と3を足して", provider=provider, gate=gate, seed=0)

    assert run.cycles == 2
    assert run.stop_reason == "goal_met"
    assert run.final.output == "5"
    assert run.gate_reasons[0].startswith("goal_not_met")
    # サイクル 1（tool_use→tool_result→答え）は turns==2・サイクル 2（続行文への直答）は turns==1（台本の構成）。
    assert run.final.turns == 1
