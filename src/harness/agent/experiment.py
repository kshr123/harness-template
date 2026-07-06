"""エージェント評価の一巡（golden set → provider → 採点 → 合否）。fold は無い（全体に 1 回）。

ML の run_experiment と同型の「評価→合否」だが、交差検証は不要（cases＝golden set が検証データそのもの）。
変種比較（leaderboard）と昇格（promote）は後続タスク（T-0090）で足す。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from harness.agent.eval import AGENT_METRICS, passes
from harness.agent.providers import Provider, build_messages, reply_text
from harness.agent.spec import AgentSpec


@dataclass(frozen=True, kw_only=True)
class AgentEvalResult:
    """評価 1 回の結果（採点器名→平均スコア・合否・件数）。"""

    metrics: dict[str, float]
    passed: bool
    n: int


def run_agent_eval(
    spec: AgentSpec,
    cases: Sequence[Mapping[str, Any]],
    *,
    provider: Provider,
    metrics: Sequence[str],
    thresholds: Mapping[str, float],
    seed: int,
) -> AgentEvalResult:
    """cases（[{id, input, expected}] の golden set）を provider に通し、採点器の平均と合否を返す。

    metrics は AGENT_METRICS の kind の並び（未知名はここで ValueError＝候補一覧つき）。合否は
    `passes`（AGENT_METRICS の向き・fail closed）。seed は明示で受ける規約（グローバル種禁止）：
    dummy/cassette では応答導出に使い、exact 系の採点では未使用（サンプリング採点を足すときの口）。
    """
    if not cases:
        raise ValueError("cases が空（golden set には 1 件以上の {id, input, expected} が要る）")
    fns = {name: AGENT_METRICS.resolve(name).fn for name in metrics}
    scores: dict[str, list[float]] = {name: [] for name in fns}
    for case in cases:
        reply = provider.reply(messages=build_messages(str(case["input"])), tools=(), spec=spec)
        predicted = reply_text(reply)
        for name, fn in fns.items():
            scores[name].append(float(fn(str(case["expected"]), predicted)))
    means = {name: sum(values) / len(values) for name, values in scores.items()}
    return AgentEvalResult(metrics=means, passed=passes(means, dict(thresholds)), n=len(cases))
