"""記録再生（cassette）プロバイダ＝実 SDK 応答の固定フィクスチャを無ネットワークで再生する（replay 専用）。

- 目的：**SDK 応答形状 → ProviderReply の変換（共有 adapter `_reply_from_anthropic`）を verify で守る**。
  応答 dict は実呼び出し（AnthropicProvider）と同じ adapter を通る＝実 SDK の応答形状が変わったら
  cassette の再記録（フィクスチャの書き直し）で検知できる。
- cassette＝JSON ファイル：`{ <キー>: <応答 dict（model_dump 相当）> }`。
  キー＝`(model, system_prompt, messages, tools)` の正準 JSON の sha256（`harness.fingerprint.input_fingerprint`
  を再利用＝導出は cassette_key の 1 か所。テストも同じ関数で期待キーを組む）。
- **record モードは無い**（実記録はネットワーク＝verify 外・DEC-0015。フィクスチャは API 契約から手で書く
  ＝実装出力のコピーでなく仕様の写し）。記録が無いキーは ValueError（**fail closed**＝黙って dummy へ
  フォールバックしない）。
- PROVIDERS へは providers.py 側が `cassette` kind（工場 cassette_replay・遅延 import）で登録する
  （カタログ `agent providers` に載せる＝DEC-0009 の発見性。登録をここに置くと import 順で一覧が変わるため）。
- import は stdlib＋harness.fingerprint＋harness.agent.{providers,spec} のみ（anthropic は import しない
  ＝軽 import・DEC-0013・無ネットワーク）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.agent.providers import ProviderReply, _reply_from_anthropic
from harness.agent.spec import AgentSpec
from harness.fingerprint import input_fingerprint


def cassette_key(
    *,
    model: str,
    system_prompt: str,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
) -> str:
    """cassette のキー＝(model, system_prompt, messages, tools) の正準 JSON の sha256。

    導出はこの 1 か所（CassetteProvider.reply とテストが同じ関数で組む＝キーのずれを作らない）。
    messages/tools は JSON 由来の dict の並び（run_agent/build_messages/to_provider_tools が作る形）。
    """
    return input_fingerprint(
        {
            "model": model,
            "system_prompt": system_prompt,
            "messages": [dict(m) for m in messages],
            "tools": [dict(t) for t in tools],
        }
    )


def load_cassette(path: Path | str) -> dict[str, dict[str, Any]]:
    """cassette JSON（{キー: 応答 dict}）を読み込む。辞書でない・値が辞書でない形は明示エラー。

    値（応答 dict）の中身の検査は再生時の共有 adapter が行う（欠損は fail loud＝providers.py 参照）。
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not all(isinstance(v, dict) for v in raw.values()):
        raise ValueError(f"{path}: cassette は {{sha256 キー: 応答 dict}} の JSON 辞書であること")
    return raw


@dataclass(frozen=True)
class CassetteProvider:
    """記録再生プロバイダ（replay 専用）。records に無いキーは ValueError（fail closed）。

    seed は明示 seed 規約の署名合わせ（再生は決定的＝未使用）。records は load_cassette の返り値
    （工場 cassette() が path から読んで詰める）。
    """

    seed: int
    records: Mapping[str, Mapping[str, Any]]

    def reply(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        spec: AgentSpec,
    ) -> ProviderReply:
        key = cassette_key(model=spec.model, system_prompt=spec.system_prompt, messages=messages, tools=tools)
        record = self.records.get(key)
        if record is None:
            raise ValueError(
                f"cassette に記録が無い（key={key}・model={spec.model}）。fail closed＝dummy 応答へは"
                "フォールバックしない。フィクスチャを API 契約から書き足すこと（record モードは無い・T-0092）"
            )
        return _reply_from_anthropic(record)


def cassette(seed: int, *, path: Path | str | None = None) -> CassetteProvider:
    """記録再生プロバイダ（replay 専用・fail closed・無ネットワーク）。テスト/CI 用＝path（記録 JSON）必須。

    PROVIDERS の工場呼び出し規約（`factory(seed)`）と署名互換にするため path は省略可の形だが、
    省略は明示エラー（`agent run` の宣言 provider には dummy/anthropic を使う＝黙って壊れない）。
    """
    if path is None:
        raise ValueError(
            "cassette には path=（記録 JSON のパス）が必須（テスト/CI 用の記録再生。"
            "`agent run` の宣言 provider には dummy か anthropic を使う）"
        )
    return CassetteProvider(seed=seed, records=load_cassette(path))
