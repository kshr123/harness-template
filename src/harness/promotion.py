"""昇格と復旧の保存機構（中核）。champion の解決・判定の実行・記録の読み書き・切り戻しを 1 本化する。

同じ仕組みが `harness.ds.models`（学習済みモデル）と `harness.agent.store`（AgentSpec）に構造同一で
複製されていたので、`storage.py` と同じ方針でここへ集めた：**仕組みだけを持ち、方針は呼び手が持つ**
（policy-free）。

- 仕組み＝記録の置き場（`promotions/<decided>.yaml`）・記録の読み書き・champion の解決・判定の実行・切り戻し。
- 方針＝どのレジストリで指標の向きを解決するか（ds は `METRICS`・agent は `AGENT_METRICS`）、primary の
  選び方、閾値、`decided`（版タイムスタンプ）の刻み。これらは呼び手が解決してから渡す。

中核なので `stdlib` ＋ `harness.storage` ＋ `harness.gates` だけに依存する（`harness.ds` / `harness.agent`
のレジストリは import しない）。これで agent は ds を import しないまま複製を捨てられる（プロファイル境界は
壊れず、むしろ強くなる）。

## 記録の種類（`kind`）と状態（`status`）
- `kind`：`promote`（昇格の候補）／`rollback`（切り戻し）。語の出典は Amazon SageMaker Model Registry。
- `status`：`approved`（承認）／`rejected`（却下）。出典は SageMaker の `ModelApprovalStatus`。
- champion は **`approved` の記録のうち最新**が指す版（`rejected` は監査のため残すが champion を動かさない）。
- 切り戻し（`rollback`）は昇格ではないので判定（`change_threshold`）を通さない。劣る旧良版へ戻せることは
  機能であって欠陥ではない。切り戻し先は `rollback_to`（記録ファイル名）の連鎖を 1 段ずつ辿る（スタックの pop）。

champion の走査は `promotions/` の中で**版の刻み（`VERSION_FORMAT`）に一致するファイル名だけ**を見る
（`_promotion_files`）。一致しない yaml が 1 枚でも居たら `ValueError`（無視でなく失敗＝fail closed）。
これで「劣る版を指す手書き yaml を 1 枚置くだけで champion を奪う」経路を塞ぐ（時刻名は数字で始まり、英字で
始まる名前は ASCII で後ろに並ぶので、従来は `sorted(glob)[-1]` が異物に乗っ取られた）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from harness import gates, storage

MANIFEST_FILE = "manifest.yaml"
PROMOTIONS_DIR = "promotions"
VERSION_FORMAT = "%Y%m%dT%H%M%S%fZ"  # 辞書順＝時刻順（最新＝降順1件）

# 記録の種類（kind）と状態（status）。語の出典は Amazon SageMaker Model Registry の ModelApprovalStatus。
KIND_PROMOTE = "promote"
KIND_ROLLBACK = "rollback"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


@dataclass(frozen=True)
class Promotion:
    """昇格・切り戻しの記録 1 件（promotions/<decided>.yaml と同内容）。ds/agent 共通の型。"""

    work: str
    name: str
    version: str
    decided: str
    primary: str
    higher_is_better: bool
    metrics: dict[str, float]
    previous_version: str | None
    # 復旧の次元（後方から追加。既定は「昇格・承認・戻り先なし・理由なし」）。
    kind: str = KIND_PROMOTE
    status: str = STATUS_APPROVED
    rollback_to: str | None = None  # 切り戻し先の記録ファイル名（null＝戻り先が無い＝初回昇格）
    reason: str | None = None  # 切り戻しの理由（rollback で必須・promote では None）


def _record_path(entity_dir: Path, filename: str) -> Path:
    return entity_dir / PROMOTIONS_DIR / filename


def _promotion_files(entity_dir: Path, *, label: str) -> list[Path]:
    """`promotions/` の記録ファイルを古い順に返す。ファイル名は版の刻み（`VERSION_FORMAT`）に一致しなければ
    ならず、一致しない yaml が 1 つでも居たら `ValueError`（無視でなく失敗＝fail closed）。

    これで `sorted(glob)[-1]` を異物 yaml（例 `notes.yaml`）が乗っ取る経路を塞ぐ：時刻名は数字で始まり、
    英字で始まる名前は ASCII で後ろに並ぶので、従来は劣る版を指す手書き yaml を 1 枚置くだけで champion を
    奪えた。champion は「異物を無視して最新の approved」ではなく「異物があれば止まる」にする（黙って劣る版を
    配るより、うるさく止まる方がよい）。
    """
    promo_dir = entity_dir / PROMOTIONS_DIR
    if not promo_dir.is_dir():
        return []
    files = sorted(promo_dir.glob("*.yaml"))
    for p in files:
        try:
            datetime.strptime(p.stem, VERSION_FORMAT)
        except ValueError:
            raise ValueError(
                f"{label}: promotions/ に版の刻み（{VERSION_FORMAT}）でない yaml がある: {p.name}"
            ) from None
    return files


def _approved_records(entity_dir: Path, *, label: str) -> list[tuple[str, dict[str, object]]]:
    """`approved` の記録を（ファイル名, 記録）で古い順に返す。`rejected` は champion に効かないので除く。

    走査は `_promotion_files`（版の刻みでない yaml は `ValueError`）。`status` の無い古い記録は `approved` と
    みなす（後方互換）。
    """
    out: list[tuple[str, dict[str, object]]] = []
    for p in _promotion_files(entity_dir, label=label):
        rec = storage.read_manifest(p)
        if rec.get("status", STATUS_APPROVED) == STATUS_APPROVED:
            out.append((p.name, rec))
    return out


def champion_record(entity_dir: Path, *, label: str) -> tuple[str, dict[str, object]] | None:
    """現 champion を作った記録（ファイル名, 記録）。approved の最新。無ければ None。実体が無ければ ValueError。

    `label` は例外メッセージに出す識別子（呼び手が `f"{work}/{name}"` などを渡す）。
    """
    records = _approved_records(entity_dir, label=label)
    if not records:
        return None
    filename, rec = records[-1]
    version = str(rec["version"])
    if not (entity_dir / version / MANIFEST_FILE).is_file():
        raise ValueError(f"{label}: 昇格記録が指す版 {version} の実体が無い")
    return filename, rec


def champion_version(entity_dir: Path, *, label: str) -> str | None:
    """昇格記録が指す現 champion の版（文字列）。昇格が無ければ None。指す版の実体が無ければ ValueError。"""
    cr = champion_record(entity_dir, label=label)
    return str(cr[1]["version"]) if cr is not None else None


def history(entity_dir: Path, *, label: str) -> list[dict[str, object]]:
    """`promotions/` の記録を古い順にすべて返す（昇格も却下も切り戻しも。監査・履歴表示用）。

    走査は `_promotion_files`（版の刻みでない yaml は `ValueError`）。履歴表示でも異物 yaml があれば黙って
    混ぜず止める（champion の解決と同じ規則を共有する）。
    """
    return [storage.read_manifest(p) for p in _promotion_files(entity_dir, label=label)]


def _version_metrics(entity_dir: Path, version: str) -> dict[str, float]:
    """版の manifest から metrics を読む（baseline・切り戻し記録に使う。存在は呼び手が保証済み）。"""
    return dict(storage.read_manifest(entity_dir / version / MANIFEST_FILE).get("metrics", {}))


def _write_record(entity_dir: Path, decided: str, record: Mapping[str, object]) -> None:
    promo_dir = entity_dir / PROMOTIONS_DIR
    promo_dir.mkdir(parents=True, exist_ok=True)
    storage.write_manifest(promo_dir / f"{decided}.yaml", dict(record))


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

    却下されても**記録は残す**（`status: rejected`。何を却下したかは監査で最も知りたい情報のひとつ）。
    champion は approved の記録だけを見るので、却下記録は champion を動かさない。最後に
    `gates.PromotionError`（`ValueError` の下位型）を投げる。
    """
    cr = champion_record(entity_dir, label=label)
    previous = str(cr[1]["version"]) if cr is not None else None
    champ_record_file = cr[0] if cr is not None else None  # この昇格から切り戻すときの戻り先（現 champion の記録）
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
    approved = decision.approved
    # 却下記録の戻り先（rollback_to）は None：却下版は champion にならないので、そこへ戻る操作は無い。
    rollback_to = champ_record_file if approved else None
    record = {
        "work": work,
        "name": name,
        "version": version,
        "decided": decided,
        "primary": primary,
        "higher_is_better": direction,  # レジストリで解決した向きを記録する（呼び手の引数ではない）
        "metrics": dict(candidate_metrics),
        "previous_version": previous,
        "kind": KIND_PROMOTE,
        "status": STATUS_APPROVED if approved else STATUS_REJECTED,
        "rollback_to": rollback_to,
        "reason": None,
    }
    _write_record(entity_dir, decided, record)
    if not approved:
        raise gates.PromotionError(f"{label}/{version} は昇格を却下（rejected）: {decision.summary}", decision)
    return Promotion(
        work=work,
        name=name,
        version=version,
        decided=decided,
        primary=primary,
        higher_is_better=direction,
        metrics=dict(candidate_metrics),
        previous_version=previous,
        kind=KIND_PROMOTE,
        status=STATUS_APPROVED,
        rollback_to=rollback_to,
        reason=None,
    )


def rollback(entity_dir: Path, *, work: str, name: str, label: str, reason: str, decided: str) -> Promotion:
    """現 champion を、前の champion（`rollback_to` の連鎖の 1 段前）へ戻す。**判定は通さない**。

    切り戻しは昇格ではない（劣る旧良版へ戻せることは機能であって欠陥ではない）ので `change_threshold` を
    課さない。戻り先は現 champion 記録の `rollback_to`（記録ファイル名）で、新しい切り戻し記録はその戻り先の
    `rollback_to` を引き継ぐ（もう 1 段戻せる＝スタックの pop）。`reason` は必須（なぜ戻すかを記録に残す）。

    戻り先が無い（初回昇格の champion）・戻り先の記録や版の実体が無いときは ValueError（黙って壊れた
    champion を指さない）。
    """
    if not reason or not reason.strip():
        raise ValueError("rollback には reason（なぜ戻すか）が必須")
    cr = champion_record(entity_dir, label=label)
    if cr is None:
        raise ValueError(f"{label}: champion が無いので切り戻せない")
    _, champ_rec = cr
    target_file = champ_rec.get("rollback_to")
    if target_file is None:
        raise ValueError(f"{label}: 戻り先が無い（初回昇格の champion は切り戻せない）")
    target_path = _record_path(entity_dir, str(target_file))
    if not target_path.is_file():
        raise ValueError(f"{label}: 切り戻し先の記録 {target_file} が無い")
    target = storage.read_manifest(target_path)
    target_version = str(target["version"])
    if not (entity_dir / target_version / MANIFEST_FILE).is_file():
        raise ValueError(f"{label}: 切り戻し先の版 {target_version} の実体が無い")

    previous = str(champ_rec["version"])  # いま離れる champion
    metrics = _version_metrics(entity_dir, target_version)
    direction = bool(target.get("higher_is_better", True))
    primary = str(target.get("primary", ""))
    inherited_rollback_to = target.get("rollback_to")
    record = {
        "work": work,
        "name": name,
        "version": target_version,
        "decided": decided,
        "primary": primary,
        "higher_is_better": direction,
        "metrics": dict(metrics),
        "previous_version": previous,
        "kind": KIND_ROLLBACK,
        "status": STATUS_APPROVED,
        "rollback_to": inherited_rollback_to,  # 戻り先の記録の rollback_to を引き継ぐ（スタックを pop）
        "reason": reason,
    }
    _write_record(entity_dir, decided, record)
    return Promotion(
        work=work,
        name=name,
        version=target_version,
        decided=decided,
        primary=primary,
        higher_is_better=direction,
        metrics=dict(metrics),
        previous_version=previous,
        kind=KIND_ROLLBACK,
        status=STATUS_APPROVED,
        rollback_to=inherited_rollback_to if inherited_rollback_to is None else str(inherited_rollback_to),
        reason=reason,
    )
