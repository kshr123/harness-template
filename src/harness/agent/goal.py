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
- 依存は stdlib＋agent 内のみ（軽 import・DEC-0013）。`StopDecision`／`StopCondition`（trigger×stop×policy の
  停止語彙）は元は core `harness.loops` にあったが、実消費が本ファイルの 1 つだけだったため DEC-0020 で
  ここへ畳み込んだ（core 再昇格は 2 個目の実 import 消費が出たときに DEC-0012 で判断）。
- goal は**宣言（YAML）が正本**（`goal_from_mapping`/`load_goal`）：自由文の成功基準は `llm_judge`（rubric＝
  `expected`）で採点する（T-0096）。`GoalGate` は metric 名の entry 型（`JudgeEntry` か否か）でしか分岐しない
  ＝exact_match だけの goal は無変更（「ゲートは metric 名しか見ない」の証明）。provider の束ね（judge の
  実体化）は `gate_from_goal`（goal.yaml の読み込み点）の 1 か所に閉じる。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from harness.agent.eval import AGENT_METRICS, JudgeEntry, passes
from harness.agent.judge import JUDGE_SYSTEM_PROMPT, RubricJudge, make_rubric_judge
from harness.agent.providers import PROVIDERS, Provider
from harness.agent.runtime import AgentRun, run_agent
from harness.agent.spec import AgentSpec, spec_from_mapping


@dataclass(frozen=True, kw_only=True)
class StopDecision:
    """停止判定の結果。reason は人が読む文字列（"goal_met" 等）。

    enum にしない：消費は表示と来歴（ログ・CLI 出力）だけで、新しい理由の追加を型変更にしたくない
    （閉じた集合にすると新しい stop 理由を足すたびに型を直す羽目になる＝YAGNI）。

    元は core `harness.loops` の型（DEC-0017）。実消費が本ファイルの 1 つだけだったため DEC-0020 で
    agent へ畳み込んだ（trigger×stop×policy の 4 類型の分類そのものは docs/agent.md の loops 節が正本）。
    """

    stop: bool
    reason: str


class StopCondition(Protocol):
    """停止条件の差し替え口。1 サイクルの出力を見て続けるか止めるかを判定する。

    骨組みでは**テキスト出力への門だけ**（`output: str`）。引数をもっと一般化する（構造化出力・複数指標の
    生スコアを直接渡す等）のは 2 個目の消費（ds sweep の閾値探索等）が実際に必要になってから
    DEC-0012 で判断する（早すぎる一般化はしない＝EP-23 item.md）。シグネチャは DEC-0018 で agent 形状に
    固定済み（`tests/test_agent_goal.py::test_stop_condition_signature_stays_agent_shaped_until_dec` が番人）。
    """

    def check(self, *, output: str, iteration: int) -> StopDecision: ...


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

    `judge`：`llm_judge` 等の `JudgeEntry` 系 metric を使うときだけ束ねる `RubricJudge`（省略時 None）。
    exact_match だけの goal では使われない＝差分ゼロ（ゲートは metric 名の entry 型でしか分岐しない）。
    """

    goal: Goal
    judge: RubricJudge | None = None

    def _scorer(self, name: str) -> Callable[[str, str], float]:
        """metric 名から採点関数を引く。純関数系は `entry.fn`・`JudgeEntry` 系は束ねた `self.judge`。"""
        entry = AGENT_METRICS.resolve(name)  # 未知名は候補一覧つき ValueError（既存挙動）
        if not isinstance(entry, JudgeEntry):
            return entry.fn
        if self.judge is None:
            raise ValueError(f"採点器 '{name}' には judge の束ねが要る（goal YAML の judge: 節）")
        return self.judge

    def check(self, *, output: str, iteration: int) -> StopDecision:
        del iteration  # 骨組みでは未使用（来歴の記録は呼び手＝run_agent_to_goal 側が gate_reasons に残す）
        scores = {name: self._scorer(name)(self.goal.expected, output) for name in self.goal.metrics}
        if passes(scores, dict(self.goal.thresholds)):
            return StopDecision(stop=True, reason="goal_met")
        detail = "  ".join(f"{name}={scores[name]:.3f}" for name in self.goal.metrics)
        return StopDecision(stop=False, reason=f"goal_not_met: {detail}")


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
    gate: StopCondition,
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


# --- goal の宣言化（YAML）。spec_from_mapping と同型の検証（extra forbid・未知キー失敗・T-0096） ---

_GOAL_FIELDS = {"expected", "metrics", "thresholds", "judge"}
_JUDGE_DECL_FIELDS = {"provider", "model", "effort", "path"}


@dataclass(frozen=True, kw_only=True)
class JudgeDecl:
    """goal.yaml の `judge:` 節（provider の束ねの宣言）。`gate_from_goal` がここから `RubricJudge` を組む。

    `path` は provider が `cassette` のときだけ書ける（他 provider に書くと `goal_from_mapping` が失敗にする）。
    """

    provider: str
    model: str
    effort: str = "medium"
    path: str | None = None


def goal_from_mapping(raw: Mapping[str, Any], *, source: str = "<mapping>") -> tuple[Goal, JudgeDecl | None]:
    """goal 宣言（キー→値の写像）を `Goal`（＋judge 節があれば `JudgeDecl`）に読み込む。

    - 未知キーは失敗（extra forbid）。goal 側に書けるのは `{expected, metrics, thresholds, judge}`・
      judge 節は `{provider, model, effort, path}`（`spec_from_mapping` と同型）。
    - `metrics` の各名は `AGENT_METRICS.resolve` で早期解決（未知名は候補一覧つき ValueError）。
    - judge 系 metric（`JudgeEntry`）を含む ⇔ `judge:` 節がある（片方だけは ValueError）。judge 系と
      純関数系（exact_match 等）の併用も ValueError（`expected` の意味が二重になるため）。
    - `path` は `judge.provider == "cassette"` のときだけ許す（他 provider に書くと ValueError）。
    """
    if not isinstance(raw, Mapping):
        raise ValueError(f"{source}: goal はキー→値の辞書であること（実際: {type(raw).__name__}）")
    data = dict(raw)
    unknown = sorted(set(data) - _GOAL_FIELDS)
    if unknown:
        raise ValueError(f"{source}: 未知のキー {unknown}（goal に書けるのは {sorted(_GOAL_FIELDS)}）")
    if "expected" not in data:
        raise ValueError(f"{source}: goal に expected が無い（必須）")
    expected = str(data["expected"])
    metrics = tuple(str(m) for m in data.get("metrics", ("exact_match",)))
    thresholds = {str(k): float(v) for k, v in dict(data.get("thresholds", {})).items()}

    entries = {name: AGENT_METRICS.resolve(name) for name in metrics}  # 未知名は候補一覧つき ValueError
    judge_names = [name for name in metrics if isinstance(entries[name], JudgeEntry)]
    plain_names = [name for name in metrics if name not in judge_names]

    judge_raw = data.get("judge")
    if judge_names and judge_raw is None:
        raise ValueError(f"{source}: metrics に judge 系（{judge_names}）があるのに judge: 節が無い")
    if judge_raw is not None and not judge_names:
        raise ValueError(f"{source}: judge: 節があるのに metrics に judge 系の採点器が無い")
    if judge_names and plain_names:
        raise ValueError(
            f"{source}: judge 系（{judge_names}）と純関数系（{plain_names}）の併用はできない"
            "（expected の意味が二重になる）"
        )

    judge_decl: JudgeDecl | None = None
    if judge_raw is not None:
        if not isinstance(judge_raw, Mapping):
            raise ValueError(f"{source}: judge はキー→値の辞書であること（実際: {type(judge_raw).__name__}）")
        judge_data = dict(judge_raw)
        judge_unknown = sorted(set(judge_data) - _JUDGE_DECL_FIELDS)
        if judge_unknown:
            raise ValueError(f"{source}: judge の未知のキー {judge_unknown}（書けるのは {sorted(_JUDGE_DECL_FIELDS)}）")
        missing = sorted(key for key in ("provider", "model") if key not in judge_data)
        if missing:
            raise ValueError(f"{source}: judge に {missing} が無い（必須）")
        path = judge_data.get("path")
        provider_name = str(judge_data["provider"])
        if path is not None and provider_name != "cassette":
            raise ValueError(f"{source}: judge.path は provider=cassette のときだけ書ける（実際: {provider_name!r}）")
        judge_decl = JudgeDecl(
            provider=provider_name,
            model=str(judge_data["model"]),
            effort=str(judge_data.get("effort", "medium")),
            path=str(path) if path is not None else None,
        )

    return Goal(expected=expected, metrics=metrics, thresholds=thresholds), judge_decl


def load_goal(path: Path) -> tuple[Goal, JudgeDecl | None]:
    """goal 宣言 YAML を読み込む（検証は `goal_from_mapping` に委譲・`load_agent_spec` と同型）。"""
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return goal_from_mapping(raw, source=str(path))


def gate_from_goal(goal: Goal, judge_decl: JudgeDecl | None, *, seed: int) -> GoalGate:
    """`Goal`（＋`JudgeDecl`）から `GoalGate` を組む＝provider を束ねる唯一の場所（goal.yaml の読み込み点）。

    `judge_decl` が None なら `judge=None` の `GoalGate`（exact_match 等の純関数系のみ・従来どおり）。
    """
    if judge_decl is None:
        return GoalGate(goal=goal)
    factory_kwargs: dict[str, Any] = {"path": judge_decl.path} if judge_decl.provider == "cassette" else {}
    provider = PROVIDERS.resolve(judge_decl.provider).factory(seed, **factory_kwargs)
    judge_spec = spec_from_mapping(
        {
            "name": "judge",
            "provider": judge_decl.provider,
            "model": judge_decl.model,
            "system_prompt": JUDGE_SYSTEM_PROMPT,
            "effort": judge_decl.effort,
        },
        source="<judge>",
    )
    judge = make_rubric_judge(provider=provider, spec=judge_spec)
    return GoalGate(goal=goal, judge=judge)
