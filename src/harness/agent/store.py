"""AgentSpec（宣言）の保存・読み込み・一覧・昇格（LLMOps のライフサイクル中核）。

- ML の `ds/models.py`（champion/promote_model）と同じ形だが、プロファイル境界を守り
  `harness.ds` を import しない独立モジュール（研究 N-8）。再利用は `harness.storage` の一次部品のみ。
- **非対称**：agent の実体は宣言 YAML そのもの＝学習済みバイナリが無いので FORMATS（保存形式の
  拡張ポイント）は要らない（manifest に spec を config として畳み込むの非対称）。
  よって実体ファイルの atomic_write も無く、manifest（write_manifest＝原子的）だけが保存の全体。
- 保存は常に許す（評価の記録）。関門は昇格だけ（絶対＝passes・相対＝現 champion に primary で勝つ）。
- `prompt_fingerprint`（system_prompt の sha256）＝「どのプロンプトで測った metrics か」の印。
"""

from __future__ import annotations

import dataclasses
import hashlib
import platform
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harness import gates, storage
from harness.agent.eval import AGENT_METRICS, passes
from harness.config import load_config

if TYPE_CHECKING:
    from harness.agent.spec import AgentSpec

MANIFEST_FILE = "manifest.yaml"
PROMOTIONS_DIR = "promotions"
VERSION_FORMAT = "%Y%m%dT%H%M%S%fZ"  # 辞書順＝時刻順（最新＝降順1件・ds/models.py と同じ規約）
# 依存版を記録する配布物（入っていないものは飛ばす）。記録のみ・照合は既定でしない。
TRACKED_DISTRIBUTIONS = ("anthropic",)


@dataclass(frozen=True)
class AgentRecord:
    """manifest.yaml 1 件＝保存済みエージェント 1 版。path 以外は manifest の内容そのもの。"""

    name: str
    work: str
    version: str
    spec: dict[str, Any]  # AgentSpec の dict（config＝正本。宣言が実体）
    metrics: dict[str, float]
    prompt_fingerprint: str  # system_prompt の sha256（どのプロンプトで測った metrics かの印）
    created: str
    path: Path
    # 来歴。古い manifest には無いので既定 None＝後方互換。
    git: dict[str, Any] | None = None
    lock_fingerprint: str | None = None


@dataclass(frozen=True)
class AgentPromotion:
    """昇格記録 1 件（promotions/<decided>.yaml と同内容）。ds の Promotion と同形だが agent 独立の型。"""

    work: str
    name: str
    version: str
    decided: str
    primary: str
    higher_is_better: bool
    metrics: dict[str, float]
    previous_version: str | None


def _base(root: Path) -> Path:
    return storage.resolve_uri(root, load_config(root).data.uri_for("models"))


def _agent_dir(root: Path, *, work: str, name: str) -> Path:
    # 保存先は作業単位に同居（work/<work>/agents/<name>/…＝AGENTS「意味のある 1 まとまり」）。
    return _base(root) / "work" / work / "agents" / name


def _utcnow() -> datetime:
    # 時刻はこの 1 関数を経由する（テストが monkeypatch で固定できる。明示性はグローバル種禁止と同じ狙い）。
    return datetime.now(UTC)


def _prompt_fingerprint(system_prompt: str) -> str:
    """system_prompt の sha256 指紋。プロンプトを変えると必ず変わる（metrics の測定条件の印）。"""
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()


def _dependencies() -> dict[str, str]:
    out: dict[str, str] = {}
    for dist in TRACKED_DISTRIBUTIONS:
        try:
            out[dist] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            continue
    return out


def _git_provenance(root: Path) -> dict[str, Any] | None:
    """git 来歴（短縮 commit・branch・作業木の dirty）。git リポでない/git 不在/失敗は None＝保存は止めない。

    読むのは git コマンドの出力だけ（認証情報・.env には触れない）。ds/models.py と同じ作法の複製
    （プロファイル独立を保つための許容コスト＝item.md の gate 複製と同じ扱い）。
    """

    def _run(*args: str) -> str:
        # encoding を明示する：省略するとロケール既定（Windows では cp932）で復号し、
        # 非 ASCII を含む git の出力（ブランチ名等）で UnicodeDecodeError になる。
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True, timeout=5
        )
        return proc.stdout.strip()

    try:
        commit = _run("rev-parse", "--short", "HEAD")
        branch = _run("rev-parse", "--abbrev-ref", "HEAD")
        # --untracked-files=normal を明示：未追跡ファイルも dirty と数える（dirty の意味を環境非依存にする）。
        dirty = bool(_run("status", "--porcelain", "--untracked-files=normal"))
    except OSError, subprocess.SubprocessError, UnicodeDecodeError:
        # CalledProcessError（非 git リポ）・FileNotFoundError（git 不在）・TimeoutExpired を含む。
        # UnicodeDecodeError：git の出力が UTF-8 でない場合（来歴が取れないだけで、保存は続ける）。
        return None
    return {"commit": commit, "branch": branch, "dirty": dirty}


def _lock_fingerprint(root: Path) -> str | None:
    """root 直下の uv.lock の sha256 指紋（どのロックで評価したかの印）。無ければ None。"""
    lock = root / "uv.lock"
    if not lock.is_file():
        return None
    return storage.fingerprint(lock)


def _record_from_manifest(version_dir: Path) -> AgentRecord:
    data = storage.read_manifest(version_dir / MANIFEST_FILE)
    return AgentRecord(
        name=data["name"],
        work=data["work"],
        version=data["version"],
        spec=dict(data.get("spec", {})),
        metrics=dict(data.get("metrics", {})),
        prompt_fingerprint=data["prompt_fingerprint"],
        created=data["created"],
        path=version_dir,
        # 古い manifest にはキーが無い → .get で None 埋め（後方互換・ds と同じ作法）。
        git=data.get("git"),
        lock_fingerprint=data.get("lock_fingerprint"),
    )


def save_agent(root: Path, spec: AgentSpec, *, work: str, name: str, metrics: Mapping[str, float]) -> AgentRecord:
    """評価済み AgentSpec を版として保存する。版ディレクトリが既にあれば拒否（版は再利用しない）。

    実体ファイルは無い（宣言が実体）＝manifest（write_manifest＝原子的）だけを書く。
    manifest 内容＝spec の dict（config）＋metrics＋prompt_fingerprint＋実行環境＋git 来歴＋created。
    保存は常に許す（評価の記録）。関門は promote_agent だけ。
    """
    version = _utcnow().strftime(VERSION_FORMAT)
    version_dir = _agent_dir(root, work=work, name=name) / version
    try:
        version_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(f"同じ版 {version} が既にある（版は再利用しない）") from exc

    spec_dict = dataclasses.asdict(spec)
    spec_dict["tools"] = list(spec_dict.get("tools", ()))  # YAML に書ける形へ（tuple は safe_dump 不可）
    manifest = {
        "name": name,
        "work": work,
        "version": version,
        "spec": spec_dict,
        "metrics": dict(metrics),
        "prompt_fingerprint": _prompt_fingerprint(spec.system_prompt),
        "python": platform.python_version(),
        "dependencies": _dependencies(),
        "created": _utcnow().isoformat(),
        # 来歴：どのコード（git）・どのロック（uv.lock 指紋）で評価したか。取れなければ None（保存は止めない）。
        "git": _git_provenance(root),
        "lock_fingerprint": _lock_fingerprint(root),
    }
    # manifest は最後（かつ唯一）の書き込み＝存在が保存完了の印（write_manifest 自体が tmp→replace で原子的）。
    storage.write_manifest(version_dir / MANIFEST_FILE, manifest)
    return _record_from_manifest(version_dir)


def load_agent(root: Path, *, work: str, name: str, version: str) -> AgentRecord:
    """保存済みエージェントの 1 版を読む。manifest が無ければ FileNotFoundError。"""
    version_dir = _agent_dir(root, work=work, name=name) / version
    if not (version_dir / MANIFEST_FILE).is_file():
        raise FileNotFoundError(f"{work}/{name}/{version}: 保存が無い")
    return _record_from_manifest(version_dir)


def list_agents(root: Path, *, work: str | None = None) -> list[AgentRecord]:
    """保存済みエージェントの一覧（manifest 走査の生成ビュー。台帳ファイルは作らない＝正本を二重化しない）。"""
    base = _base(root) / "work"
    if not base.is_dir():
        return []
    pattern = f"{work}/agents/*/*/{MANIFEST_FILE}" if work else f"*/agents/*/*/{MANIFEST_FILE}"
    records = [_record_from_manifest(m.parent) for m in base.glob(pattern)]
    return sorted(records, key=lambda r: (r.work, r.name, r.version))


def champion(root: Path, *, work: str, name: str) -> AgentRecord | None:
    """昇格記録が指す現 champion の版（生成ビュー）。昇格が無ければ None。"""
    promo_dir = _agent_dir(root, work=work, name=name) / PROMOTIONS_DIR
    if not promo_dir.is_dir():
        return None
    files = sorted(promo_dir.glob("*.yaml"))
    if not files:
        return None
    latest = storage.read_manifest(files[-1])
    version_dir = _agent_dir(root, work=work, name=name) / latest["version"]
    if not (version_dir / MANIFEST_FILE).is_file():
        raise ValueError(f"{work}/{name}: 昇格記録が指す版 {latest['version']} の実体が無い")
    return _record_from_manifest(version_dir)


def promote_agent(
    root: Path,
    *,
    work: str,
    name: str,
    version: str,
    thresholds: Mapping[str, float],
    primary: str,
) -> AgentPromotion:
    """昇格の関門。絶対（passes）かつ相対（現 champion に primary で勝つ）を満たすときだけ昇格する。

    primary の向き（大きいほど良いか）の正本は AGENT_METRICS＝引数では受けない（呼び手の向きの
    思い違いで劣る版が昇格する事故を構造的に塞ぐ）。負け/同点は昇格しない。関門で落ちたら ValueError
    （昇格は明示ゲート＝ここは exit を止める。監視の「門番にしない」とは別の関心）。
    """
    if primary not in AGENT_METRICS:
        raise ValueError(f"未登録の primary 指標 '{primary}'（{sorted(AGENT_METRICS)} のいずれか）")
    direction = AGENT_METRICS[primary].higher_is_better  # 向きの正本はレジストリ
    record = load_agent(root, work=work, name=name, version=version)  # 保存が無ければ FileNotFoundError

    if not passes(record.metrics, dict(thresholds)):
        raise ValueError(f"絶対関門で不合格: metrics={record.metrics} thresholds={dict(thresholds)}")
    if primary not in record.metrics:
        raise ValueError(f"primary 指標 '{primary}' が metrics に無い")

    champ = champion(root, work=work, name=name)
    previous = None
    if champ is not None:
        previous = champ.version
        if primary not in champ.metrics:
            # 過去の昇格と違う primary に切り替えた場合。測っていない指標では比較できない＝昇格しない
            # （passes の「測っていない＝満たしたと見なさない」と同じ規約。KeyError で落ちない）。
            raise ValueError(f"primary 指標 '{primary}' が現 champion（{champ.version}）の metrics に無い")
        # 比較の意味（向きで正規化した改善量が min_change を超えるか・NaN は fail closed）は中核の gates が持つ。
        context = gates.GateContext(
            candidate=record.metrics,
            baseline=champ.metrics,
            directions={primary: direction},
            baseline_label=champ.version,
        )
        decision = gates.evaluate(context, [{"kind": "change_threshold", "metric": primary, "baseline": "champion"}])
        if not decision.approved:
            raise ValueError(
                f"相対関門で不合格: {primary} 候補={record.metrics[primary]} 現 champion={champ.metrics[primary]}"
            )

    decided = _utcnow().strftime(VERSION_FORMAT)
    promotion = {
        "work": work,
        "name": name,
        "version": version,
        "decided": decided,
        "primary": primary,
        "higher_is_better": direction,  # レジストリで解決した向きを記録する（呼び手の引数ではない）
        "metrics": dict(record.metrics),
        "previous_version": previous,
    }
    promo_dir = _agent_dir(root, work=work, name=name) / PROMOTIONS_DIR
    promo_dir.mkdir(parents=True, exist_ok=True)
    storage.write_manifest(promo_dir / f"{decided}.yaml", promotion)
    return AgentPromotion(
        work=work,
        name=name,
        version=version,
        decided=decided,
        primary=primary,
        higher_is_better=direction,
        metrics=dict(record.metrics),
        previous_version=previous,
    )
