"""onnx_format（FORMATS "onnx"・sklearn 尾部のみ変換・OnnxClassifier/OnnxRegressor）のテスト。

期待値は構成から導く：save→load の予測一致は「同じ fit 済み tail を別表現で持つ」性質（許容差は float32 丸め）、
確率は [0,1]・行和 1、metadata は保存した Pipeline の構成（列名・列数・クラス・予測種別）そのもの。
onnx extra は optional なので importorskip で守る（未導入環境では形式ごと不在＝ISS ではない）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from sklearn.linear_model import LogisticRegression

from harness import storage
from harness.ds import cv, data, store
from harness.ds import models as model_store
from harness.ds.cli import _data_predict
from harness.ds.onnx_format import METADATA_KEY, OnnxClassifier, OnnxRegressor, _onnx_load
from harness.ds.pipeline import build_estimator, build_model

pytest.importorskip("skl2onnx")  # optional extra `onnx`（未導入は形式ごと不在＝ISS ではない）
pytest.importorskip("onnxruntime")

pytestmark = pytest.mark.integration

# x1/x2 の 2 列＝to_numpy 境界の列がそのまま特徴量（metadata の feature_names の期待値の根拠）。
_SPEC = {"features": [{"kind": "columns", "columns": ["x1", "x2"]}]}


def _fit_binary() -> Any:
    """二値（generate_synthetic の y は 0/1）＝classes [0, 1]・prediction_kind "proba" の構成。"""
    df = data.generate_synthetic(n=60, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    est = build_estimator(_SPEC, build_model({"kind": "logreg"}, seed=0), seed=0)
    est.fit(df, y)
    return est


def _fit_multiclass(*, spread: int = 1) -> Any:
    """x1 の3分位でラベル 0/1/2（×spread で非連番を作る）。3 クラス＝"multiclass_proba" の構成。"""
    df = data.generate_synthetic(n=90, seed=0)
    x1 = df["x1"].to_numpy()
    y = (np.digitize(x1, np.quantile(x1, [1 / 3, 2 / 3])) * spread).astype(np.float64)
    est = build_estimator(_SPEC, build_model({"kind": "logreg"}, seed=0), seed=0)
    est.fit(df, y)
    return est


def _fit_regression() -> Any:
    """連続 y（2*x1 - x2）＝回帰・prediction_kind "value" の構成。"""
    df = data.generate_synthetic(n=60, seed=0)
    y = (2.0 * df["x1"].to_numpy() - df["x2"].to_numpy()).astype(np.float64)
    est = build_estimator(_SPEC, build_model({"kind": "ridge"}, seed=0), seed=0)
    est.fit(df, y)
    return est


def test_binary_roundtrip_matches_sklearn(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    est = _fit_binary()
    record = model_store.save_model(proj.root, est, name="onnx-bin", work="E-0001", format="onnx")
    assert record.format == "onnx"  # manifest スキーマは不変（format 文字列が変わるだけ）
    assert (record.path / "model.onnx").is_file()  # FORMATS["onnx"].file_name の実体
    assert record.fingerprint == storage.fingerprint(record.path / "model.onnx")  # 指紋＝実体の sha256

    loaded, _ = model_store.load_model(proj.root, name="onnx-bin", work="E-0001")
    assert isinstance(loaded, OnnxClassifier)
    np.testing.assert_array_equal(loaded.classes_, np.array([0, 1], dtype=np.int64))  # y の構成（0/1 二値）から

    new = data.generate_synthetic(n=16, seed=1)
    proba = loaded.predict_proba(new)
    assert proba.shape == (16, 2)
    assert proba.dtype == np.float64
    np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)  # 各行は確率分布
    # 同じ fit 済み tail の別表現＝sklearn の predict_proba と一致（許容差は float32 丸め）。
    np.testing.assert_allclose(proba, np.asarray(est.predict_proba(new)), rtol=1e-3, atol=1e-4)
    np.testing.assert_array_equal(loaded.predict(new), np.asarray(est.predict(new)).astype(np.int64))
    # cv._predict 互換＝二値は陽性（ラベル 1）確率の 1 列（data predict が無改修で使える契約）。
    pos = cv._predict(loaded, new, "proba")
    np.testing.assert_allclose(pos, np.asarray(est.predict_proba(new))[:, 1], rtol=1e-3, atol=1e-4)


def test_metadata_contract_is_burned_in(make_project: Callable[..., Any]) -> None:
    import onnxruntime

    proj = make_project()
    record = model_store.save_model(proj.root, _fit_binary(), name="onnx-meta", work="E-0001", format="onnx")
    sess = onnxruntime.InferenceSession(str(record.path / "model.onnx"), providers=["CPUExecutionProvider"])
    meta = json.loads(sess.get_modelmeta().custom_metadata_map[METADATA_KEY])
    # すべて保存した Pipeline の構成から：columns ブロックの 2 列・二値（0/1）・特徴量済み float32 入力。
    assert meta == {
        "feature_names": ["x1", "x2"],
        "n_features": 2,
        "input_dtype": "float32",
        "prediction_kind": "proba",
        "classes": [0, 1],
        "source": "harness.ds",
    }


def test_multiclass_roundtrip(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    est = _fit_multiclass()
    model_store.save_model(proj.root, est, name="onnx-mc", work="E-0001", format="onnx")
    loaded, _ = model_store.load_model(proj.root, name="onnx-mc", work="E-0001")
    assert isinstance(loaded, OnnxClassifier)
    np.testing.assert_array_equal(loaded.classes_, np.array([0, 1, 2], dtype=np.int64))  # 3分位ラベルの構成から

    new = data.generate_synthetic(n=12, seed=2)
    proba = loaded.predict_proba(new)
    assert proba.shape == (12, 3)  # クラス数ぶんの列（陽性 1 列に潰さない）
    np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)
    np.testing.assert_allclose(proba, np.asarray(est.predict_proba(new)), rtol=1e-3, atol=1e-4)
    assert cv._predict(loaded, new, "proba").shape == (12, 3)  # 多クラス契約（連番検査）を通る


def test_multiclass_nonconsecutive_labels_rejected(make_project: Callable[..., Any]) -> None:
    # ラベル 0/2/4（spread=2）＝cv._predict と同契約（0..k-1 連番）に反する → 保存時に止める。
    proj = make_project()
    est = _fit_multiclass(spread=2)
    with pytest.raises(ValueError, match="連番"):
        model_store.save_model(proj.root, est, name="onnx-bad", work="E-0001", format="onnx")


def test_regression_roundtrip(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    est = _fit_regression()
    model_store.save_model(proj.root, est, name="onnx-reg", work="E-0001", format="onnx")
    loaded, _ = model_store.load_model(proj.root, name="onnx-reg", work="E-0001")
    assert isinstance(loaded, OnnxRegressor)
    assert not hasattr(loaded, "predict_proba")  # cli の hasattr 分岐がそのまま「回帰＝value」経路になる

    new = data.generate_synthetic(n=10, seed=3)
    pred = loaded.predict(new)
    assert pred.shape == (10,)  # (n, 1) の ONNX 出力を (n,) に揃える（cv._predict の value 契約）
    np.testing.assert_allclose(pred, np.asarray(est.predict(new)), rtol=1e-3, atol=1e-3)
    np.testing.assert_allclose(cv._predict(loaded, new, "value"), pred)


def test_whole_model_without_to_numpy(make_project: Callable[..., Any]) -> None:
    # to_numpy 段が無い＝全体を変換（純 numpy 入力の sklearn 推定器も FORMATS 経由で可搬にできる）。
    rng = np.random.default_rng(0)
    x = rng.normal(size=(40, 3))
    y = (x[:, 0] + x[:, 1] > 0).astype(np.float64)
    clf = LogisticRegression(random_state=0, max_iter=1000).fit(x, y)
    proj = make_project()
    model_store.save_model(proj.root, clf, name="plain", work="E-0001", format="onnx")
    loaded, _ = model_store.load_model(proj.root, name="plain", work="E-0001")
    assert isinstance(loaded, OnnxClassifier)
    x_new = rng.normal(size=(8, 3)).astype(np.float32)
    np.testing.assert_allclose(loaded.predict_proba(x_new), clf.predict_proba(x_new), rtol=1e-3, atol=1e-4)


def test_lightgbm_tail_rejected(make_project: Callable[..., Any]) -> None:
    pytest.importorskip("lightgbm")  # optional extra（未導入なら対象の構成が作れない＝ISS ではない）
    df = data.generate_synthetic(n=60, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    est = build_estimator(_SPEC, build_model({"kind": "lightgbm"}, seed=0), seed=0)
    est.fit(df, y)
    proj = make_project()
    with pytest.raises(ValueError, match="lightgbm"):
        model_store.save_model(proj.root, est, name="lgbm", work="E-0001", format="onnx")


def test_sparse_tail_input_rejected(make_project: Callable[..., Any]) -> None:
    # tfidf の出力は疎（語彙 22・各行 3 語＝密度 3/22 < ColumnTransformer の疎閾値 0.3 の構成）＝tail 入力が疎。
    n = 20
    df = pl.DataFrame({"id": range(n), "text": [f"w{i} w{i + 1} common" for i in range(n)]})
    y = np.array([i % 2 for i in range(n)], dtype=np.float64)
    spec = {
        "features": [{"kind": "columns", "columns": ["text"]}],
        "encode": [{"kind": "tfidf", "columns": "text"}],
    }
    est = build_estimator(spec, build_model({"kind": "logreg"}, seed=0), seed=0)
    est.fit(df, y)
    proj = make_project()
    with pytest.raises(ValueError, match="疎"):
        model_store.save_model(proj.root, est, name="sparse", work="E-0001", format="onnx")


def test_broken_or_foreign_onnx_rejected(tmp_path: Path) -> None:
    # 壊れたファイル＝ValueError（onnxruntime の例外を明示型に揃える）。
    broken = tmp_path / "model.onnx"
    broken.write_bytes(b"not an onnx file")
    with pytest.raises(ValueError, match="読めない"):
        _onnx_load(broken)

    # 契約 metadata の無い正規 ONNX（harness 外の保存）＝ValueError（自己記述の無いファイルは包めない）。
    import onnx
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    rng = np.random.default_rng(0)
    x = rng.normal(size=(30, 2))
    y = (x[:, 0] > 0).astype(np.float64)
    clf = LogisticRegression(random_state=0, max_iter=1000).fit(x, y)
    proto = convert_sklearn(clf, initial_types=[("input", FloatTensorType([None, 2]))])
    foreign = tmp_path / "foreign.onnx"
    onnx.save_model(proto, str(foreign))
    with pytest.raises(ValueError, match=METADATA_KEY):
        _onnx_load(foreign)

    # source 不一致＝ValueError（他所の同名キーを黙って信じない）。
    fake = {
        "feature_names": [],
        "n_features": 2,
        "input_dtype": "float32",
        "prediction_kind": "proba",
        "classes": [0, 1],
        "source": "other",
    }
    onnx.helper.set_model_props(proto, {METADATA_KEY: json.dumps(fake)})
    other = tmp_path / "other.onnx"
    onnx.save_model(proto, str(other))
    with pytest.raises(ValueError, match="source"):
        _onnx_load(other)


def test_wrapper_input_validation(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    model_store.save_model(proj.root, _fit_binary(), name="onnx-in", work="E-0001", format="onnx")
    loaded, _ = model_store.load_model(proj.root, name="onnx-in", work="E-0001")
    assert isinstance(loaded, OnnxClassifier)
    # numpy は列数検査（契約 n_features=2 は _SPEC の columns 2 列から）。
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match=r"\(n, 2\)"):
        loaded.predict_proba(rng.normal(size=(4, 3)))
    # polars は feature_names の存在検査（不足列を名指しで止める）。
    with pytest.raises(ValueError, match="x2"):
        loaded.predict_proba(pl.DataFrame({"x1": [0.0, 1.0]}))
    # 正しい形はどちらの入口でも通る（float64 numpy は内部で float32 化）。
    assert loaded.predict_proba(rng.normal(size=(4, 2))).shape == (4, 2)


_INPUT_SCHEMA = {
    "id": "predict_input",
    "description": "バッチ予測の入力（to_numpy 境界の特徴量列そのもの）",
    "layer": "raw",
    "scope": "project",
    "primary_key": ["id"],
    "columns": [
        {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
        {"name": "x1", "dtype": "Float64", "nullable": False},
        {"name": "x2", "dtype": "Float64", "nullable": False},
    ],
}


@pytest.mark.e2e
def test_data_predict_with_onnx_champion(make_project: Callable[..., Any]) -> None:
    # e2e：onnx champion＋特徴量テーブルで `data predict` が無改修で通る（ラッパの cv._predict 互換の一巡）。
    proj = make_project()
    record = model_store.save_model(
        proj.root, _fit_binary(), name="onnx-champ", work="E-0001", format="onnx", metrics={"roc_auc": 0.9}
    )
    model_store.promote_model(
        proj.root,
        work="E-0001",
        name="onnx-champ",
        version=record.version,
        thresholds={"roc_auc": 0.8},
        primary="roc_auc",
    )
    proj.add_schema(_INPUT_SCHEMA)
    store.save(proj.root, data.generate_synthetic(n=8, seed=1).select("id", "x1", "x2"), "predict_input")

    _data_predict(work="E-0001", name="onnx-champ", table="predict_input", root=proj.root)

    out = next(d for d in (proj.root / "artifacts" / "predictions" / "onnx-champ").iterdir() if d.is_dir())
    result = pl.read_parquet(out / "predictions.parquet")
    assert result.height == 8  # 入力テーブルの行数
    pred = result["prediction"].to_numpy()
    assert np.all((pred >= 0.0) & (pred <= 1.0))  # 陽性確率の性質
    manifest = storage.read_manifest(out / "manifest.yaml")
    assert manifest["prediction_kind"] == "proba"  # 二値＝陽性確率 1 列の契約が来歴に残る
