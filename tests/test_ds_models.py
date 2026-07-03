"""models.py（学習済み Pipeline の保存・読込・一覧・昇格）のテスト。

時刻は `_utcnow` を差し替えて固定する（版＝時刻なので、再利用拒否・最新解決を構成で確かめられる）。
期待値はテストデータ・保存レイアウトの構成から導ける（実装出力の写経はしない）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness.ds import data
from harness.ds import models as model_store
from harness.ds.features import Columns, FeaturePipeline, Interactions

pytestmark = pytest.mark.integration

_T1 = datetime(2026, 7, 3, 9, 0, 0, tzinfo=UTC)
_T2 = datetime(2026, 7, 3, 11, 0, 0, tzinfo=UTC)
_V1 = "20260703T090000000000Z"
_V2 = "20260703T110000000000Z"


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
    est = Pipeline([("features", FeaturePipeline(blocks)), ("model", LogisticRegression(random_state=0, max_iter=1000))])
    est.fit(df, y)
    return est


def test_save_load_roundtrip_and_feature_names(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _clock(monkeypatch, [_T1])
    proj = make_project()
    est = _fitted(interaction=True)
    record = model_store.save_model(proj.root, est, name="baseline", work="E-0001", metrics={"roc_auc": 0.9})

    assert record.version == _V1
    assert record.feature_names == ("x1", "x2", "x1_x_x2")  # get_feature_names_out から自動導出
    loaded, loaded_record = model_store.load_model(proj.root, name="baseline", work="E-0001")
    df = data.generate_synthetic(n=8, seed=1)
    np.testing.assert_array_equal(loaded.predict_proba(df), est.predict_proba(df))  # 同一オブジェクトの復元
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
    # 形式が pickle でない。
    manifest = record.path / "manifest.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("format: pickle", "format: onnx"), encoding="utf-8")
    with pytest.raises(NotImplementedError, match="onnx"):
        model_store.load_model(proj.root, name="baseline", work="E-0001")
    # manifest 無し。
    manifest.unlink()
    with pytest.raises(ValueError, match="manifest"):
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
        model_store.promote_model(proj.root, work="E-0001", name="m", version=_V1, thresholds={"roc_auc": 0.95}, primary="roc_auc")
    # 初回昇格は無条件（0.85 で champion に）。
    model_store.promote_model(proj.root, work="E-0001", name="m", version=_V1, thresholds={"roc_auc": 0.80}, primary="roc_auc")
    assert model_store.champion(proj.root, work="E-0001", name="m").version == _V1
    # 勝つ 2 件目（0.90>0.85）で champion 移動。
    model_store.promote_model(proj.root, work="E-0001", name="m", version=_V2, thresholds={"roc_auc": 0.80}, primary="roc_auc")
    assert model_store.champion(proj.root, work="E-0001", name="m").version == _V2
