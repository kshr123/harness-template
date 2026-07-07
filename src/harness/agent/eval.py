"""採点器（AGENT_METRICS）と合否ゲート。exact_match（純関数）と llm_judge（provider 束ね・T-0096）。

- 採点器は ds の指標と同じ形（Registry[MetricEntry]・description は docstring 1 行目＝DEC-0009）。
  thresholds に書ける名前＝このレジストリの kind（一覧は `uv run agent metrics`）。
- `passes` は `harness.ds.eval.passes` と同じ規約（合格条件を正の形で問う＝NaN は不合格・fail closed・L-009）。
  ds 版は名前を ds の METRICS で検証するため exact_match 等を渡せない＝向きの解決だけ AGENT_METRICS に
  差し替えた小さな複製。3 箇所目が出たら core への昇格を DEC 化する（item.md の leaderboard と同じ扱い）。
- `llm_judge`（`JudgeEntry`）は `MetricEntry.fn` の純関数契約（provider を持たない）を破らない：`.fn` へは
  アクセスさせず、案内つき ValueError で「goal YAML の judge: 節か `GoalGate(judge=…)` 経由で使う」ことを
  教える（登録はカタログ・`passes` の membership・向き解決を既存機構にそのまま乗せるため。実体の束ねは
  `goal.gate_from_goal` の 1 か所＝T-0096）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from harness.agent.judge import make_rubric_judge
from harness.registry import MetricEntry, Registry

AGENT_METRICS: Registry[MetricEntry] = Registry("採点器", catalog="agent metrics")


@dataclass(frozen=True, kw_only=True)
class JudgeEntry(MetricEntry):
    """LLM-judge 採点器の項目。`.fn` は使えない（provider の束ねが要る＝goal YAML の judge: 節経由で使う）。"""

    @property
    def fn(self) -> Callable[..., Any]:
        raise ValueError(
            "llm_judge は provider の束ねが要る＝goal YAML の judge: 節か GoalGate(judge=…) 経由で使う。"
            "run_agent_eval の metrics には書けない・T-0096"
        )


def exact_match(y_true: str, y_pred: str) -> float:
    """完全一致（期待文字列と予測が一致で 1.0・不一致で 0.0）。golden set の決定的な採点の基準線。"""
    return 1.0 if y_true == y_pred else 0.0


AGENT_METRICS.register(
    "exact_match",
    exact_match,
    task="exact",
    entry_cls=MetricEntry,
    input="label",
    higher_is_better=True,
    tasks=("exact",),
)

# 登録の家はここ 1 か所（import 順で一覧が変わらない）。実体（RubricJudge の組み立て）は judge.py・
# 束ね（provider を渡す）は goal.gate_from_goal が行う（T-0096）。
AGENT_METRICS.register(
    "llm_judge",
    make_rubric_judge,
    task="rubric",
    entry_cls=JudgeEntry,
    input="label",
    higher_is_better=True,
    tasks=("rubric",),
)


def passes(metrics: dict[str, float], thresholds: dict[str, float]) -> bool:
    """設定の閾値をすべて満たすときだけ成功（True）。向きは AGENT_METRICS で解決する。

    higher_is_better なら `>=`、そうでなければ `<=`。thresholds に未登録の名があれば ValueError
    （typo を黙って不合格にしない）。metrics 側に無い名・NaN は不合格（fail closed・L-009）。
    """
    for name, limit in thresholds.items():
        if name not in AGENT_METRICS:
            raise ValueError(f"未登録の採点器 '{name}'（thresholds に書けるのは {sorted(AGENT_METRICS)}）")
        if name not in metrics:
            return False
        value = metrics[name]
        # 合格条件を正の形（>= / <=）で問う＝NaN はどの比較も False なので必ず不合格（fail closed）。
        ok = value >= limit if AGENT_METRICS[name].higher_is_better else value <= limit
        if not ok:
            return False
    return True
