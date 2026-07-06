"""models.py（学習済み Pipeline の保存・読込・一覧・昇格）のテスト。

時刻は `_utcnow` を差し替えて固定する（版＝時刻なので、再利用拒否・最新解決を構成で確かめられる）。
期待値はテストデータ・保存レイアウトの構成から導ける（実装出力の写経はしない）。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sklearn.base import BaseEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness import storage
from harness.ds import data
from harness.ds import models as model_store
from harness.ds.features import Columns, FeaturePipeline, Interactions

pytestmark = pytest.mark.integration

_T1 = datetime(2026, 7, 3, 9, 0, 0, tzinfo=UTC)
_T2 = datetime(2026, 7, 3, 11, 0, 0, tzinfo=UTC)
_T3 = datetime(2026, 7, 3, 13, 0, 0, tzinfo=UTC)
_V1 = "20260703T090000000000Z"
_V2 = "20260703T110000000000Z"
_V3 = "20260703T130000000000Z"


def _clock(monkeypatch: pytest.MonkeyPatch, times: list[datetime]) -> None:
    # save_model は _utcnow を 2 回呼ぶ（version・created）。各時刻を 2 回ずつ返し、
    # 尽きたら実時刻へフォールバック（昇格記録など版に依らない呼び出し用・単調増加）。
    seq = iter([t for t in times for _ in range(2)])

    def _next() -> datetime:
        try:
            return next(seq)
        except StopIteration:
            return datetime.now(UTC)

    monkeypatch.setattr(model_store, "_utcnow", _next)


def _fitted(*, interaction: bool = False) -> Pipeline:
    df = data.generate_synthetic(n=40, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    blocks: list[tuple[str, Any]] = [("columns", Columns(["x1", "x2"]))]
    if interaction:
        blocks.append(("inter", Interactions([("x1", "x2")])))
    est = Pipeline(
        [("features", FeaturePipeline(blocks)), ("model", LogisticRegression(random_state=0, max_iter=1000))]
    )
    est.fit(df, y)
    return est


def test_save_load_roundtrip_and_feature_names(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, [_T1])
    proj = make_project()
    est = _fitted(interaction=True)
    record = model_store.save_model(proj.root, est, name="baseline", work="E-0001", metrics={"roc_auc": 0.9})

    assert record.version == _V1
    assert record.feature_names == ("x1", "x2", "x1_x_x2")  # get_feature_names_out から自動導出
    loaded, loaded_record = model_store.load_model(proj.root, name="baseline", work="E-0001")
    df = data.generate_synthetic(n=8, seed=1)
    # 同一オブジェクトの復元（load は object を返すので予測呼び出しは型無視）。
    np.testing.assert_array_equal(loaded.predict_proba(df), est.predict_proba(df))  # type: ignore[attr-defined]
    assert loaded_record.fingerprint == record.fingerprint


def test_same_version_is_rejected(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _clock(monkeypatch, [_T1, _T1])  # 2 回の save を同じ時刻にする
    proj = make_project()
    model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001")
    with pytest.raises(ValueError, match="版は再利用しない"):
        model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001")


def test_latest_version_resolution(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _clock(monkeypatch, [_T1, _T2])
    proj = make_project()
    model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001", config={"v": 1})
    model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001", config={"v": 2})
    _, latest = model_store.load_model(proj.root, name="baseline", work="E-0001")  # version=None
    assert latest.version == _V2  # 降順 1 件＝新しい方
    _, old = model_store.load_model(proj.root, name="baseline", work="E-0001", version=_V1)
    assert old.config == {"v": 1}


def test_rejects_missing_manifest_tampered_and_bad_format(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, [_T1])
    proj = make_project()
    record = model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001")

    # 指紋不一致（実体を改変）。
    (record.path / "model.pkl").write_bytes((record.path / "model.pkl").read_bytes() + b"x")
    with pytest.raises(ValueError, match="指紋"):
        model_store.load_model(proj.root, name="baseline", work="E-0001")
    # 形式が FORMATS に無い（T-0084 で onnx は登録済みになったため、未登録の名前で検査する）。
    manifest = record.path / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("format: pickle", "format: feather"), encoding="utf-8"
    )
    with pytest.raises(NotImplementedError, match="feather"):
        model_store.load_model(proj.root, name="baseline", work="E-0001")
    # manifest 無し（版を明示指定）＝壊れた保存は読まない。
    manifest.unlink()
    with pytest.raises(ValueError, match="manifest"):
        model_store.load_model(proj.root, name="baseline", work="E-0001", version=record.version)
    # version=None は manifest のある版だけを候補にする → 有効な保存が 1 つも無い扱い。
    with pytest.raises(FileNotFoundError, match="保存が無い"):
        model_store.load_model(proj.root, name="baseline", work="E-0001")


def test_non_file_backend_is_not_implemented(make_project: Callable[..., Any]) -> None:
    proj = make_project(
        config='[data]\ndefault_backend = "local"\n\n[data.backends.local]\nuri = "s3:bucket"\n\n[data.layer]\n'
    )
    with pytest.raises(NotImplementedError, match="s3"):
        model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001")


def test_promotion_gate(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _clock(monkeypatch, [_T1, _T2])
    proj = make_project()
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics={"roc_auc": 0.85})
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics={"roc_auc": 0.90})

    # 絶対関門で不合格（閾値 0.95 に届かない）。
    with pytest.raises(ValueError, match="絶対関門"):
        model_store.promote_model(
            proj.root, work="E-0001", name="m", version=_V1, thresholds={"roc_auc": 0.95}, primary="roc_auc"
        )
    # 初回昇格は無条件（0.85 で champion に）。
    model_store.promote_model(
        proj.root, work="E-0001", name="m", version=_V1, thresholds={"roc_auc": 0.80}, primary="roc_auc"
    )
    champ1 = model_store.champion(proj.root, work="E-0001", name="m")
    assert champ1 is not None and champ1.version == _V1
    # 勝つ 2 件目（0.90>0.85）で champion 移動。
    model_store.promote_model(
        proj.root, work="E-0001", name="m", version=_V2, thresholds={"roc_auc": 0.80}, primary="roc_auc"
    )
    champ2 = model_store.champion(proj.root, work="E-0001", name="m")
    assert champ2 is not None and champ2.version == _V2


def test_promotion_relative_reject(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # 先に強い版（0.90）を champion に、後から劣る版（0.85）を昇格しようとすると相対関門で棄却。
    _clock(monkeypatch, [_T1, _T2])
    proj = make_project()
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics={"roc_auc": 0.90})
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics={"roc_auc": 0.85})
    model_store.promote_model(
        proj.root, work="E-0001", name="m", version=_V1, thresholds={"roc_auc": 0.80}, primary="roc_auc"
    )
    with pytest.raises(ValueError, match="相対関門"):
        model_store.promote_model(
            proj.root, work="E-0001", name="m", version=_V2, thresholds={"roc_auc": 0.80}, primary="roc_auc"
        )


def test_promotion_direction_resolved_from_registry(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # log_loss は小さいほど良い（向きの正本は eval.METRICS）。呼び手の既定値に頼らず、
    # 劣る候補（log_loss が大きい）は棄却・勝つ候補（小さい）だけ昇格する。
    _clock(monkeypatch, [_T1, _T2, _T3])
    proj = make_project()
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics={"log_loss": 0.50})
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics={"log_loss": 0.60})
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics={"log_loss": 0.40})
    promo = model_store.promote_model(
        proj.root, work="E-0001", name="m", version=_V1, thresholds={"log_loss": 0.70}, primary="log_loss"
    )
    assert promo.higher_is_better is False  # レジストリで解決した向きが記録に残る
    # 劣る候補（0.60 > 0.50）は相対関門で棄却（向きを取り違えて昇格しない）。
    with pytest.raises(ValueError, match="相対関門"):
        model_store.promote_model(
            proj.root, work="E-0001", name="m", version=_V2, thresholds={"log_loss": 0.70}, primary="log_loss"
        )
    # 勝つ候補（0.40 < 0.50）は昇格し champion が移動する。
    model_store.promote_model(
        proj.root, work="E-0001", name="m", version=_V3, thresholds={"log_loss": 0.70}, primary="log_loss"
    )
    champ = model_store.champion(proj.root, work="E-0001", name="m")
    assert champ is not None and champ.version == _V3


def test_promotion_rejects_unknown_primary_and_contradicting_direction(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, [_T1])
    proj = make_project()
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics={"log_loss": 0.50})
    # METRICS に無い primary は typo を黙って通さず ValueError。
    with pytest.raises(ValueError, match="未登録"):
        model_store.promote_model(proj.root, work="E-0001", name="m", version=_V1, thresholds={}, primary="nope")
    # レジストリの向き（log_loss=小さいほど良い）と矛盾する指定は拒否。
    with pytest.raises(ValueError, match="矛盾"):
        model_store.promote_model(
            proj.root, work="E-0001", name="m", version=_V1, thresholds={}, primary="log_loss", higher_is_better=True
        )
    # 一致する明示指定は許す（初回昇格が成立する）。
    promo = model_store.promote_model(
        proj.root, work="E-0001", name="m", version=_V1, thresholds={}, primary="log_loss", higher_is_better=False
    )
    assert promo.higher_is_better is False


def _fitted_with_to_numpy() -> Pipeline:
    """to_numpy 境界つきの学習済み Pipeline（onnx 形式は境界の尾部だけを変換する＝T-0084）。"""
    from harness.ds.pipeline import build_estimator, build_model

    df = data.generate_synthetic(n=40, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    est = build_estimator(
        {"features": [{"kind": "columns", "columns": ["x1", "x2"]}]}, build_model({"kind": "logreg"}, seed=0), seed=0
    )
    est.fit(df, y)
    return est


@pytest.mark.parametrize("fmt", sorted(model_store.FORMATS))
def test_format_roundtrip(fmt: str, make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # FORMATS の全形式で save→load の往復（optional 未導入ならその形式は対象外＝条件登録の構成どおり）。
    # 実体ファイル名は FORMATS の file_name・manifest の format は指定値、と構成から導ける。
    _clock(monkeypatch, [_T1])
    proj = make_project()
    if fmt == "onnx":
        # onnx は to_numpy 境界つきの構成が対象（詳細な契約・エラー系は test_ds_models_onnx.py が担う）。
        est = _fitted_with_to_numpy()
    else:
        est = _fitted(interaction=True)  # FeaturePipeline（自作型）入り＝信頼リスト経路も往復で確かめる
    record = model_store.save_model(proj.root, est, name="baseline", work="E-0001", format=fmt)
    assert record.format == fmt
    assert (record.path / model_store.FORMATS[fmt].file_name).is_file()
    loaded, loaded_record = model_store.load_model(proj.root, name="baseline", work="E-0001")
    assert loaded_record.format == fmt
    df = data.generate_synthetic(n=8, seed=1)
    if fmt == "onnx":  # ONNX は同一計算の float32 別表現（同一オブジェクトの復元ではない）＝丸め差まで許容
        np.testing.assert_allclose(loaded.predict_proba(df), est.predict_proba(df), rtol=1e-3, atol=1e-4)  # type: ignore[attr-defined]
    else:
        np.testing.assert_array_equal(loaded.predict_proba(df), est.predict_proba(df))  # type: ignore[attr-defined]


def test_unknown_format_is_rejected_with_hint(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # FORMATS に無い形式は保存前に拒否（版ディレクトリも作らない）。skops の導入手順をメッセージで案内する。
    # （T-0084 で onnx は登録済みになったため、未登録の名前 feather で検査する。）
    _clock(monkeypatch, [_T1])
    proj = make_project()
    with pytest.raises(ValueError, match=r"feather.*uv sync --extra skops"):
        model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001", format="feather")
    assert not model_store._model_dir(proj.root, work="E-0001", name="baseline").exists()  # 版ディレクトリ未作成


class _Unvetted(BaseEstimator):  # type: ignore[misc]
    """TRUSTED_HARNESS_TYPES に載っていない自作型（信頼リスト検査のテスト専用）。"""


def test_skops_load_rejects_untrusted_file(tmp_path: Path) -> None:
    # load 時の防御（外部から渡された・改竄された .skops への任意コード実行防御）。
    # 保存ガードを迂回して直接作った悪意ファイル（信頼リスト外の型）を、_skops_load が load 前に拒否する。
    # 未知の型の検査が trusted 指定より先＝信頼リストに無い型は skops.io.load に到達しない。
    skops_io = pytest.importorskip("skops.io")  # optional extra（ISS ではない）
    from harness.ds.models import _skops_load

    evil = tmp_path / "evil.skops"
    skops_io.dump(_Unvetted(), evil)  # 当リポの save ガードを通さず直接作った外部ファイル相当
    with pytest.raises(ValueError, match=r"信頼リスト.*_Unvetted"):
        _skops_load(evil)


@pytest.mark.unit
def test_skops_load_corrupt_file_raises_valueerror(tmp_path: Path) -> None:
    # 壊れた/空の .skops（skops 形式でない）は、素の BadZipFile でなく明示型（ValueError）で失敗する契約。
    pytest.importorskip("skops")
    from harness.ds.models import _skops_load

    broken = tmp_path / "broken.skops"
    broken.write_bytes(b"not a zip file")  # skops は zip 形式なので解析に失敗する
    with pytest.raises(ValueError, match=r"解析できない"):
        _skops_load(broken)


def test_orphan_version_dir_is_ignored(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # 保存が mkdir 後・manifest 前に落ちた孤児ディレクトリ（辞書順で最新・manifest 無し）が
    # あっても、version=None の最新解決は manifest のある良い版を返す（永久に壊れない）。
    _clock(monkeypatch, [_T1])
    proj = make_project()
    record = model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001")
    (record.path.parent / _V2).mkdir()  # 孤児：_V1 より新しい名前・manifest 無し
    _, latest = model_store.load_model(proj.root, name="baseline", work="E-0001")
    assert latest.version == _V1  # 孤児を飛ばして良い版に解決する
    # 一覧も孤児を出さない（manifest 走査＝従来から一致）。
    assert [r.version for r in model_store.list_models(proj.root, work="E-0001")] == [_V1]


# --- T-0059 来歴（git・lock_fingerprint）＋ model_card ---


def _init_git_repo(root: Path) -> None:
    # 一時プロジェクトを構成から git リポにする（branch=main・空コミット 1 つ）。
    # 全体/システムの git 設定を無効化して環境非依存にする（署名・テンプレート等の影響を受けない）。
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}

    def _run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)

    _run("init", "-b", "main")
    _run("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init")


def test_manifest_records_git_provenance_and_lock_fingerprint(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 期待値は構成から導く：branch は `git init -b main` で "main"・dirty は未追跡ファイル
    # （.harness/config.toml 等）が必ずあるので True・commit は非空 str（具体値は環境依存なのでハードコードしない）。
    _clock(monkeypatch, [_T1])
    proj = make_project()
    _init_git_repo(proj.root)
    lock_body = b"locked-by-test\n"
    (proj.root / "uv.lock").write_bytes(lock_body)

    record = model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001")

    # record は manifest.yaml を読み直した結果（save_model の返し方）＝ manifest への記録も同時に確かめている。
    assert record.git is not None
    assert isinstance(record.git["commit"], str) and record.git["commit"]
    assert record.git["branch"] == "main"
    assert record.git["dirty"] is True
    # lock 指紋＝置いた中身の sha256（64 桁 hex・構成から導出）。
    assert record.lock_fingerprint == hashlib.sha256(lock_body).hexdigest()


def test_provenance_is_none_outside_git_and_without_lock(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 非 git・uv.lock 無しの一時プロジェクト＝両方 None。かつ保存自体は成功する（来歴取得が保存を止めない）。
    # 上位に git リポがある環境でも決定的にするため、探索の上限を tmp_path に固定する。
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    _clock(monkeypatch, [_T1])
    proj = make_project()  # tmp_path 配下＝git リポ外・uv.lock 無し
    record = model_store.save_model(proj.root, _fitted(), name="baseline", work="E-0001")
    assert record.git is None
    assert record.lock_fingerprint is None


@pytest.mark.unit
def test_old_manifest_without_provenance_keys_reads_as_none(tmp_path: Path) -> None:
    # T-0059 以前の manifest（git/lock_fingerprint キー無し）を手で構成 → None 埋めで読める（後方互換）。
    old = {
        "name": "baseline",
        "work": "E-0001",
        "version": _V1,
        "format": "pickle",
        "fingerprint": "0" * 64,
        "data_fingerprint": None,
        "feature_names": ["x1"],
        "config": {},
        "metrics": {"roc_auc": 0.9},
        "python": "3.14.0",
        "dependencies": {},
        "created": _T1.isoformat(),
    }
    storage.write_manifest(tmp_path / "manifest.yaml", old)
    record = model_store._record_from_manifest(tmp_path)
    assert record.git is None
    assert record.lock_fingerprint is None
    assert record.metrics == {"roc_auc": 0.9}  # 既存フィールドは従来どおり読める


@pytest.mark.unit
def test_model_card_contains_key_fields() -> None:
    # 構成した record の値がそのまま文字列に含まれる（期待値は入力の構成から導く・実装出力の写経でない）。
    record = model_store.ModelRecord(
        name="baseline",
        work="E-0001",
        version=_V1,
        format="pickle",
        fingerprint="f" * 64,
        data_fingerprint="d" * 64,
        feature_names=("x1",),
        config={},
        metrics={"roc_auc": 0.9},
        python="3.14.0",
        dependencies={"numpy": "2.0.0"},
        created=_T1.isoformat(),
        path=Path("."),
        git={"commit": "abc1234", "branch": "main", "dirty": False},
        lock_fingerprint="a" * 64,
    )
    card = model_store.model_card(record)
    for expected in ("baseline", _V1, "pickle", "roc_auc: 0.9", "f" * 64, "abc1234", "main", "a" * 64, "3.14.0"):
        assert expected in card
    assert "\n" in card  # 複数行の体裁（キー: 値の行区切り）


@pytest.mark.unit
def test_model_card_without_provenance_shows_placeholder() -> None:
    # 古い manifest 由来（git/lock 無し）でも落ちず、無い項目は「-」で示す。
    record = model_store.ModelRecord(
        name="old",
        work="E-0001",
        version=_V1,
        format="pickle",
        fingerprint="0" * 64,
        data_fingerprint=None,
        feature_names=(),
        config={},
        metrics={},
        python="3.14.0",
        dependencies={},
        created=_T1.isoformat(),
        path=Path("."),
    )
    card = model_store.model_card(record)
    assert "git: -" in card
    assert "lock_fingerprint: -" in card


@pytest.mark.unit
def test_skops_roundtrip_stateful_pipeline(make_project: Any) -> None:
    pytest.importorskip("skops")
    # 状態を持つ Pipeline（count_encode の polars 統計＋TargetEncoder の KFold＋モデル）を skops で往復。
    # 信頼リストが不足していると save 時に fail-loud で止まる（読めないモデルを作らない）＝この往復が成功＝リスト充足。
    import numpy as np
    import polars as pl

    from harness.ds.pipeline import build_estimator, build_model

    rng = np.random.default_rng(0)
    df = pl.DataFrame({"id": np.arange(80), "x1": rng.normal(size=80), "cat": (np.arange(80) % 5).astype(str)})
    y = (np.arange(80) % 2).astype(np.float64)
    spec = {
        "features": [
            {"kind": "columns", "columns": ["x1", "cat"]},
            {"kind": "count_encode", "columns": ["cat"]},
        ],
        "encode": [{"kind": "target", "columns": ["cat"]}],
    }
    est = build_estimator(spec, build_model({"kind": "logreg"}, seed=0), seed=0)
    est.fit(df, y)
    proj = make_project()
    rec = model_store.save_model(proj.root, est, name="m", work="E", format="skops")
    assert rec.format == "skops"
    loaded, _ = model_store.load_model(proj.root, name="m", work="E")
    reloaded: Any = loaded  # 保存モデルは object 型で返る＝復元後は動的に予測を呼ぶ
    # 復元したモデルは同じ確率を返す（状態が正しく往復した）。
    np.testing.assert_allclose(reloaded.predict_proba(df)[:, 1], est.predict_proba(df)[:, 1])


@pytest.mark.unit
def test_skops_save_fails_loud_on_untrusted_type(make_project: Any) -> None:
    pytest.importorskip("skops")
    # 信頼リストに無い型を含むモデルは、読めなくなる前に save 時点で止める（不完全な保存も残さない）。
    # _Unvetted は module 直下の「信頼リスト外の自作型」（load 拒否テストと共用）。
    proj = make_project()
    with pytest.raises(ValueError, match="信頼リスト外"):
        model_store.save_model(proj.root, _Unvetted(), name="m", work="E", format="skops")
    # 保存に失敗した実体が「どこにも」残らない（本体 .skops も書きかけの .skops.tmp も）。
    # 保存先は config の uri（既定 file:data）配下＝固定パス決め打ちにせず proj.root 全体を走査する
    # （誤ったパスを見て常に空＝空振りにしないため。atomic_write の tmp 削除が退行したら必ず落ちる）。
    leftovers = list(proj.root.rglob("*.skops")) + list(proj.root.rglob("*.skops.tmp"))
    assert not leftovers, f"不完全な skops 保存が残っている: {leftovers}"
