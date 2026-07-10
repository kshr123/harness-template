"""学習済みモデル（sklearn Pipeline 丸ごと）の保存・読み込み・一覧・昇格。

- 実体は pickle 1 ファイル（特徴量→モデルの Pipeline を丸ごと。前処理と本体がずれない）。
- store.py と同じ4作法（config URI で置き場を解決／一時ファイル→rename／sha256 指紋／manifest.yaml）は
  harness.storage の共通部品で行い、ここは方針（保存は常に許す・関門は昇格だけ・manifest 最後＝完了の印）を持つ。
- 保存は常に許す（実験の記録）。関門は昇格だけ（負の結果も記録で完了、と両立する）。
- 形式は FORMATS レジストリが担う（manifest の `format` 文字列で save/load が分岐する拡張ポイント）。
  pickle（既定・常に登録）と skops（安全読込・optional extra `skops` で条件登録）。可搬形式（onnx 等）が
  要る時はここに枝を足す。
- harness/models.py（PM の Item 型）と紛れるので、import は必ず
  `from harness.ds import models as model_store` と別名にする（規約）。この核は sklearn を import しない。
"""

from __future__ import annotations

import importlib.util
import pickle
import platform
import subprocess
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from harness import storage
from harness.config import load_config
from harness.ds.eval import METRICS, passes

MANIFEST_FILE = "manifest.yaml"
PROMOTIONS_DIR = "promotions"
VERSION_FORMAT = "%Y%m%dT%H%M%S%fZ"  # 辞書順＝時刻順（最新＝降順1件）
# 依存版を記録する配布物（入っていないものは飛ばす）。記録のみ・照合は既定でしない。
TRACKED_DISTRIBUTIONS = ("scikit-learn", "numpy", "polars", "lightgbm", "statsmodels")


# --- 保存形式（FORMATS レジストリ・拡張ポイント） ---


@dataclass(frozen=True)
class ModelFormat:
    """保存形式 1 件（FORMATS レジストリの値）。

    dump は atomic_write 経由で一時パスに書く（部分書き込み防止は storage が担う）。
    load は manifest＋指紋照合を通ったパスだけを受ける。file_name は版ディレクトリ内の実体ファイル名。
    """

    dump: Callable[[object, Path], None]
    load: Callable[[Path], object]
    file_name: str
    description: str


def _pickle_dump(model: object, path: Path) -> None:
    with path.open("wb") as f:
        pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)


def _pickle_load(path: Path) -> object:
    with path.open("rb") as f:
        # 自分が書いた manifest＋指紋の裏付けがあるファイルだけ読む（load_model が照合してから呼ぶ）。
        return pickle.load(f)


# skops の安全読込で信頼する自作型（module.qualname）。ここに無い型が入った保存は load で拒否する。
# 追加するときは、その型の __reduce__/__setstate__ が任意コード実行にならないことを確認してから足すこと。
TRUSTED_HARNESS_TYPES = (
    # features.py：Pipeline に入る自作 transformer（FeaturePipeline と各ブロック）。
    "harness.ds.features.FeaturePipeline",
    "harness.ds.features.FeatureBlock",
    "harness.ds.features.Columns",
    "harness.ds.features.Interactions",
    "harness.ds.features.Ratios",
    "harness.ds.features.Differences",
    "harness.ds.features.GroupAggregate",
    "harness.ds.features.CountEncode",
    "harness.ds.features.CombineKeys",
    "harness.ds.features.MultiHot",
    "harness.ds.features.TargetAggregate",
    # unsupervised.py：特徴経路の薄い包み。
    "harness.ds.unsupervised.ClusterLabel",
    "harness.ds.unsupervised.AnomalyScore",
    # pipeline.py：FunctionTransformer に入るモジュール関数（lambda 不可の代わり）。
    "harness.ds.pipeline._to_numpy",
    "harness.ds.pipeline._fill_text",
    "harness.ds.pipeline._densify",
    # 科学計算スタックの標準型（fit 済み Pipeline に正当に現れる。いずれも自前のバイナリ復元で任意コード実行はしない）。
    # ※ 型名は skops の get_untrusted_types が返す実際の名前（全ブロック×全エンコーダ×全モデル種の stateful
    #    Pipeline を保存して実測して確定）。StratifiedKFold は現行では未観測だが、多クラス/層化 target 化で現れる
    #    ための前方互換の防御的登録（純データ型で過剰信頼のリスクなし）。
    "polars.dataframe.frame.DataFrame",  # GroupAggregate/CountEncode/TargetAggregate の fit 済み統計
    "numpy.dtype",  # cluster/anomaly_score エンコーダ等
    "collections.OrderedDict",
    "sklearn.model_selection._split.KFold",  # TargetEncoder(cv=KFold(...))
    "sklearn.model_selection._split.StratifiedKFold",  # 前方互換（層化 target・多クラス）。現行未観測
    # lightgbm（optional。導入時のみ Pipeline に現れる）。
    "lightgbm.sklearn.LGBMClassifier",
    "lightgbm.sklearn.LGBMRegressor",
    "lightgbm.basic.Booster",
)


def _skops_dump(model: object, path: Path) -> None:
    import skops.io  # 遅延 import（条件登録済みだが、import コストも使う時まで遅らせる）

    skops.io.dump(model, path)
    # 「読めない skops を作らない」：保存直後に信頼リスト外の型が無いか確かめ、あれば保存を失敗させる。
    # 後で load 不能になる罠（保存できるが読めないモデル）を防ぐ。atomic_write が tmp を消すので不完全な保存は残らない。
    unknown = set(skops.io.get_untrusted_types(file=path)) - set(TRUSTED_HARNESS_TYPES)
    if unknown:
        raise ValueError(
            f"skops 保存に信頼リスト外の型が含まれる: {sorted(unknown)}"
            "（読めないモデルを保存しないため保存時に止める。監査のうえ TRUSTED_HARNESS_TYPES に足すこと）"
        )


def _skops_load(path: Path) -> object:
    """skops の安全読込。未知の型の検査が先・trusted は明示リストで渡す（順序と明示性が安全性の要）。"""
    import skops.io

    try:
        found = skops.io.get_untrusted_types(file=path)
    except Exception as exc:  # 壊れた/空の .skops（BadZipFile 等）は読込失敗として明示型（ValueError）で再送出
        raise ValueError(f"{path}: skops ファイルを解析できない（壊れているか skops 形式でない）: {exc}") from exc
    unknown = set(found) - set(TRUSTED_HARNESS_TYPES)
    if unknown:
        raise ValueError(
            f"{path}: 信頼リストに無い型が含まれる: {sorted(unknown)}"
            "（監査のうえ TRUSTED_HARNESS_TYPES に足してから読み直すこと）"
        )
    # trusted は信頼リストそのものを明示的に渡す（untrusted 集合を渡す実装依存を避け、上の検査と独立に安全）。
    return skops.io.load(path, trusted=list(TRUSTED_HARNESS_TYPES))


FORMATS: dict[str, ModelFormat] = {
    # "pickle" は常に登録（既定・後方互換。既存の保存は format: pickle として読める）。
    "pickle": ModelFormat(
        dump=_pickle_dump,
        load=_pickle_load,
        file_name="model.pkl",
        description="pickle 1 ファイル（既定）。速く確実だが、読む側は指紋照合済みの自前ファイルに限る。",
    ),
}

# optional 依存の形式はここで「入っていれば登録」する（MODELS の lightgbm と同じ条件登録・find_spec は import ゼロ）。
if importlib.util.find_spec("skops") is not None:
    FORMATS["skops"] = ModelFormat(
        dump=_skops_dump,
        load=_skops_load,
        file_name="model.skops",
        description="skops（安全読込）。信頼リスト（TRUSTED_HARNESS_TYPES）に無い型は load で拒否する。",
    )

# ONNX（可搬形式・optional extra `onnx`）。変換＝skl2onnx・読込＝onnxruntime の両方が要る＝両方在るときだけ登録。
# 実体は onnx_format.py（この核を肥らせない。onnx_format の module top は stdlib＋numpy のみ＝import は軽い）。
if importlib.util.find_spec("skl2onnx") is not None and importlib.util.find_spec("onnxruntime") is not None:
    from harness.ds.onnx_format import _onnx_dump, _onnx_load

    FORMATS["onnx"] = ModelFormat(
        dump=_onnx_dump,
        load=_onnx_load,
        file_name="model.onnx",
        description="ONNX（可搬・読込で任意コード実行なし）。to_numpy 以降の sklearn 尾部のみ変換＝入力は"
        "特徴量計算済み float32。疎入力（tfidf 等）・lightgbm 尾部・forecast は対象外（dump 時にエラー）。",
    )


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
    # 来歴（T-0059 で追加）。古い manifest には無いので既定 None＝後方互換。
    git: dict[str, Any] | None = None
    lock_fingerprint: str | None = None


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
    return storage.resolve_uri(root, load_config(root).data.uri_for("models"))


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


def _git_provenance(root: Path) -> dict[str, Any] | None:
    """git 来歴（短縮 commit・branch・作業木の dirty）。git リポでない/git 不在/失敗は None＝保存は止めない。

    読むのは git コマンドの出力だけ（認証情報・.env には触れない）。
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
        # --untracked-files=normal を明示：利用者のグローバル設定 status.showUntrackedFiles に依らず、
        # 未追跡ファイルも dirty と数える（dirty の意味を環境非依存にする）。
        dirty = bool(_run("status", "--porcelain", "--untracked-files=normal"))
    except OSError, subprocess.SubprocessError, UnicodeDecodeError:
        # CalledProcessError（非 git リポ）・FileNotFoundError（git 不在）・TimeoutExpired を含む。
        # UnicodeDecodeError：git の出力が UTF-8 でない場合（来歴が取れないだけで、保存は続ける）。
        return None
    return {"commit": commit, "branch": branch, "dirty": dirty}


def _lock_fingerprint(root: Path) -> str | None:
    """root 直下の uv.lock の sha256 指紋（どのロックで作ったかの印）。無ければ None。"""
    lock = root / "uv.lock"
    if not lock.is_file():
        return None
    return storage.fingerprint(lock)


def _record_from_manifest(path: Path) -> ModelRecord:
    data = storage.read_manifest(path / MANIFEST_FILE)
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
        # 古い manifest（T-0059 以前）にはキーが無い → .get で None 埋め（後方互換）。
        git=data.get("git"),
        lock_fingerprint=data.get("lock_fingerprint"),
    )


def save_model(
    root: Path,
    model: object,
    *,
    name: str,
    work: str,
    format: str = "pickle",
    data_fingerprint: str | None = None,
    config: Mapping[str, Any] | None = None,
    metrics: Mapping[str, float] | None = None,
    feature_names: Sequence[str] | None = None,
) -> ModelRecord:
    """学習済み model（Pipeline）を FORMATS の形式＋manifest で保存する。版ディレクトリが既にあれば拒否。"""
    if format not in FORMATS:
        raise ValueError(
            f"未対応の保存形式 '{format}'（対応形式: {sorted(FORMATS)}。skops は `uv sync --extra skops` で導入）"
        )
    fmt = FORMATS[format]
    version = _utcnow().strftime(VERSION_FORMAT)
    version_dir = _model_dir(root, work=work, name=name) / version
    try:
        version_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(f"同じ版 {version} が既にある（版は再利用しない）") from exc

    names = tuple(feature_names) if feature_names is not None else _feature_names_of(model)
    # 完全に書いてから確定（部分書き込みの防止）。書き方の実体は形式（fmt.dump）が担う。
    fingerprint = storage.atomic_write(version_dir / fmt.file_name, lambda p: fmt.dump(model, p))

    manifest = {
        "name": name,
        "work": work,
        "version": version,
        "format": format,
        "fingerprint": fingerprint,
        "data_fingerprint": data_fingerprint,
        "feature_names": list(names),
        "config": dict(config) if config else {},
        "metrics": dict(metrics) if metrics else {},
        "python": platform.python_version(),
        "dependencies": _dependencies(),
        "created": _utcnow().isoformat(),
        # 来歴：どのコード（git）・どのロック（uv.lock 指紋）で作られたか。取れなければ None（保存は止めない）。
        "git": _git_provenance(root),
        "lock_fingerprint": _lock_fingerprint(root),
    }
    # manifest は最後に書く（存在＝保存完了の印）。印なので書き込みも原子的に（pickle と同じ tmp→replace）。
    storage.write_manifest(version_dir / MANIFEST_FILE, manifest)
    return _record_from_manifest(version_dir)


def _versions(model_dir: Path) -> list[str]:
    # manifest がある版だけ（＝保存完了の印。list_models の glob と同じ基準）。
    # 途中で落ちた孤児ディレクトリを最新扱いすると、良い版があるのに永久に読めなくなる。
    if not model_dir.is_dir():
        return []
    return sorted(d.name for d in model_dir.iterdir() if d.is_dir() and (d / MANIFEST_FILE).is_file())


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
    fmt = FORMATS.get(record.format)
    if fmt is None:
        raise NotImplementedError(f"形式 '{record.format}' は未対応（対応形式: {sorted(FORMATS)}）")
    model_path = version_dir / fmt.file_name
    storage.verify_fingerprint(model_path, record.fingerprint)  # 不一致＝実体が改変・破損なら ValueError
    if warn_dependencies:
        now = {**_dependencies(), "python": platform.python_version()}
        was = {**record.dependencies, "python": record.python}
        drift = {k: (was[k], now.get(k)) for k in was if now.get(k) != was[k]}
        if drift:
            warnings.warn(f"{work}/{name}/{version}: 学習時と依存版が違う: {drift}", stacklevel=2)
    model = fmt.load(model_path)  # 読み方の実体は形式が担う（指紋照合済みのファイルだけが届く）
    return model, record


def list_models(root: Path, *, work: str | None = None) -> list[ModelRecord]:
    """保存済みモデルの一覧（manifest 走査の生成ビュー。台帳ファイルは作らない＝正本を二重化しない）。"""
    base = _base(root) / "work"
    if not base.is_dir():
        return []
    pattern = f"{work}/models/*/*/{MANIFEST_FILE}" if work else f"*/models/*/*/{MANIFEST_FILE}"
    records = [_record_from_manifest(m.parent) for m in base.glob(pattern)]
    return sorted(records, key=lambda r: (r.work, r.name, r.version))


def model_card(record: ModelRecord) -> str:
    """保存済みモデル 1 版の来歴・指標を人/エージェント向けに要約する（監査・再現の確認用）。

    manifest の内容（name/version/形式/指紋/データ指紋/metrics/実行環境/git 来歴/lock 指紋/作成時刻）を
    「キー: 値」の行区切りで整形した複数行文字列を返す。print してそのまま読める。値が無い項目は「-」。
    """
    lines = [
        f"model: {record.work}/{record.name}",
        f"version: {record.version}",
        f"format: {record.format}",
        f"fingerprint: {record.fingerprint}",
        f"data_fingerprint: {record.data_fingerprint or '-'}",
        f"feature_names: {len(record.feature_names)} columns" if record.feature_names else "feature_names: -",
    ]
    if record.metrics:
        lines.append("metrics:")
        lines.extend(f"  {key}: {value}" for key, value in sorted(record.metrics.items()))
    else:
        lines.append("metrics: -")
    lines.append(f"python: {record.python}")
    if record.dependencies:
        lines.append("dependencies:")
        lines.extend(f"  {dist}: {ver}" for dist, ver in sorted(record.dependencies.items()))
    else:
        lines.append("dependencies: -")
    if record.git is not None:
        git = record.git
        lines.append(f"git: commit={git.get('commit')} branch={git.get('branch')} dirty={git.get('dirty')}")
    else:
        lines.append("git: -")
    lines.append(f"lock_fingerprint: {record.lock_fingerprint or '-'}")
    lines.append(f"created: {record.created}")
    return "\n".join(lines)


def champion(root: Path, *, work: str, name: str) -> ModelRecord | None:
    """昇格記録が指す現 champion の版（生成ビュー）。昇格が無ければ None。"""
    promo_dir = _model_dir(root, work=work, name=name) / PROMOTIONS_DIR
    if not promo_dir.is_dir():
        return None
    files = sorted(promo_dir.glob("*.yaml"))
    if not files:
        return None
    latest = storage.read_manifest(files[-1])
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
    higher_is_better: bool | None = None,
) -> Promotion:
    """昇格の関門。絶対（passes）かつ相対（現 champion に primary で勝つ）を満たすときだけ昇格する。

    primary の向き（大きいほど良いか）の正本は eval.METRICS。higher_is_better は省略が基本で、
    明示するならレジストリと一致していること（矛盾＝呼び手の思い違いなので ValueError で止める。
    向きを取り違えると劣る方が昇格してしまう）。
    """
    if primary not in METRICS:
        raise ValueError(f"未登録の primary 指標 '{primary}'（{sorted(METRICS)} のいずれか）")
    direction = METRICS[primary].higher_is_better  # 向きの正本はレジストリ
    if higher_is_better is not None and higher_is_better != direction:
        raise ValueError(
            f"higher_is_better={higher_is_better} はレジストリの向き"
            f"（{primary}: higher_is_better={direction}）と矛盾する"
        )
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
        if primary not in champ.metrics:
            # 過去の昇格と違う primary に切り替えた場合。測っていない指標では比較できない＝昇格しない
            # （passes の「測っていない＝満たしたと見なさない」と同じ規約。KeyError で落ちない）。
            raise ValueError(f"primary 指標 '{primary}' が現 champion（{champ.version}）の metrics に無い")
        if direction:
            better = record.metrics[primary] > champ.metrics[primary]
        else:
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
        "higher_is_better": direction,  # レジストリで解決した向きを記録する（呼び手の引数ではない）
        "metrics": dict(record.metrics),
        "previous_version": previous,
    }
    promo_dir = _model_dir(root, work=work, name=name) / PROMOTIONS_DIR
    promo_dir.mkdir(parents=True, exist_ok=True)
    storage.write_manifest(promo_dir / f"{decided}.yaml", promotion)
    return Promotion(
        work=work,
        name=name,
        version=version,
        decided=decided,
        primary=primary,
        higher_is_better=direction,
        metrics=dict(record.metrics),
        previous_version=previous,
    )
