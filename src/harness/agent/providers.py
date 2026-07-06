"""プロバイダ抽象（Provider Protocol＋PROVIDERS レジストリ）。骨組みでは dummy のみ登録。

- ProviderReply は Anthropic の content block 形（{"type": "text", "text": ...} の並び）に素直：
  実プロバイダ（T-0092・AnthropicProvider/CassetteProvider）を足しても呼び手が変わらない差し替え口。
- dummy は**決定的・無ネットワーク・課金ゼロ**：入力メッセージ＋seed の正準 JSON の sha256 から
  テキストを導く（グローバル種は使わない）。replies で「この入力にはこの応答」を仕込める（テスト・スモーク用）。
- このモジュールは軽い（stdlib＋harness.registry のみ）。anthropic SDK はここから import しない
  （extra `agent` の遅延 import は T-0092 で足す＝verify 経路の無ネットワークを守る・DEC-0015）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from harness.agent.spec import AgentSpec
from harness.registry import Entry, Registry


@dataclass(frozen=True)
class ProviderReply:
    """プロバイダの 1 応答。content は Anthropic content block 形の並び（text 抽出は reply_text）。"""

    stop_reason: str
    content: tuple[Mapping[str, Any], ...]
    usage: Mapping[str, int]


class Provider(Protocol):
    """プロバイダの差し替え口。messages（role/content の並び）と spec を受けて 1 応答を返す。"""

    def reply(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        spec: AgentSpec,
    ) -> ProviderReply: ...


def reply_text(reply: ProviderReply) -> str:
    """応答の text block を連結して 1 文字列にする（採点・表示の共通経路）。"""
    return "".join(str(block.get("text", "")) for block in reply.content if block.get("type") == "text")


def build_messages(text: str) -> list[dict[str, Any]]:
    """ユーザ発話 1 件のメッセージ列を作る（experiment と CLI の共通形。system は spec 側が持つ）。"""
    return [{"role": "user", "content": [{"type": "text", "text": text}]}]


def _dummy_script_key(messages: Sequence[Mapping[str, Any]]) -> str:
    """dummy の台本（replies）を引く鍵。通常は最後の user テキスト・直近が tool_result なら "tool_result:<結果>"。

    tool_result 後の続き（text でも tool_use でも）を replies で台本化できるようにする（run_agent の
    往復テスト・max_turns 打ち切りテストの土台）。鍵は結果文字列から決まる＝構成から導出できる。
    """
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, Sequence) and not isinstance(content, str):
            for block in content:
                if isinstance(block, Mapping) and block.get("type") == "tool_result":
                    return "tool_result:" + str(block.get("content", ""))
        break  # 最後の user が tool_result でなければ通常経路（テキストの鍵）
    return _last_user_text(messages)


def _last_user_text(messages: Sequence[Mapping[str, Any]]) -> str:
    """最後の user メッセージのテキスト（str 直書きでも content block の並びでも取り出せる）。"""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, Sequence):
            return "".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, Mapping) and block.get("type") == "text"
            )
    return ""


@dataclass(frozen=True)
class DummyProvider:
    """決定的なダミー応答。replies の値が str なら text 応答・{"tool_use": …} なら tool_use 応答。

    鍵は _dummy_script_key（通常＝最後の user テキスト・直近が tool_result なら "tool_result:<結果>"）。
    どちらの経路も仕込みが無ければハッシュ由来のテキスト（決定的・グローバル種に依らない）。
    """

    seed: int
    replies: Mapping[str, Any]

    def reply(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        spec: AgentSpec,
    ) -> ProviderReply:
        scripted = self.replies.get(_dummy_script_key(messages))
        if isinstance(scripted, Mapping) and "tool_use" in scripted:
            block = dict(scripted["tool_use"])  # {"name": …, "input": …, "id"?: …}
            return ProviderReply(
                stop_reason="tool_use",
                content=(
                    {
                        "type": "tool_use",
                        "id": str(block.get("id", "tool_0")),
                        "name": str(block["name"]),
                        "input": dict(block["input"]),
                    },
                ),
                usage={"input_tokens": 0, "output_tokens": 0},
            )
        text = scripted if isinstance(scripted, str) else None
        if text is None:
            # 正準 JSON（キー昇順）の sha256 ＝同じ入力・同じ seed なら常に同じ応答（グローバル種に依らない）。
            payload = json.dumps(
                {"seed": self.seed, "messages": [dict(m) for m in messages]}, sort_keys=True, ensure_ascii=False
            )
            text = "dummy:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return ProviderReply(
            stop_reason="end_turn",
            content=({"type": "text", "text": text},),
            usage={"input_tokens": 0, "output_tokens": 0},
        )


def dummy(seed: int, *, replies: Mapping[str, Any] | None = None) -> DummyProvider:
    """決定的なダミー応答（無ネットワーク・課金ゼロ）。verify のスモークとテストの土台。

    replies={"入力": "応答"} で既知の応答を仕込める（exact_match の期待を構成から導くため）。
    値に {"tool_use": {"name", "input", "id"?}} を仕込むと tool_use 応答（往復ループの台本化）。
    tool_result 後の続きは鍵 "tool_result:<結果文字列>" で仕込む（無ければハッシュ由来のテキスト）。
    仕込みが無い入力には正準 JSON ハッシュ由来の "dummy:<hex16>" を返す（決定的・期待と衝突しない）。
    """
    return DummyProvider(seed=seed, replies=dict(replies or {}))


# AgentSpec の provider に書ける kind → 工場。実プロバイダは extras_hint（`uv sync --extra agent`）で案内する。
PROVIDERS: Registry[Entry] = Registry("プロバイダ", catalog="agent providers", extras_hint={"anthropic": "agent"})
PROVIDERS.register("dummy", dummy)
