"""昇格の判定（gates）。champion を差し替えてよいかを、宣言した判定条件の並びで決める。

同じ判定が `harness.ds.models.promote_model` と `harness.agent.store.promote_agent` に重複していたので、
判定の意味だけをここへ集めた。プロファイルは「どの指標を・どの向きで見るか」を自分のレジストリ
（`ds.eval.METRICS` / `agent.eval.AGENT_METRICS`）で解決してから、解決済みの向きとともにここへ渡す
（中核はプロファイルのレジストリを import しない）。

判定の種類は `GATES` レジストリで開いている。config は `kind` の文字列で選ぶ：

    [{"kind": "value_threshold", "metric": "roc_auc", "limit": 0.80},
     {"kind": "change_threshold", "metric": "roc_auc", "baseline": "champion"}]

判定の名前の出典は `GATES.register(..., source=…)` が正本（`uv run gates` で見える）。このレジストリは
`require_source=True` なので、出典の無い名前は登録できない＝造語を作れない。

判定はすべて **fail closed**。合格条件を正の形で問い、そこに「観測値が有限である」（`math.isfinite`）を
含める。比較だけでは足りない：`NaN >= 0.8` は False で止まるが `inf >= 0.8` は True で通り、
比較対象の無い初回昇格では比較そのものが行われない。有限性を条件に入れて初めて、発散した版が
champion に上がらないと言える。測っていない指標も不合格（`passes` の「測っていない＝満たしたと
見なさない」と同じ規約）。

判定は**全件集めてから**合否を出す（`checks.PM_CHECKS` と同じ方式）。最初の 1 件で止めると、直した次の
実行でまた別の条件に落ちる往復が起きる。core の部品（プロファイル非依存）。stdlib と `harness.registry`
だけに依存する。
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
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
    # ok | not_measured | not_finite | threshold_not_met | no_baseline
    # | baseline_not_measured | baseline_not_finite | no_improvement
    # 向きに依らない名にする（小さいほど良い指標が上限を超えて落ちても threshold_not_met）。
    reason: str
    observed: float | None
    baseline: float | None
    detail: str  # 人が読む 1 行（実測値入り）
    # その判定に渡した引数（`kind` を除いた spec そのもの）。判定ごとに引数が違うので単一の欄で兼ねない。
    # 昇格記録へ写して監査に使う欄なので、書き換えられない読み取り専用ビューにする（`__post_init__`）。
    # ハッシュには含めない（compare=False）：dict は unhashable なので、含めると frozen の `__hash__` が
    # `set` 投入で TypeError になる（GateResult を set に入れられなくなる。T-0185）。
    params: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        # frozen なので object.__setattr__ 経由で読み取り専用のビューに差し替える（`params["x"] = …` を封じる）。
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


@dataclass(frozen=True)
class PromotionDecision:
    """判定の総合結果。`approved`（承認）と、その否定＝`rejected`（却下）で表す。

    語の出典：Amazon SageMaker Model Registry の `ModelApprovalStatus`（Approved / Rejected /
    PendingManualApproval）。人手の承認待ちを入れるときは同じ語彙の `pending_manual_approval` を使う。
    """

    approved: bool
    results: tuple[GateResult, ...]

    @property
    def judged(self) -> bool:
        """判定を 1 件でも実際に下したか。`approved` は 0 件のとき `all([])=True`（合格に見える）ので、
        「判定していない」を「合格」と区別したい呼び手はこれを見る（EP-32 T-0199）。promote 経路は必ず
        `change_threshold` を含むので常に judged=True。空になりうるのは探索の `passes(x, {})` の側。
        """
        return len(self.results) > 0

    @property
    def first_promotion(self) -> bool:
        """初回昇格（比較対象の champion が無い）で、改善量の判定を課さない緩和が実際に効いたか。監査で
        名指しできるようにする（緩和を暗黙にしない＝EP-32 T-0199）。`change_threshold` が `no_baseline` を
        返したことから導く（別のフラグを二重に持たない）。

        注意：`no_baseline` は候補の未測定・非有限（not_measured / not_finite）の検査を通った後に返る。
        つまり初回でも primary が欠けている・発散している場合は not_measured/not_finite で却下され、
        この property は False になる。承認された昇格では正しく、却下された初回の監査ラベルとしてだけ甘い。
        """
        return any(r.reason == "no_baseline" for r in self.results)

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
    params = {"limit": limit}
    if metric not in ctx.candidate:
        detail = f"value_threshold: {metric} を測っていない（{comparison} {limit} を確かめられない）"
        return GateResult("value_threshold", metric, False, "not_measured", None, None, detail, params)
    observed = ctx.candidate[metric]
    if not math.isfinite(observed):  # NaN も ±inf も発散。inf >= limit は True なので比較では止まらない。
        detail = f"value_threshold: {metric}={observed} が有限でない（発散した版は昇格させない）"
        return GateResult("value_threshold", metric, False, "not_finite", observed, None, detail, params)
    passed = observed >= limit if direction else observed <= limit
    verdict = "を満たす" if passed else "を満たさない"
    detail = f"value_threshold: {metric}={observed} は {comparison} {limit} {verdict}"
    reason = "ok" if passed else "threshold_not_met"
    return GateResult("value_threshold", metric, passed, reason, observed, None, detail, params)


def change_threshold(ctx: GateContext, *, metric: str, baseline: str, min_change: float = 0.0) -> GateResult:
    """baseline（現 champion）からの改善量が min_change を超えるか（既定 0.0＝厳密に良い・同点は不合格）。

    改善量は向きで正規化する（大きいほど良いなら候補−baseline、そうでなければ baseline−候補）。だから
    min_change の符号は指標の向きに依存しない：`log_loss` でも `min_change=0.01` は「0.01 以上下がること」。

    比較対象が無い初回昇格ではこの判定を課さないが、それは「何でも通す」ことではない。閾値が 1 つも
    宣言されていない設定では、ここが発散した版を止める最後の場所になる（有限性だけは初回でも問う）。

    baseline は比較対象の名前で、今は `"champion"` だけ。この語の出典は MLflow Model Registry の alias
    （2.9 で Model Stages を非推奨にした後の推奨）。何と比べるかを名前で一意にするため、既定値を持たない。
    """
    if baseline != "champion":
        raise ValueError(f"change_threshold の baseline は 'champion' だけ（'{baseline}' は未対応）")
    direction = ctx.direction(metric)
    label = f"champion({ctx.baseline_label})" if ctx.baseline_label else "champion"
    params = {"baseline": baseline, "min_change": min_change}
    # 候補の未測定は baseline の有無より先に見る（初回昇格でも、測っていない指標では昇格を認めない）。
    if metric not in ctx.candidate:
        detail = f"change_threshold: 候補が {metric} を測っていないので比較できない"
        return GateResult("change_threshold", metric, False, "not_measured", None, None, detail, params)
    observed = ctx.candidate[metric]
    if not math.isfinite(observed):
        detail = f"change_threshold: 候補の {metric}={observed} が有限でない（発散した版は昇格させない）"
        return GateResult("change_threshold", metric, False, "not_finite", observed, None, detail, params)
    if ctx.baseline is None:  # 初回昇格＝比較対象が無いので、改善量は問えない（有限性は上で確かめた）
        detail = "change_threshold: baseline が無い（初回昇格なので比較しない）"
        return GateResult("change_threshold", metric, True, "no_baseline", observed, None, detail, params)
    if metric not in ctx.baseline:
        detail = f"change_threshold: {label} が {metric} を測っていないので比較できない"
        return GateResult("change_threshold", metric, False, "baseline_not_measured", observed, None, detail, params)
    before = ctx.baseline[metric]
    if not math.isfinite(before):
        # champion 側が壊れている。候補は悪くないので reason で区別する（切り戻しが要る状態）。
        detail = f"change_threshold: {label} の {metric}={before} が有限でない（champion の切り戻しが要る）"
        return GateResult("change_threshold", metric, False, "baseline_not_finite", observed, before, detail, params)
    improvement = observed - before if direction else before - observed
    passed = improvement > min_change  # 同点（改善量 0.0）は不合格＝厳密な改善だけを認める。
    verdict = "を満たす" if passed else "を満たさない"
    # 改善量は引き算の結果なので浮動小数点の桁が出る（0.6-0.9=-0.30000000000000004）。読む人には無意味なので丸める。
    detail = (
        f"change_threshold: {metric} 候補={observed} {label}={before} "
        f"改善量={improvement:+.6g} は > {min_change} {verdict}"
    )
    reason = "ok" if passed else "no_improvement"
    return GateResult("change_threshold", metric, passed, reason, observed, before, detail, params)


def _require_gate_context_first(kind: str, factory: Callable[..., Any]) -> None:
    """判定の第 1 引数が `GateContext` を位置で受ける契約を、登録時に確かめる（T-0185・fail closed）。

    `_run` は `factory(ctx, **params)` を位置引数で束ねるので、`def sneaky(metric, *, limit)` のように
    第 1 引数が別物だと `ctx` が `metric` に黙って束縛され、エラーを出さず走ってしまう。実行時に黙って壊れる
    より、登録時に `ValueError` で止める方が発生源に近い。
    """
    params = list(inspect.signature(factory).parameters.values())
    if not params:
        raise ValueError(f"判定 '{kind}' は引数を取らない（第 1 引数に GateContext を位置で受ける契約）")
    first = params[0]
    if first.kind not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
        raise ValueError(
            f"判定 '{kind}' の第 1 引数 '{first.name}' が位置引数でない（GateContext を位置で受ける契約に反する）"
        )
    # from __future__ import annotations のため注釈は文字列。型そのものでも文字列でも受ける。
    if first.annotation not in (GateContext, "GateContext"):
        raise ValueError(
            f"判定 '{kind}' の第 1 引数 '{first.name}' の型注釈が GateContext でない（{first.annotation!r}）"
        )


# 判定の名前は「概念そのものの名前」なので、出典なしに登録できない（require_source）。
# 第 1 引数が GateContext である契約は factory_validator で登録時に強制する（T-0185）。
GATES: Registry[Entry] = Registry(
    "昇格の判定", catalog="gates", require_source=True, factory_validator=_require_gate_context_first
)
GATES.register(
    "value_threshold",
    value_threshold,
    source="TensorFlow Extended の tfma.MetricThreshold（GenericValueThreshold）",
)
GATES.register(
    "change_threshold",
    change_threshold,
    source="TensorFlow Extended の tfma.MetricThreshold（GenericChangeThreshold）",
)


def _run(ctx: GateContext, spec: GateSpec) -> GateResult:
    """spec 1 件を判定に渡す。設定の書き間違いはすべて ValueError にする（呼び手の契約）。

    `factory(ctx, **params)` を直に呼ぶと、引数の typo は TypeError になって `except ValueError` を
    素通りする。判定を config に書けるようにする以上、typo は「設定の誤り」であって「内部の型の誤り」
    ではない。呼ぶ前に署名へ束ねて確かめる。
    """
    if "kind" not in spec:
        raise ValueError(f"判定の spec に 'kind' が無い（{sorted(spec)} だけが書かれている）")
    kind = spec["kind"]
    factory = GATES.resolve(kind).factory
    params = {k: v for k, v in spec.items() if k != "kind"}
    try:
        inspect.signature(factory).bind(ctx, **params)
    except TypeError as exc:  # 未知の引数・必須引数の欠落
        raise ValueError(f"判定 '{kind}' の引数が誤り: {exc}") from exc
    result: GateResult = factory(ctx, **params)
    return result


def evaluate(ctx: GateContext, specs: Sequence[GateSpec]) -> PromotionDecision:
    """判定の並びをすべて評価し、1 つでも落ちたら rejected（全件の結果を返す）。

    `kind` で `GATES` を引き、残りのキーを判定の引数として渡す（未知 kind・未知の引数は ValueError）。
    """
    results = tuple(_run(ctx, spec) for spec in specs)
    return PromotionDecision(approved=all(r.passed for r in results), results=results)


def value_threshold_specs(thresholds: Mapping[str, float]) -> list[GateSpec]:
    """閾値の対応表（指標→値）を value_threshold の並びに直す（既存 API の糖衣）。"""
    return [{"kind": "value_threshold", "metric": name, "limit": limit} for name, limit in thresholds.items()]
