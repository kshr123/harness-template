"""agent runtime（ツール往復ループ・TOOLS・AGENT_LOG_FIELDS）と input_fingerprint 移設の検査。ネットワーク 0。

- 期待値は台本・payload の構成から導く：dummy の replies に「入力→calculator(add,2,3)」
  「tool_result:5→答えは 5」を仕込む＝2+3=5 は台本の構成から出る（実装出力のコピーではない）。
- ネットワーク遮断は socket.socket 差し替え（test_agent_e2e.py と同型＝どのクライアント経由でも検知）。
"""

from __future__ import annotations

import hashlib
import json
import socket
from typing import Any

import pytest

from harness.agent.providers import PROVIDERS
from harness.agent.runtime import AGENT_LOG_FIELDS, build_log_row, run_agent
from harness.agent.spec import AgentSpec
from harness.agent.tools import TOOLS, run_tool, to_provider_tools
from harness.fingerprint import input_fingerprint


def _cut_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """socket 生成を失敗にする（テスト中にネットワークへ出ようとしたら即座に落とす）。"""

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("テストがネットワーク接続を試みた（agent の verify は無ネットワークが契約）")

    monkeypatch.setattr(socket, "socket", _refuse)


def _spec(tools: tuple[str, ...] = ("calculator",)) -> AgentSpec:
    return AgentSpec(
        name="looper", provider="dummy", model="dummy-model", system_prompt="計算はツールで行う", tools=tools
    )


# 台本：入力 → calculator(add, 2, 3) を呼ぶ／tool_result "5"（=2+3・構成から導出）を受けたら答える。
_TOOL_SCRIPT = {
    "2と3を足して": {"tool_use": {"name": "calculator", "input": {"a": 2, "b": 3, "op": "add"}}},
    "tool_result:5": "答えは 5",
}


@pytest.mark.integration
def test_run_agent_tool_loop_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # 往復の一巡：tool_use → run_tool → tool_result → end_turn（2 ターン＝台本の構成から導出）。
    _cut_network(monkeypatch)
    provider = PROVIDERS.resolve("dummy").factory(0, replies=_TOOL_SCRIPT)
    run = run_agent(_spec(), "2と3を足して", provider=provider, seed=0)
    assert run.turns == 2
    assert run.tools_used == ("calculator",)
    assert "5" in run.output  # 2+3（ツールの計算結果）が最終応答に載る
    assert run.stop_reason == "end_turn"
    # 履歴の形：user → assistant(tool_use) → user(tool_result) → assistant(text)。tool_result は計算結果。
    assert [m["role"] for m in run.messages] == ["user", "assistant", "user", "assistant"]
    tool_result = run.messages[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["content"] == "5"


@pytest.mark.unit
def test_run_agent_max_turns_terminates(monkeypatch: pytest.MonkeyPatch) -> None:
    # 常に tool_use を返す台本（1+1=2 → tool_result:2 でまた同じ呼び出し）＝黙って回り続けず打ち切る。
    _cut_network(monkeypatch)
    loop_call = {"tool_use": {"name": "calculator", "input": {"a": 1, "b": 1, "op": "add"}}}
    provider = PROVIDERS.resolve("dummy").factory(0, replies={"loop": loop_call, "tool_result:2": loop_call})
    run = run_agent(_spec(), "loop", provider=provider, seed=0, max_turns=3)
    assert run.stop_reason == "max_turns"
    assert run.turns == 3
    assert run.tools_used == ("calculator",) * 3  # 3 ターンとも呼んだ（呼んだ回数だけ並ぶ）
    with pytest.raises(ValueError, match="max_turns"):
        run_agent(_spec(), "loop", provider=provider, seed=0, max_turns=0)  # 上限 0 は明示エラー


@pytest.mark.unit
def test_input_fingerprint_is_canonical_json_sha256() -> None:
    # 移設の不変性：正準 JSON（キー昇順・区切り最小）の sha256 を構成から計算して一致を確かめる。
    payload = {"b": 2, "a": 1}
    canonical = json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert canonical == '{"a":1,"b":2}'  # キー昇順・区切り最小（構成から書ける）
    assert input_fingerprint(payload) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # serve は中核の同一関数を再輸出する（移設で serve/agent の指紋が割れない）。
    from harness.serve import runtime as serve_runtime

    assert serve_runtime.input_fingerprint is input_fingerprint


@pytest.mark.unit
def test_tools_catalog_entries_have_description_and_schema() -> None:
    # ：カタログに載れない（説明の無い）ツールを作らない。宣言形（input_schema）も必須。
    assert len(TOOLS) >= 1
    for kind, entry in TOOLS.items():
        assert entry.description, kind
        assert entry.input_schema.get("type") == "object", kind
        assert set(entry.input_schema.get("required", [])) <= set(entry.input_schema.get("properties", {})), kind


@pytest.mark.unit
def test_to_provider_tools_shape_and_unknown_name() -> None:
    decls = to_provider_tools(("calculator",))
    assert decls == [
        {
            "name": "calculator",
            "description": TOOLS["calculator"].description,
            "input_schema": dict(TOOLS["calculator"].input_schema),
        }
    ]
    with pytest.raises(ValueError, match="calculator"):  # 未登録名は候補一覧つきで止まる
        to_provider_tools(("no_such_tool",))


@pytest.mark.unit
def test_run_tool_computes_from_args() -> None:
    assert run_tool("calculator", {"a": 2, "b": 3, "op": "add"}) == "5"  # 2+3（構成から導出）
    assert run_tool("calculator", {"a": 4, "b": 5, "op": "mul"}) == "20"  # 4*5（構成から導出）


@pytest.mark.unit
def test_run_tool_unknown_name_and_schema_mismatch() -> None:
    with pytest.raises(ValueError, match="ツール"):
        run_tool("no_such_tool", {"a": 1})
    with pytest.raises(ValueError, match="required"):
        run_tool("calculator", {"a": 1, "op": "add"})  # b 欠け（required の充足検査）
    with pytest.raises(ValueError, match="未宣言"):
        run_tool("calculator", {"a": 1, "b": 2, "op": "add", "x": 9})  # 未宣言キーの拒否
    with pytest.raises(ValueError, match="op"):
        run_tool("calculator", {"a": 1, "b": 2, "op": "div"})  # 未知の演算はツール本体が止める


@pytest.mark.unit
def test_build_log_row_matches_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    from harness.agent import runtime

    spec = _spec()
    provider = PROVIDERS.resolve("dummy").factory(0, replies=_TOOL_SCRIPT)
    run = run_agent(spec, "2と3を足して", provider=provider, seed=0)
    row = build_log_row(run, spec=spec, request_id="req-0", time="2026-07-06T00:00:00+00:00")

    assert row.keys() == AGENT_LOG_FIELDS.keys()  # 契約のキー集合と一致
    assert row["input"] == "2と3を足して"  # messages 先頭の user テキストから復元
    assert row["input_fingerprint"] == input_fingerprint({"input": "2と3を足して"})  # 再計算可能
    assert row["agent"]["prompt_fingerprint"] == hashlib.sha256(spec.system_prompt.encode("utf-8")).hexdigest()
    assert row["output"] == run.output
    assert row["turns"] == 2
    assert row["tools_used"] == ["calculator"]

    # キー集合ドリフトは ValueError で止まる（契約に増減があれば build_log_row を直すまで通らない）。
    monkeypatch.setitem(runtime.AGENT_LOG_FIELDS, "extra_key", "契約側だけに在るキー")
    with pytest.raises(ValueError, match="契約"):
        build_log_row(run, spec=spec, request_id="req-0", time="2026-07-06T00:00:00+00:00")
    monkeypatch.delitem(runtime.AGENT_LOG_FIELDS, "extra_key")
    monkeypatch.delitem(runtime.AGENT_LOG_FIELDS, "usage")  # 行側だけに在るキーも同様に止まる
    with pytest.raises(ValueError, match="契約"):
        build_log_row(run, spec=spec, request_id="req-0", time="2026-07-06T00:00:00+00:00")


@pytest.mark.unit
def test_dummy_str_replies_behave_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    # 台本拡張の後方互換：str 値の replies は従来どおり end_turn の text（既存の eval 経路を壊さない）。
    _cut_network(monkeypatch)
    provider = PROVIDERS.resolve("dummy").factory(0, replies={"ping": "pong"})
    run = run_agent(_spec(tools=()), "ping", provider=provider, seed=0)
    assert run.output == "pong"
    assert run.stop_reason == "end_turn"
    assert run.turns == 1
    assert run.tools_used == ()
