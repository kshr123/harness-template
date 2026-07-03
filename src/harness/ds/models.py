"""学習済みモデル（sklearn Pipeline 丸ごと）の保存・読み込み・一覧・昇格。

- 実体は pickle 1 ファイル（特徴量→モデルの Pipeline を丸ごと。前処理と本体がずれない）。
- store.py と同じ4作法：config URI で置き場を解決／一時ファイル→rename／sha256 指紋／manifest.yaml。
- 保存は常に許す（実験の記録）。関門は昇格だけ（負の結果も記録で完了、と両立する）。
- 形式は manifest の `format` 文字列が担う（load が分岐）。可搬形式（onnx 等）が要る時に枝を足す差し替え口。
- harness/models.py（PM の Item 型）と紛れるので、import は必ず
  `from harness.ds import models as model_store` と別名にする（規約）。この核は sklearn を import しない。
"""

from __future__ import annotations

import hashlib
import pickle
import platform
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

from harness.config import load_config
from harness.ds.eval import passes

MODEL_FILE = "model.pkl"
MANIFEST_FILE = "manifest.yaml"
PROMOTIONS_DIR = "promotions"
VERSION_FORMAT = "%Y%m%dT%H%M%S%fZ"  # 辞書順＝時刻順（最新＝降順1件）
# 依存版を記録する配布物（入っていないものは飛ばす）。記録のみ・照合は既定でしない。
TRACKED_DISTRIBUTIONS = ("scikit-learn", "numpy", "polars", "lightgbm", "statsmodels")


@dataclass(frozen=True)
class ModelRecord:
    """manifest.yaml 1 件＝保存済みモデル 1 版。path 以外は manifest の内容そのもの。"""

    name: str
    work: str
    version: str
    format: str
    fingerprint: str
    data_fingerprint: str | None
    feature_names: tuple[str, ...]
    config: dict[str, Any]
    metrics: dict[str, float]
    python: str
    dependencies: dict[str, str]
    created: str
    path: Path


@dataclass(frozen=True)
class Promotion:
    """昇格記録 1 件（promotions/<decided>.yaml と同内容）。"""

    work: str
    name: str
    version: str
    decided: str
    primary: str
    higher_is_better: bool
    metrics: dict[str, float]
    previous_version: str | None


def _base(root: Path) -> Path:
    uri = load_config(root).data.uri_for("models")
    if not uri.startswith("file:"):
        raise NotImplementedError(f"保存先 '{uri}' は未対応（この段階はローカルのみ）")
    return root / uri[len("file:") :]


def _model_dir(root: Path, *, work: str, name: str) -> Path:
    return _base(root) / "work" / work / "models" / name


def _utcnow() -> datetime:
    # 時刻はこの 1 関数を経由する（テストが monkeypatch で固定できる。明示性はグローバル種禁止と同じ狙い）。
    return datetime.now(UTC)


def _feature_names_of(model: object) -> tuple[str, ...]:
    """Pipeline なら最終段手前（model[:-1]）の get_feature_names_out を試す。取れなければ空。

    ダックタイピングで書く＝models.py は sklearn を import しない（stdlib＋yaml＋config のみを維持）。
    """
    try:
        names = model[:-1].get_feature_names_out()  # type: ignore[index]
    except Exception:
        return ()
    return tuple(str(n) for n in names)


def _dependencies() -> dict[str, str]:
    out: dict[str, str] = {}
    for dist in TRACKED_DISTRIBUTIONS:
        try:
            out[dist] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            continue
    return out


def _record_from_manifest(path: Path) -> ModelRecord:
    data = yaml.safe_load((path / MANIFEST_FILE).read_text(encoding="utf-8"))
    return ModelRecord(
        name=data["name"],
        work=data["work"],
        version=data["version"],
        format=data["format"],
        fingerprint=data["fingerprint"],
        data_fingerprint=data.get("data_fingerprint"),
        feature_names=tuple(data.get("feature_names", [])),
        config=dict(data.get("config", {})),
        metrics=dict(data.get("metrics", {})),
        python=data["python"],
        dependencies=dict(data.get("dependencies", {})),
        created=data["created"],
        path=path,
    )


def save_model(
    root: Path,
    model: object,
    *,
    name: str,
    work: str,
    data_fingerprint: str | None = None,
    config: Mapping[str, Any] | None = None,
    metrics: Mapping[str, float] | None = None,
    feature_names: Sequence[str] | None = None,
) -> ModelRecord:
    """学習済み model（Pipeline）を pickle＋manifest で保存する。版ディレクトリが既にあれば拒否。"""
    version = _utcnow().strftime(VERSION_FORMAT)
    version_dir = _model_dir(root, work=work, name=name) / version
    try:
        version_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(f"同じ版 {version} が既にある（版は再利用しない）") from exc

    names = tuple(feature_names) if feature_names is not None else _feature_names_of(model)
    model_path = version_dir / MODEL_FILE
    tmp = model_path.with_name(MODEL_FILE + ".tmp")
    with tmp.open("wb") as f:
        pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(model_path)  # 完全に書いてから名前を付け替える（部分書き込みの防止）
    fingerprint = hashlib.sha256(model_path.read_bytes()).hexdigest()

    manifest = {
        "name": name,
        "work": work,
        "version": version,
        "format": "pickle",
        "fingerprint": fingerprint,
        "data_fingerprint": data_fingerprint,
        "feature_names": list(names),
        "config": dict(config) if config else {},
        "metrics": dict(metrics) if metrics else {},
        "python": platform.python_version(),
        "dependencies": _dependencies(),
        "created": _utcnow().isoformat(),
    }
    # manifest は最後に書く（存在＝保存完了の印）。
    (version_dir / MANIFEST_FILE).write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return _record_from_manifest(version_dir)


def _versions(model_dir: Path) -> list[str]:
    if not model_dir.is_dir():
        return []
    return sorted(d.name for d in model_dir.iterdir() if d.is_dir() and d.name != PROMOTIONS_DIR)


def load_model(
    root: Path,
    *,
    name: str,
    work: str,
    version: str | None = None,
    warn_dependencies: bool = False,
) -> tuple[object, ModelRecord]:
    """保存済みモデルを読む。version=None は最新（版の降順 1 件）。manifest 無し・指紋不一致は拒否。"""
    model_dir = _model_dir(root, work=work, name=name)
    if version is None:
        found = _versions(model_dir)
        if not found:
            raise FileNotFoundError(f"モデル {work}/{name} の保存が無い: {model_dir}")
        version = found[-1]
    version_dir = model_dir / version
    if not (version_dir / MANIFEST_FILE).is_file():
        raise ValueError(f"{work}/{name}/{version}: manifest が無い（壊れた保存は読まない）")
    record = _record_from_manifest(version_dir)
    if record.format != "pickle":
        raise NotImplementedError(f"形式 '{record.format}' は未対応（pickle のみ）")
    model_path = version_dir / MODEL_FILE
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != record.fingerprint:
        raise ValueError(f"{work}/{name}/{version}: 指紋が一致しない（実体が改変・破損）")
    if warn_dependencies:
        now = {**_dependencies(), "python": platform.python_version()}
        was = {**record.dependencies, "python": record.python}
        drift = {k: (was[k], now.get(k)) for k in was if now.get(k) != was[k]}
        if drift:
            warnings.warn(f"{work}/{name}/{version}: 学習時と依存版が違う: {drift}", stacklevel=2)
    with model_path.open("rb") as f:
        model = pickle.load(f)  # 自分が書いた manifest＋指紋の裏付けがあるファイルだけ読む
    return model, record


def list_models(root: Path, *, work: str | None = None) -> list[ModelRecord]:
    """保存済みモデルの一覧（manifest 走査の生成ビュー。台帳ファイルは作らない＝正本を二重化しない）。"""
    base = _base(root) / "work"
    if not base.is_dir():
        return []
    pattern = f"{work}/models/*/*/{MANIFEST_FILE}" if work else f"*/models/*/*/{MANIFEST_FILE}"
    records = [_record_from_manifest(m.parent) for m in base.glob(pattern)]
    return sorted(records, key=lambda r: (r.work, r.name, r.version))


def champion(root: Path, *, work: str, name: str) -> ModelRecord | None:
    """昇格記録が指す現 champion の版（生成ビュー）。昇格が無ければ None。"""
    promo_dir = _model_dir(root, work=work, name=name) / PROMOTIONS_DIR
    if not promo_dir.is_dir():
        return None
    files = sorted(promo_dir.glob("*.yaml"))
    if not files:
        return None
    latest = yaml.safe_load(files[-1].read_text(encoding="utf-8"))
    version_dir = _model_dir(root, work=work, name=name) / latest["version"]
    if not (version_dir / MANIFEST_FILE).is_file():
        raise ValueError(f"{work}/{name}: 昇格記録が指す版 {latest['version']} の実体が無い")
    return _record_from_manifest(version_dir)


def promote_model(
    root: Path,
    *,
    work: str,
    name: str,
    version: str,
    thresholds: Mapping[str, float],
    primary: str,
    higher_is_better: bool = True,
) -> Promotion:
    """昇格の関門。絶対（passes）かつ相対（現 champion に primary で勝つ）を満たすときだけ昇格する。"""
    version_dir = _model_dir(root, work=work, name=name) / version
    if not (version_dir / MANIFEST_FILE).is_file():
        raise FileNotFoundError(f"{work}/{name}/{version}: 保存が無い")
    record = _record_from_manifest(version_dir)

    if not passes(record.metrics, dict(thresholds)):
        raise ValueError(f"絶対関門で不合格: metrics={record.metrics} thresholds={dict(thresholds)}")
    if primary not in record.metrics:
        raise ValueError(f"primary 指標 '{primary}' が metrics に無い")

    champ = champion(root, work=work, name=name)
    previous = None
    if champ is not None:
        previous = champ.version
        better = record.metrics[primary] > champ.metrics[primary]
        if not higher_is_better:
            better = record.metrics[primary] < champ.metrics[primary]
        if not better:
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
        "higher_is_better": higher_is_better,
        "metrics": dict(record.metrics),
        "previous_version": previous,
    }
    promo_dir = _model_dir(root, work=work, name=name) / PROMOTIONS_DIR
    promo_dir.mkdir(parents=True, exist_ok=True)
    (promo_dir / f"{decided}.yaml").write_text(
        yaml.safe_dump(promotion, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return Promotion(
        work=work,
        name=name,
        version=version,
        decided=decided,
        primary=primary,
        higher_is_better=higher_is_better,
        metrics=dict(record.metrics),
        previous_version=previous,
    )
