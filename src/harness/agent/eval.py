"""採点器（AGENT_METRICS）と合否ゲート。骨組みは exact_match のみ（rubric/LLM-judge は後続タスク）。

- 採点器は ds の指標と同じ形（Registry[MetricEntry]・description は docstring 1 行目＝DEC-0009）。
  thresholds に書ける名前＝このレジストリの kind（一覧は `uv run agent metrics`）。
- `passes` は `harness.ds.eval.passes` と同じ規約（合格条件を正の形で問う＝NaN は不合格・fail closed・L-009）。
  ds 版は名前を ds の METRICS で検証するため exact_match 等を渡せない＝向きの解決だけ AGENT_METRICS に
  差し替えた小さな複製。3 箇所目が出たら core への昇格を DEC 化する（item.md の leaderboard と同じ扱い）。
"""

from __future__ import annotations

from harness.registry import MetricEntry, Registry

AGENT_METRICS: Registry[MetricEntry] = Registry("採点器", catalog="agent metrics")


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
