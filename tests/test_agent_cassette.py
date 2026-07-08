"""実プロバイダ（AnthropicProvider）と記録再生（CassetteProvider）の検査（T-0092・無ネットワーク）。

- adapter（_reply_from_anthropic）：API 契約から書いた応答 dict（フィクスチャ）が ProviderReply に
  正しく写る・欠損は ValueError（fail loud）。期待値はすべてフィクスチャの構成から導く（ハードコード期待値禁止）。
- cassette：replay が adapter と同一の ProviderReply を返す・記録が無ければ fail closed。socket を塞いで
  「無ネットワーク」の担保を本物にする。run_agent に挿しても往復ループが不変であることも固定する。
- AnthropicProvider：temperature を送らない・effort（output_config）を送る（create を偽物に差し替え＝
  実クライアントは作らない・ネットワーク 0）。
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, NoReturn

import pytest

from harness.agent.cassette import CassetteProvider, cassette, cassette_key, load_cassette
from harness.agent.providers import PROVIDERS, AnthropicProvider, _reply_from_anthropic, build_messages
from harness.agent.runtime import run_agent
from harness.agent.spec import AgentSpec
from harness.agent.tools import to_provider_tools

# --- フィクスチャ（Anthropic Messages API 契約の写し。値はここでの構成から導く＝実装出力のコピーではない） ---

_TEXT_RESPONSE: dict[str, Any] = {
    "content": [{"type": "text", "text": "こんにちは"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 3},
}

_TOOL_USE_RESPONSE: dict[str, Any] = {
    "content": [{"type": "tool_use", "id": "toolu_1", "name": "calculator", "input": {"a": 2, "b": 3, "op": "add"}}],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


@pytest.fixture
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """socket を塞ぐ（うっかり実ネットワークへ出た瞬間に失敗＝「無ネットワーク」の担保を本物にする）。"""

    def _blocked(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("このテストはネットワーク禁止（socket.socket が呼ばれた）")

    monkeypatch.setattr(socket, "socket", _blocked)


# --- adapter（_reply_from_anthropic）の純変換 ---


@pytest.mark.unit
def test_adapter_maps_text_response() -> None:
    reply = _reply_from_anthropic(_TEXT_RESPONSE)
    assert reply.stop_reason == "end_turn"  # フィクスチャの stop_reason がそのまま写る
    assert reply.content == ({"type": "text", "text": "こんにちは"},)
    assert reply.usage == {"input_tokens": 12, "output_tokens": 3}


@pytest.mark.unit
def test_adapter_maps_tool_use_response() -> None:
    reply = _reply_from_anthropic(_TOOL_USE_RESPONSE)
    assert reply.stop_reason == "tool_use"
    assert reply.content == (
        {"type": "tool_use", "id": "toolu_1", "name": "calculator", "input": {"a": 2, "b": 3, "op": "add"}},
    )
    assert reply.usage == {"input_tokens": 10, "output_tokens": 5}


@pytest.mark.unit
def test_adapter_rejects_tool_use_without_input() -> None:
    broken = {
        "content": [{"type": "tool_use", "id": "toolu_1", "name": "calculator"}],  # input 欠け
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    with pytest.raises(ValueError, match="tool_use block"):
        _reply_from_anthropic(broken)


@pytest.mark.unit
def test_adapter_rejects_missing_stop_reason_or_usage() -> None:
    no_stop = {k: v for k, v in _TEXT_RESPONSE.items() if k != "stop_reason"}
    with pytest.raises(ValueError, match="stop_reason"):
        _reply_from_anthropic(no_stop)
    no_usage = {k: v for k, v in _TEXT_RESPONSE.items() if k != "usage"}
    with pytest.raises(ValueError, match="usage"):
        _reply_from_anthropic(no_usage)


@pytest.mark.unit
def test_adapter_rejects_unknown_block_type() -> None:
    unknown = {
        "content": [{"type": "thinking", "thinking": "…"}],  # 未対応の block ＝形状ドリフトとして落とす
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    with pytest.raises(ValueError, match="未知の content block type"):
        _reply_from_anthropic(unknown)


# --- cassette（記録再生・fail closed・無ネットワーク） ---


def _write_cassette(path: Path, records: dict[str, dict[str, Any]]) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


@pytest.mark.integration
def test_cassette_replay_matches_adapter_no_network(tmp_path: Path, block_network: None) -> None:
    spec = AgentSpec(name="replay", provider="cassette", model="claude-test", system_prompt="検証用")
    text_messages = build_messages("こんにちは")
    tool_messages = build_messages("2と3を足して")
    records = {
        cassette_key(model=spec.model, system_prompt=spec.system_prompt, messages=text_messages, tools=[]): (
            _TEXT_RESPONSE
        ),
        cassette_key(model=spec.model, system_prompt=spec.system_prompt, messages=tool_messages, tools=[]): (
            _TOOL_USE_RESPONSE
        ),
    }
    path = tmp_path / "cassette.json"
    _write_cassette(path, records)
    provider = cassette(0, path=path)
    # replay の結果＝共有 adapter に直接通した結果（text と tool_use の両形状）。
    assert provider.reply(messages=text_messages, tools=[], spec=spec) == _reply_from_anthropic(_TEXT_RESPONSE)
    assert provider.reply(messages=tool_messages, tools=[], spec=spec) == _reply_from_anthropic(_TOOL_USE_RESPONSE)
    # 記録の無いキーは fail closed（dummy へフォールバックしない）。
    with pytest.raises(ValueError, match="cassette に記録が無い"):
        provider.reply(messages=build_messages("記録に無い入力"), tools=[], spec=spec)


@pytest.mark.integration
def test_run_agent_through_cassette_tool_loop(tmp_path: Path, block_network: None) -> None:
    """cassette 2 応答で tool_use→tool_result→end_turn が回る＝実プロバイダに差し替えても run_agent は不変。"""
    spec = AgentSpec(
        name="replay-tools",
        provider="cassette",
        model="claude-test",
        system_prompt="計算はツールで行う",
        tools=("calculator",),
    )
    provider_tools = to_provider_tools(spec.tools)  # run_agent が provider へ渡す形をそのまま再現
    turn1_messages = build_messages("2と3を足して")
    # 2 ターン目の messages は run_agent の組み立てを写す：assistant（tool_use ブロック）→ user（tool_result）。
    # tool_result の content は calculator(add, 2, 3) の結果＝"5"（構成から導出）。
    turn2_messages = [
        *turn1_messages,
        {"role": "assistant", "content": [dict(_TOOL_USE_RESPONSE["content"][0])]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "5"}]},
    ]
    end_response: dict[str, Any] = {
        "content": [{"type": "text", "text": "答えは 5"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 20, "output_tokens": 7},
    }
    records = {
        cassette_key(
            model=spec.model, system_prompt=spec.system_prompt, messages=turn1_messages, tools=provider_tools
        ): _TOOL_USE_RESPONSE,
        cassette_key(
            model=spec.model, system_prompt=spec.system_prompt, messages=turn2_messages, tools=provider_tools
        ): end_response,
    }
    path = tmp_path / "cassette.json"
    _write_cassette(path, records)
    run = run_agent(spec, "2と3を足して", provider=cassette(0, path=path), seed=0)
    assert run.stop_reason == "end_turn"
    assert run.turns == 2  # tool_use → end_turn の 2 往復
    assert run.tools_used == ("calculator",)
    assert run.output == "答えは 5"
    # usage は 2 ターンの合算（フィクスチャの構成から：10+20 / 5+7）。
    assert run.usage == {"input_tokens": 30, "output_tokens": 12}


@pytest.mark.unit
def test_cassette_factory_requires_path(tmp_path: Path) -> None:
    # PROVIDERS 経由の factory(seed) 呼び（`agent run` の規約）は path を渡せない＝明示エラーで止まる。
    with pytest.raises(ValueError, match="path"):
        PROVIDERS.resolve("cassette").factory(0)
    # 壊れた cassette（辞書でない JSON）は読み込みで明示エラー（黙って空扱いしない）。
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="cassette"):
        load_cassette(bad)


@pytest.mark.unit
def test_cassette_provider_is_replay_only(tmp_path: Path) -> None:
    # 空の記録で作った provider はどの入力にも fail closed（record モードが無いことの固定）。
    spec = AgentSpec(name="empty", provider="cassette", model="claude-test", system_prompt="x")
    provider = CassetteProvider(seed=0, records={})
    with pytest.raises(ValueError, match="cassette に記録が無い"):
        provider.reply(messages=build_messages("何か"), tools=[], spec=spec)


# --- AnthropicProvider（effort を送る・temperature を送らない・実クライアントは作らない） ---


@pytest.mark.unit
def test_anthropic_provider_sends_effort_not_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic  # テスト環境は uv sync --all-extras（monkeypatch のためだけに import・実クライアントは作らない）

    captured: dict[str, Any] = {}

    class _FakeResponse:
        @staticmethod
        def model_dump() -> dict[str, Any]:
            return _TEXT_RESPONSE

    class _FakeMessages:
        @staticmethod
        def create(**kwargs: Any) -> _FakeResponse:
            captured.update(kwargs)
            return _FakeResponse()

    class _FakeClient:
        def __init__(self) -> None:
            self.messages = _FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)
    spec = AgentSpec(name="real", provider="anthropic", model="claude-opus-4-8", system_prompt="検証用", effort="high")
    messages = build_messages("ping")
    reply = AnthropicProvider(seed=0).reply(messages=messages, tools=[], spec=spec)
    assert "temperature" not in captured  # 現行モデルは temperature を受けない（送ると 400）
    assert captured["output_config"] == {"effort": "high"}  # 決定性の軸＝宣言に固定した effort
    assert captured["model"] == "claude-opus-4-8"
    assert captured["system"] == "検証用"
    assert captured["messages"] == messages
    assert captured["tools"] == []
    assert captured["max_tokens"] > 0  # 既定の上限が渡る（値の具体は実装定数＝ここでは正値のみ検査）
    assert reply == _reply_from_anthropic(_TEXT_RESPONSE)  # 応答は共有 adapter を通る


# --- カタログ（：全 provider に説明文） ---


@pytest.mark.unit
def test_all_providers_have_descriptions() -> None:
    for kind in ("dummy", "anthropic", "cassette"):
        assert kind in PROVIDERS, f"PROVIDERS に '{kind}' が登録されていない"
    for kind, entry in PROVIDERS.items():
        assert entry.description, f"PROVIDERS['{kind}'] に説明文が無い（カタログに載れない）"
