"""昇格の保存機構（中核）。champion の解決・判定の実行・記録の読み書きを 1 本化する。

同じ仕組みが `harness.ds.models`（学習済みモデル）と `harness.agent.store`（AgentSpec）に構造同一で
複製されていたので、`storage.py` と同じ方針でここへ集めた：**仕組みだけを持ち、方針は呼び手が持つ**
（policy-free）。

- 仕組み＝記録の置き場（`promotions/<decided>.yaml`）・記録の読み書き・champion の解決・判定の実行。
- 方針＝どのレジストリで指標の向きを解決するか（ds は `METRICS`・agent は `AGENT_METRICS`）、primary の
  選び方、閾値、`decided`（版タイムスタンプ）の刻み。これらは呼び手が解決してから渡す。

中核なので `stdlib` ＋ `harness.storage` ＋ `harness.gates` だけに依存する（`harness.ds` / `harness.agent`
のレジストリは import しない）。これで agent は ds を import しないまま複製を捨てられる（プロファイル境界は
壊れず、むしろ強くなる）。

`champion()` の `sorted(glob)[-1]` の欠陥（時刻名でない yaml が混じると壊れる）は本タスクでは**そのまま
移送する**（欠陥を直すのと構造を変えるのを同じコミットに混ぜない。alias 化と異物拒否は T-0174）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from harness import gates, storage

MANIFEST_FILE = "manifest.yaml"
PROMOTIONS_DIR = "promotions"
VERSION_FORMAT = "%Y%m%dT%H%M%S%fZ"  # 辞書順＝時刻順（最新＝降順1件）


@dataclass(frozen=True)
class Promotion:
    """昇格記録 1 件（promotions/<decided>.yaml と同内容）。ds/agent 共通の型。"""

    work: str
    name: str
    version: str
    decided: str
    primary: str
    higher_is_better: bool
    metrics: dict[str, float]
    previous_version: str | None


def champion_version(entity_dir: Path, *, label: str) -> str | None:
    """昇格記録が指す現 champion の版（文字列）。昇格が無ければ None。指す版の実体が無ければ ValueError。

    `label` は例外メッセージに出す識別子（呼び手が `f"{work}/{name}"` などを渡す）。
    走査は `sorted(promotions/*.yaml)[-1]`（既知の欠陥をそのまま移送。alias 化は T-0174）。
    """
    promo_dir = entity_dir / PROMOTIONS_DIR
    if not promo_dir.is_dir():
        return None
    files = sorted(promo_dir.glob("*.yaml"))
    if not files:
        return None
    latest = storage.read_manifest(files[-1])
    version = str(latest["version"])
    if not (entity_dir / version / MANIFEST_FILE).is_file():
        raise ValueError(f"{label}: 昇格記録が指す版 {version} の実体が無い")
    return version


def _version_metrics(entity_dir: Path, version: str) -> dict[str, float]:
    """版の manifest から metrics を読む（champion の baseline に使う。存在は呼び手が保証済み）。"""
    return dict(storage.read_manifest(entity_dir / version / MANIFEST_FILE).get("metrics", {}))


def promote(
    entity_dir: Path,
    *,
    work: str,
    name: str,
    version: str,
    label: str,
    candidate_metrics: Mapping[str, float],
    thresholds: Mapping[str, float],
    primary: str,
    direction: bool,
    directions: Mapping[str, bool],
    decided: str,
) -> Promotion:
    """`value_threshold`（閾値）と `change_threshold`（現 champion からの改善）をすべて満たすときだけ昇格する。

    向きの解決（`direction`・`directions`）・candidate の metrics・`decided` の刻みは呼び手が済ませて渡す
    （方針は呼び手）。ここが持つのは champion の解決・判定の実行・記録の書き込み（仕組み）。
    判定に落ちたら `gates.PromotionError`（`ValueError` の下位型）を投げる。
    """
    previous = champion_version(entity_dir, label=label)
    baseline = _version_metrics(entity_dir, previous) if previous is not None else None
    context = gates.GateContext(
        candidate=candidate_metrics,
        baseline=baseline,
        directions=directions,
        baseline_label=previous,
    )
    specs = [
        *gates.value_threshold_specs(thresholds),
        {"kind": "change_threshold", "metric": primary, "baseline": "champion"},
    ]
    decision = gates.evaluate(context, specs)
    if not decision.approved:
        raise gates.PromotionError(f"{label}/{version} は昇格を却下（rejected）: {decision.summary}", decision)

    record = {
        "work": work,
        "name": name,
        "version": version,
        "decided": decided,
        "primary": primary,
        "higher_is_better": direction,  # レジストリで解決した向きを記録する（呼び手の引数ではない）
        "metrics": dict(candidate_metrics),
        "previous_version": previous,
    }
    promo_dir = entity_dir / PROMOTIONS_DIR
    promo_dir.mkdir(parents=True, exist_ok=True)
    storage.write_manifest(promo_dir / f"{decided}.yaml", record)
    return Promotion(
        work=work,
        name=name,
        version=version,
        decided=decided,
        primary=primary,
        higher_is_better=direction,
        metrics=dict(candidate_metrics),
        previous_version=previous,
    )
