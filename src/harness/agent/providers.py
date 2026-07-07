"""プロバイダ抽象（Provider Protocol＋PROVIDERS レジストリ）。骨組みでは dummy のみ登録。

- ProviderReply は Anthropic の content block 形（{"type": "text", "text": ...} の並び）に素直：
  実プロバイダ（T-0092・AnthropicProvider/CassetteProvider）を足しても呼び手が変わらない差し替え口。
- dummy は**決定的・無ネットワーク・課金ゼロ**：入力メッセージ＋seed の正準 JSON の sha256 から
  テキストを導く（グローバル種は使わない）。replies で「この入力にはこの応答」を仕込める（テスト・スモーク用）。
- このモジュールは軽い（stdlib＋harness.registry のみ）。anthropic SDK は top では import しない：
  AnthropicProvider.reply() の中で遅延 import する（extra `agent` 無しでも `import harness.agent` が
  壊れない＝軽 import・DEC-0013。verify 経路は dummy/cassette のみ＝無ネットワーク・DEC-0015）。
- 応答 adapter `_reply_from_anthropic`（Anthropic Messages API 応答 dict → ProviderReply）は
  AnthropicProvider（実呼び出し）と CassetteProvider（記録再生・cassette.py）が共有する＝
  SDK 応答形状のドリフトを無ネットワークのテストで検知する 1 か所。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from harness.agent.spec import AgentSpec
from harness.registry import Entry, Registry

if TYPE_CHECKING:
    from harness.agent.cassette import CassetteProvider


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


def _reply_from_anthropic(data: Mapping[str, Any]) -> ProviderReply:
    """Anthropic Messages API 応答 dict（`resp.model_dump()` 相当）→ ProviderReply の純変換（共有 adapter）。

    AnthropicProvider（実呼び出し）と CassetteProvider（記録再生）の両方がここを通る＝この関数の
    テストがそのまま「SDK 応答形状 → ProviderReply」の契約検査になる（無ネットワーク・SDK 不在でも動く
    ＝anthropic を import しない）。欠損・未知の block type は明示 ValueError（黙って握りつぶすと
    SDK 応答形状のドリフトを見逃す＝fail loud）。
    """
    stop_reason = data.get("stop_reason")
    if not isinstance(stop_reason, str) or not stop_reason:
        raise ValueError(f"Anthropic 応答に stop_reason（str）が無い（実際: {stop_reason!r}）")
    usage_raw = data.get("usage")
    if not isinstance(usage_raw, Mapping) or not {"input_tokens", "output_tokens"} <= set(usage_raw):
        raise ValueError(f"Anthropic 応答に usage（input_tokens/output_tokens）が無い（実際: {usage_raw!r}）")
    content = data.get("content")
    if not isinstance(content, Sequence) or isinstance(content, str):
        raise ValueError(f"Anthropic 応答の content が block の並びでない（実際: {content!r}）")
    blocks: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, Mapping):
            raise ValueError(f"content block が辞書でない（実際: {block!r}）")
        btype = block.get("type")
        if btype == "text":
            if not isinstance(block.get("text"), str):
                raise ValueError(f"text block に text（str）が無い（実際: {dict(block)!r}）")
            blocks.append({"type": "text", "text": block["text"]})
        elif btype == "tool_use":
            missing = sorted(key for key in ("id", "name", "input") if block.get(key) is None)
            if missing:
                raise ValueError(f"tool_use block に {missing} が無い（応答形状のドリフト？実際: {dict(block)!r}）")
            blocks.append(
                {"type": "tool_use", "id": str(block["id"]), "name": str(block["name"]), "input": dict(block["input"])}
            )
        else:
            raise ValueError(f"未知の content block type {btype!r}（text | tool_use のみ対応。分岐を足して対応する）")
    return ProviderReply(
        stop_reason=stop_reason,
        content=tuple(blocks),
        usage={"input_tokens": int(usage_raw["input_tokens"]), "output_tokens": int(usage_raw["output_tokens"])},
    )


# 実プロバイダの応答トークン上限（骨組みの既定。可変にする必要が見えたら AgentSpec に載せる＝YAGNI）。
_ANTHROPIC_MAX_TOKENS = 4096


@dataclass(frozen=True)
class AnthropicProvider:
    """実 Anthropic 呼び出し。SDK は reply() 内で遅延 import（軽 import・DEC-0013）＝verify 経路外。

    決定性は effort（`output_config={"effort": spec.effort}`）＝宣言に固定した推論の深さで作る。
    **temperature は送らない**（現行モデルはパラメータごと廃止＝送ると 400・DEC-0015）。
    API キーは環境変数から SDK が読む（コードでは読まない・書かない）。seed は明示 seed 規約の
    署名合わせ（実 API に乱数種は無い＝未使用）。
    """

    seed: int

    def reply(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        spec: AgentSpec,
    ) -> ProviderReply:
        import anthropic  # 遅延 import：extra `agent` 無しでも本モジュールの import は壊れない（DEC-0013）

        client = anthropic.Anthropic()  # API キーは環境変数（コードは読まない・プロンプトに書かない）
        resp = client.messages.create(
            model=spec.model,
            system=spec.system_prompt,
            # SDK の TypedDict（MessageParam/ToolParam）と dict は mypy 上は別物＝実行形は同じなので cast。
            messages=cast("Any", [dict(m) for m in messages]),
            tools=cast("Any", [dict(t) for t in tools]),
            max_tokens=_ANTHROPIC_MAX_TOKENS,
            output_config={"effort": spec.effort},  # temperature/top_p/top_k は送らない（DEC-0015）
        )
        return _reply_from_anthropic(resp.model_dump())


def anthropic_provider(seed: int, *, replies: Mapping[str, Any] | None = None) -> AnthropicProvider:
    """実 Anthropic プロバイダ（要 `uv sync --extra agent`・API キーは環境変数）。verify 経路では使わない。

    工場の署名は dummy と互換（`factory(seed, replies=…)` 呼びを壊さない）。replies は実呼び出しでは
    未使用＝無視する（台本は dummy/cassette の関心）。決定性は effort を宣言に固定して作る＝
    temperature は送らない（DEC-0015）。
    """
    del replies  # 署名互換のためだけの引数（実 API に台本は無い）
    return AnthropicProvider(seed=seed)


def cassette_replay(seed: int, *, path: Path | str | None = None) -> CassetteProvider:
    """記録再生（replay 専用・fail closed・無ネットワーク）。テスト/CI 用＝path（記録 JSON）が必須。

    実体は harness.agent.cassette（関数内 import は循環回避＝cassette.py が共有 adapter を
    ここから import するため）。PROVIDERS へは本 kind で登録しカタログに載せる（DEC-0009 の発見性）。
    `agent run` の `factory(seed)` 呼びは path を渡せない＝省略は cassette 側の明示エラーで止まる。
    """
    from harness.agent.cassette import cassette

    return cassette(seed, path=path)


# AgentSpec の provider に書ける kind → 工場。実プロバイダは extras_hint（`uv sync --extra agent`）で案内する。
PROVIDERS: Registry[Entry] = Registry("プロバイダ", catalog="agent providers", extras_hint={"anthropic": "agent"})
PROVIDERS.register("dummy", dummy)
PROVIDERS.register("anthropic", anthropic_provider)
PROVIDERS.register("cassette", cassette_replay)
