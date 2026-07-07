"""goal-based 停止ゲート（評価器が合格と言うまで続行する loop・T-0095・DEC-0017）。

AGENTS 第一原則「完了＝検証にすべて成功したときだけ・自己申告で完了にしない」をエージェント実行そのものへ
機械化したもの：モデルの `end_turn`（「完了した気になった」）を、宣言済みの評価器（`AGENT_METRICS`＋
`eval.passes`・fail closed）が検査し、未達なら続行を注入する。maker（モデル）≠checker（評価器）の構図が
ループ内に入る（docs/learnings.md 参照）。

- `run_agent` を丸ごと再利用し、goal ループはその外側に巻く（往復ループの再実装をしない＝DEC-0006）。
- ゲートの合否は既存 `eval.passes`（NaN・欠けは不合格・未登録名は ValueError）をそのまま使う＝
  新しい合否機構を作らない。
- 「止めさせない」の backstop は `max_cycles`（黙って無限ループしない＝`runtime.run_agent` の `max_turns`
  と同じ規律）。
- 依存は stdlib＋agent 内＋`harness.loops` のみ（軽 import・DEC-0013）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from harness import loops
from harness.agent.eval import AGENT_METRICS, passes
from harness.agent.providers import Provider
from harness.agent.runtime import AgentRun, run_agent
from harness.agent.spec import AgentSpec

# goal-based ループの既定続行文。評価器ゲートが未達と判定したときに次サイクルへ渡す user 発話。
# 方針（続行のしかた）はゲートでなくループ側の引数＝trigger×stop×policy の分離を写す（item.md）。
DEFAULT_CONTINUE_PROMPT = "まだ成功基準を満たしていない。前の応答を見直して続けること。"


@dataclass(frozen=True, kw_only=True)
class Goal:
    """人が宣言する成功基準（自動生成しない）。expected と thresholds は呼び手が golden set から決める。

    metrics：採点に使う `AGENT_METRICS` の kind の並び（既定は exact_match の 1 つ）。
    thresholds：`eval.passes` に渡す閾値（未登録名は passes 側で候補一覧つき ValueError＝fail closed）。
    """

    expected: str
    metrics: tuple[str, ...] = ("exact_match",)
    thresholds: Mapping[str, float]


@dataclass(frozen=True)
class GoalGate:
    """`loops.StopCondition` を実装するゲート。既存の採点器（`AGENT_METRICS`）と合否（`eval.passes`）だけで
    合否を決める＝新しい合否機構を作らない。

    stop 時は `reason="goal_met"`。未達時はスコア入りの `"goal_not_met: exact_match=0.000"` 形式
    （来歴で人が読める）。未登録 metric 名は `AGENT_METRICS.resolve` の候補一覧つき ValueError
    （既存挙動の流用＝新しいエラー経路を作らない）。
    """

    goal: Goal

    def check(self, *, output: str, iteration: int) -> loops.StopDecision:
        del iteration  # 骨組みでは未使用（来歴の記録は呼び手＝run_agent_to_goal 側が gate_reasons に残す）
        scores = {name: AGENT_METRICS.resolve(name).fn(self.goal.expected, output) for name in self.goal.metrics}
        if passes(scores, dict(self.goal.thresholds)):
            return loops.StopDecision(stop=True, reason="goal_met")
        detail = "  ".join(f"{name}={scores[name]:.3f}" for name in self.goal.metrics)
        return loops.StopDecision(stop=False, reason=f"goal_not_met: {detail}")


@dataclass(frozen=True)
class GoalRun:
    """goal-based ループ 1 回の結果。gate_reasons は各サイクルの判定＝来歴（表示・監視の入力）。"""

    final: AgentRun
    cycles: int
    stop_reason: str  # "goal_met" | "max_cycles"
    gate_reasons: tuple[str, ...]


def run_agent_to_goal(
    spec: AgentSpec,
    user_input: str,
    *,
    provider: Provider,
    gate: loops.StopCondition,
    continue_prompt: str = DEFAULT_CONTINUE_PROMPT,
    seed: int,
    max_cycles: int = 4,
    max_turns: int | None = None,
) -> GoalRun:
    """`run_agent` を繰り返し、`gate`（既定は `GoalGate`）が合格と言うまで続行注入する（純関数）。

    1 サイクル＝`run_agent` 1 回＋`gate.check`。未達なら `run_agent(spec, continue_prompt,
    prior_messages=直前の messages, ...)` で会話履歴を保ったまま続ける。`max_cycles` に到達したら
    `stop_reason="max_cycles"` で必ず止まる（黙って無限ループしない）。`max_cycles` は 1 以上
    （`runtime.run_agent` の `max_turns` チェックと同文言の規律）。ネットワーク・ファイル I/O はしない。
    """
    if max_cycles < 1:
        raise ValueError(f"max_cycles は 1 以上（実際: {max_cycles}）")
    gate_reasons: list[str] = []
    current_input = user_input
    prior_messages: tuple[Mapping[str, Any], ...] = ()
    cycle = 0
    while True:
        cycle += 1
        run = run_agent(
            spec, current_input, provider=provider, seed=seed, max_turns=max_turns, prior_messages=prior_messages
        )
        decision = gate.check(output=run.output, iteration=cycle)
        gate_reasons.append(decision.reason)
        if decision.stop:
            return GoalRun(final=run, cycles=cycle, stop_reason="goal_met", gate_reasons=tuple(gate_reasons))
        if cycle >= max_cycles:
            return GoalRun(final=run, cycles=cycle, stop_reason="max_cycles", gate_reasons=tuple(gate_reasons))
        current_input = continue_prompt
        prior_messages = run.messages
