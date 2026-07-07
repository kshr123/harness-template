"""エージェント実行の往復ループ（純関数）と、1 実行を JSONL に残すログ契約（AGENT_LOG_FIELDS）。

- run_agent は provider の stop_reason に従って **ツールを呼ぶ→結果を渡す→また考える** を繰り返す。
  上限（spec.max_turns・引数 max_turns で上書き）に達したら stop_reason="max_turns" で必ず止まる
  （黙って無限ループしない）。ネットワーク・ファイル I/O はしない（無ネットワークの verify 契約）。
- AGENT_LOG_FIELDS は JSONL 1 行の契約の正本（serve.PREDICTION_LOG_FIELDS と同型の「キー集合ドリフトを
  止める」規律）。監視（T-0093）はこの契約だけに依存する（勝手にキーを増減・改名しない）。
- 依存は stdlib＋agent 内＋harness.fingerprint のみ（軽 import）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.agent.providers import Provider, ProviderReply, _last_user_text, build_messages, reply_text
from harness.agent.spec import AgentSpec
from harness.agent.tools import TOOLS, ToolEntry, run_tool, to_provider_tools
from harness.fingerprint import input_fingerprint
from harness.registry import Registry

# エージェント実行 JSONL の行スキーマ（キー→型と意味）。1 行＝1 実行。この辞書のキー集合と各行のキー集合は
# 一致する（build_log_row が検査する）。変更は契約の変更＝docs/agent.md と消費側（監視 T-0093）を同時に直すこと。
AGENT_LOG_FIELDS: dict[str, str] = {
    "time": "str（ISO 8601・UTC）",
    "request_id": "str（uuid4 hex）",
    "agent": "dict（name: str・provider: str・model: str・prompt_fingerprint: str＝system_prompt の sha256）",
    "input_fingerprint": "str（{'input': 入力テキスト} の正準 JSON の sha256。input_fingerprint で再計算できる）",
    "input": "str（ユーザ入力＝messages 先頭の user テキスト）",
    "output": "str（最終応答テキスト）",
    "stop_reason": "str（end_turn | max_turns＝上限打ち切り | その他 provider の stop_reason）",
    "turns": "int（provider 呼び出し回数）",
    "tools_used": "list[str]（呼んだツール名・呼んだ順。同じツールは呼んだ回数だけ並ぶ）",
    "usage": "dict（input_tokens: int・output_tokens: int＝全ターンの合算）",
}


@dataclass(frozen=True)
class AgentRun:
    """run_agent 1 回の結果。messages は会話履歴の全量（配信 T-0094 が使う・ログには畳み込まない）。"""

    output: str
    stop_reason: str
    turns: int
    tools_used: tuple[str, ...]
    usage: dict[str, int]
    messages: tuple[Mapping[str, Any], ...]


def run_agent(
    spec: AgentSpec,
    user_input: str,
    *,
    provider: Provider,
    tools: Registry[ToolEntry] = TOOLS,
    seed: int,
    max_turns: int | None = None,
    prior_messages: Sequence[Mapping[str, Any]] = (),
) -> AgentRun:
    """ツール往復ループの一巡（純関数）。stop_reason が tool_use の間はツールを実行して結果を返し続ける。

    上限は spec.max_turns（引数 max_turns は上書き口）。到達したら stop_reason="max_turns" で打ち切る
    （turns＝provider 呼び出し回数）。ツールは順に実行し、ツールが投げたらそのまま止まる（再試行方針は
    監視 T-0093 で必要が見えてから＝YAGNI）。seed は明示で受ける規約（グローバル種禁止）：dummy/cassette
    は生成時に seed を持つため未使用＝サンプリング実行を足すときの口（run_agent_eval と同じ扱い）。

    prior_messages は続行口（省略時 () ＝従来どおりの挙動・後方互換）：会話履歴の続きから始めたいとき
    （goal-based ループが「続けろ」を注入する T-0095）に渡す。`[*prior_messages, *build_messages(user_input)]`
    で開始する＝過去の往復を保ったまま新しい user 発話を積む。
    """
    limit = max_turns if max_turns is not None else spec.max_turns
    if limit < 1:
        raise ValueError(f"max_turns は 1 以上（実際: {limit}）")
    provider_tools = to_provider_tools(spec.tools, registry=tools)
    messages: list[dict[str, Any]] = [dict(m) for m in prior_messages]
    messages.extend(build_messages(user_input))
    usage = {"input_tokens": 0, "output_tokens": 0}
    tools_used: list[str] = []
    turns = 0
    reply: ProviderReply | None = None
    for _ in range(limit):
        reply = provider.reply(messages=messages, tools=provider_tools, spec=spec)
        turns += 1
        for key in usage:
            usage[key] += int(reply.usage.get(key, 0))
        messages.append({"role": "assistant", "content": [dict(block) for block in reply.content]})
        if reply.stop_reason != "tool_use":  # end_turn ほか＝ここで完了
            return AgentRun(
                output=reply_text(reply),
                stop_reason=reply.stop_reason,
                turns=turns,
                tools_used=tuple(tools_used),
                usage=usage,
                messages=tuple(messages),
            )
        results: list[dict[str, Any]] = []
        for block in reply.content:
            if block.get("type") != "tool_use":
                continue
            name = str(block.get("name", ""))
            result = run_tool(name, dict(block.get("input") or {}), registry=tools)
            tools_used.append(name)
            results.append({"type": "tool_result", "tool_use_id": str(block.get("id", "")), "content": result})
        messages.append({"role": "user", "content": results})
    # ここに来る＝limit 回すべて tool_use（黙って回り続けず打ち切りを明示する）。
    assert reply is not None  # limit >= 1 を上で保証済み（mypy の絞り込み用）
    return AgentRun(
        output=reply_text(reply),
        stop_reason="max_turns",
        turns=turns,
        tools_used=tuple(tools_used),
        usage=usage,
        messages=tuple(messages),
    )


def build_log_row(run: AgentRun, *, spec: AgentSpec, request_id: str, time: str) -> dict[str, Any]:
    """1 実行の JSONL 行（AGENT_LOG_FIELDS の契約どおり）を組み立てる。キー集合がずれたら ValueError。

    input は run.messages 先頭の user テキストから復元する（run_agent が build_messages で必ず先頭に積む＝
    引数で二重に受けない）。input_fingerprint は {"input": テキスト} の指紋＝harness.fingerprint で再計算できる。
    """
    user_input = _last_user_text(run.messages[:1])
    entry: dict[str, Any] = {
        "time": time,
        "request_id": request_id,
        "agent": {
            "name": spec.name,
            "provider": spec.provider,
            "model": spec.model,
            # store._prompt_fingerprint と同じ導出（system_prompt の sha256＝どの宣言の実行かの印）。
            "prompt_fingerprint": hashlib.sha256(spec.system_prompt.encode("utf-8")).hexdigest(),
        },
        "input_fingerprint": input_fingerprint({"input": user_input}),
        "input": user_input,
        "output": run.output,
        "stop_reason": run.stop_reason,
        "turns": run.turns,
        "tools_used": list(run.tools_used),
        "usage": dict(run.usage),
    }
    if entry.keys() != AGENT_LOG_FIELDS.keys():  # 契約からのドリフトをここで止める（serve と同じ規律）
        raise ValueError(f"ログ行のキーが契約とずれている: {sorted(entry)} != {sorted(AGENT_LOG_FIELDS)}")
    return entry


def agent_log_path(root: Path, *, name: str, log_dir: Path | None = None, when: datetime | None = None) -> Path:
    """実行 JSONL の置き場。既定 `artifacts/agent/runs/<name>/<YYYYMMDD>.jsonl`（UTC の日付で 1 ファイル）。

    log_dir を渡すと `<log_dir>/<YYYYMMDD>.jsonl`（エージェント名のディレクトリを掘らない＝呼び手が置き場を
    決める）。既定は `agent monitor` の既定 glob `artifacts/agent/runs/**/*.jsonl` に一致する＝配信（T-0094）の
    ログをそのまま監視が読める（serve.runtime.log_path と同型。serve は import しない＝プロファイル境界）。
    """
    stamp = (when if when is not None else datetime.now(UTC)).strftime("%Y%m%d")
    base = log_dir if log_dir is not None else root / "artifacts" / "agent" / "runs" / name
    return base / f"{stamp}.jsonl"


def append_run_log(path: Path, row: Mapping[str, Any]) -> None:
    """JSONL に 1 行追記する（1 行＝1 JSON・UTF-8・非 ASCII 素通し）。親ディレクトリは無ければ作る。

    `build_log_row` の返り値をそのまま書ける（stdlib のみ。serve の append_jsonl は import しない＝
    プロファイル境界。小さな重複は境界維持の許容コスト＝3 個目の消費で core 昇格を  判断）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
