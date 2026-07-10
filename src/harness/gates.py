"""昇格の判定（gates）。champion を差し替えてよいかを、宣言した判定条件の並びで決める。

同じ判定が `harness.ds.models.promote_model` と `harness.agent.store.promote_agent` に重複していたので、
判定の意味だけをここへ集めた。プロファイルは「どの指標を・どの向きで見るか」を自分のレジストリ
（`ds.eval.METRICS` / `agent.eval.AGENT_METRICS`）で解決してから、解決済みの向きとともにここへ渡す
（中核はプロファイルのレジストリを import しない）。

判定の種類は `GATES` レジストリで開いている。config は `kind` の文字列で選ぶ：

    [{"kind": "value_threshold", "metric": "roc_auc", "limit": 0.80},
     {"kind": "change_threshold", "metric": "roc_auc", "baseline": "champion"}]

用語の出所:
- `value_threshold` / `change_threshold` … TensorFlow Extended の `tfma.MetricThreshold`。前者は指標そのものの
  下限（向きが逆なら上限）、後者は baseline との差。
- `approved` / `rejected` … Amazon SageMaker Model Registry の `ModelApprovalStatus`。
- `champion` … MLflow Model Registry の alias（2.9 で Model Stages を非推奨にした後の推奨）。

判定はすべて **fail closed**。「合格条件が成り立つか」を正の形で問うので、NaN はどの比較も False になり
必ず不合格になる（発散したモデルが champion に上がらない）。測っていない指標も不合格（`passes` の
「測っていない＝満たしたと見なさない」と同じ規約）。

判定は**全件集めてから**合否を出す（`checks.PM_CHECKS` と同じ方式）。最初の 1 件で止めると、直した次の
実行でまた別の条件に落ちる往復が起きる。core の部品（プロファイル非依存）。stdlib と `harness.registry`
だけに依存する。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from harness.registry import Entry, Registry

# 判定の並び（config の 1 節）。`kind` で GATES を引き、残りのキーは判定の引数になる。
GateSpec = Mapping[str, Any]


@dataclass(frozen=True)
class GateContext:
    """判定に渡す事実。向き（higher_is_better）の正本は呼び手のレジストリで、ここへは解決済みで届く。"""

    candidate: Mapping[str, float]
    baseline: Mapping[str, float] | None  # 現 champion の metrics（未昇格なら None）
    directions: Mapping[str, bool]  # 指標 → 大きいほど良いか
    baseline_label: str | None = None  # 比較対象の版（メッセージに出す。例 champion の version）

    def direction(self, metric: str) -> bool:
        """指標の向き。未解決の指標は呼び手の思い違いなので止める（黙って不合格にしない）。"""
        if metric not in self.directions:
            raise ValueError(f"指標 '{metric}' の向き（higher_is_better）が解決されていない")
        return self.directions[metric]


@dataclass(frozen=True)
class GateResult:
    """判定 1 件の結果。通過したものも残す（昇格記録に写して監査に使えるようにするため）。"""

    kind: str
    metric: str
    passed: bool
    reason: str  # ok | below_limit | not_measured | baseline_not_measured | no_baseline | no_improvement
    observed: float | None
    baseline: float | None
    limit: float
    detail: str  # 人が読む 1 行（実測値入り）


@dataclass(frozen=True)
class PromotionDecision:
    """判定の総合結果。`approved` / `rejected` は SageMaker の ModelApprovalStatus の語彙。"""

    approved: bool
    results: tuple[GateResult, ...]

    @property
    def failures(self) -> tuple[GateResult, ...]:
        """落ちた判定だけ（全件。最初の 1 件で止めない）。"""
        return tuple(r for r in self.results if not r.passed)

    @property
    def summary(self) -> str:
        """落ちた判定を 1 行ずつ並べた文字列（例外のメッセージに使う）。"""
        return "; ".join(r.detail for r in self.failures)


class PromotionError(ValueError):
    """昇格が却下された（rejected）。落ちた判定を構造として持つので、呼び手は文字列を解析しなくてよい。"""

    def __init__(self, message: str, decision: PromotionDecision) -> None:
        super().__init__(message)
        self.decision = decision


def value_threshold(ctx: GateContext, *, metric: str, limit: float) -> GateResult:
    """指標そのものが閾値を満たすか（向きが大きいほど良いなら下限、そうでなければ上限）。"""
    direction = ctx.direction(metric)
    comparison = ">=" if direction else "<="
    if metric not in ctx.candidate:
        detail = f"value_threshold: {metric} を測っていない（{comparison} {limit} を確かめられない）"
        return GateResult("value_threshold", metric, False, "not_measured", None, None, limit, detail)
    observed = ctx.candidate[metric]
    # 合格条件を正の形で問う＝NaN はどの比較も False になり必ず不合格（fail closed）。
    passed = observed >= limit if direction else observed <= limit
    verdict = "を満たす" if passed else "を満たさない"
    detail = f"value_threshold: {metric}={observed} は {comparison} {limit} {verdict}"
    reason = "ok" if passed else "below_limit"
    return GateResult("value_threshold", metric, passed, reason, observed, None, limit, detail)


def change_threshold(ctx: GateContext, *, metric: str, baseline: str, min_change: float = 0.0) -> GateResult:
    """baseline（現 champion）からの改善量が min_change を超えるか（既定 0.0＝厳密に良い・同点は不合格）。

    改善量は向きで正規化する（大きいほど良いなら候補−baseline、そうでなければ baseline−候補）。だから
    min_change の符号は指標の向きに依存しない：`log_loss` でも `min_change=0.01` は「0.01 以上下がること」。
    """
    if baseline != "champion":
        raise ValueError(f"change_threshold の baseline は 'champion' だけ（'{baseline}' は未対応）")
    direction = ctx.direction(metric)
    label = f"champion({ctx.baseline_label})" if ctx.baseline_label else "champion"
    # 候補の未測定は baseline の有無より先に見る（初回昇格でも、測っていない指標では昇格を認めない）。
    if metric not in ctx.candidate:
        detail = f"change_threshold: 候補が {metric} を測っていないので比較できない"
        return GateResult("change_threshold", metric, False, "not_measured", None, None, min_change, detail)
    if ctx.baseline is None:  # 初回昇格＝比較対象が無いので、この判定は課さない
        detail = "change_threshold: baseline が無い（初回昇格なので比較しない）"
        observed_only = ctx.candidate[metric]
        return GateResult("change_threshold", metric, True, "no_baseline", observed_only, None, min_change, detail)
    if metric not in ctx.baseline:
        detail = f"change_threshold: {label} が {metric} を測っていないので比較できない"
        observed_only = ctx.candidate[metric]
        return GateResult(
            "change_threshold", metric, False, "baseline_not_measured", observed_only, None, min_change, detail
        )
    observed = ctx.candidate[metric]
    before = ctx.baseline[metric]
    improvement = observed - before if direction else before - observed
    passed = improvement > min_change  # NaN はどちらの比較も False＝fail closed。同点（0.0）も不合格。
    verdict = "を満たす" if passed else "を満たさない"
    # 改善量は引き算の結果なので浮動小数点の桁が出る（0.6-0.9=-0.30000000000000004）。読む人には無意味なので丸める。
    detail = (
        f"change_threshold: {metric} 候補={observed} {label}={before} "
        f"改善量={improvement:+.6g} は > {min_change} {verdict}"
    )
    reason = "ok" if passed else "no_improvement"
    return GateResult("change_threshold", metric, passed, reason, observed, before, min_change, detail)


GATES: Registry[Entry] = Registry("昇格の判定", catalog="gates")
GATES.register("value_threshold", value_threshold)
GATES.register("change_threshold", change_threshold)


def evaluate(ctx: GateContext, specs: Sequence[GateSpec]) -> PromotionDecision:
    """判定の並びをすべて評価し、1 つでも落ちたら rejected（全件の結果を返す）。

    `kind` で `GATES` を引き、残りのキーを判定の引数として渡す（未知 kind・未知の引数は ValueError）。
    """
    results = tuple(
        GATES.resolve(spec.get("kind")).factory(ctx, **{k: v for k, v in spec.items() if k != "kind"}) for spec in specs
    )
    return PromotionDecision(approved=all(r.passed for r in results), results=results)


def value_threshold_specs(thresholds: Mapping[str, float]) -> list[GateSpec]:
    """閾値の対応表（指標→値）を value_threshold の並びに直す（既存 API の糖衣）。"""
    return [{"kind": "value_threshold", "metric": name, "limit": limit} for name, limit in thresholds.items()]
