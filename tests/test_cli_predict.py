"""data predict（バッチ推論入口）のテスト。champion 解決→予測→parquet＋sidecar yaml の来歴。

期待値はテストデータの構成から導く：行数＝入力テーブルの行数、指紋＝save の返り値や書かれた実体の
sha256（storage.fingerprint）、prediction の範囲＝predict_proba の性質（確率∈[0,1]）。実装出力の写経はしない。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import polars as pl
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness import storage
from harness.ds import data, store
from harness.ds import models as model_store
from harness.ds.cli import _data_predict
from harness.ds.features import Columns, FeaturePipeline

pytestmark = pytest.mark.integration

# 入力テーブルの定義（モデルの特徴 x1/x2 と行の鍵 id）。raw 層＝再書き込み制約なし。
_INPUT_SCHEMA = {
    "id": "predict_input",
    "description": "バッチ予測の入力",
    "layer": "raw",
    "scope": "project",
    "primary_key": ["id"],
    "columns": [
        {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
        {"name": "x1", "dtype": "Float64", "nullable": False},
        {"name": "x2", "dtype": "Float64", "nullable": False},
    ],
}


def _fitted_classifier() -> Pipeline:
    """小さな学習済み分類 Pipeline（generate_synthetic は seed 決め打ち＝決定的）。"""
    df = data.generate_synthetic(n=40, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    est = Pipeline(
        [
            ("features", FeaturePipeline([("columns", Columns(["x1", "x2"]))])),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )
    est.fit(df, y)
    return est


def _input_table(n: int, seed: int) -> pl.DataFrame:
    src = data.generate_synthetic(n=n, seed=seed)
    return src.select("id", "x1", "x2")  # 定義どおりの 3 列（目的変数は持たない＝推論入力）


def _setup_champion(proj: Any, *, n_input: int = 8) -> tuple[Any, str]:
    """champion 1 版＋入力テーブルを構成する。保存版の record と入力テーブルの指紋を返す。"""
    record = model_store.save_model(
        proj.root, _fitted_classifier(), name="baseline", work="E-0001", metrics={"roc_auc": 0.9}
    )
    model_store.promote_model(
        proj.root,
        work="E-0001",
        name="baseline",
        version=record.version,
        thresholds={"roc_auc": 0.8},
        primary="roc_auc",
    )
    proj.add_schema(_INPUT_SCHEMA)
    data_fp = store.save(proj.root, _input_table(n_input, seed=1), "predict_input")
    return record, data_fp


def test_predict_champion_writes_parquet_and_sidecar(make_project: Callable[..., Any]) -> None:
    # 一巡：champion 昇格→入力保存→predict（version 省略＝champion 解決・out 省略＝既定の置き場）。
    proj = make_project()
    record, data_fp = _setup_champion(proj, n_input=8)

    _data_predict(work="E-0001", name="baseline", table="predict_input", root=proj.root)

    base = proj.root / "artifacts" / "predictions" / "baseline"
    out_dirs = [d for d in base.iterdir() if d.is_dir()]
    assert len(out_dirs) == 1  # 1 回の実行＝時刻ディレクトリ 1 つ
    out = out_dirs[0]
    result = pl.read_parquet(out / "predictions.parquet")
    assert result.height == 8  # 入力テーブルの行数（構成から）
    assert "prediction" in result.columns
    # 入力列は保たれる（入力に予測列を足した DataFrame。列は定義の構成から）。
    assert {"id", "x1", "x2"} <= set(result.columns)

    manifest = storage.read_manifest(out / "manifest.yaml")
    assert manifest["model"] == {
        "work": "E-0001",
        "name": "baseline",
        "version": record.version,  # champion に解決された版＝昇格した版
        "fingerprint": record.fingerprint,  # 保存時の manifest と同じ指紋
    }
    assert manifest["input_table"] == "predict_input"
    assert manifest["data_fingerprint"] == data_fp  # store.save の返り値と一致
    assert manifest["n_rows"] == 8
    # 予測実体の指紋＝書かれた parquet の sha256（構成から再計算して照合）。
    assert manifest["prediction_fingerprint"] == storage.fingerprint(out / "predictions.parquet")
    assert manifest["created"]  # ISO 時刻（値は実行時刻なので存在だけ確かめる）


def test_predict_without_champion_raises(make_project: Callable[..., Any]) -> None:
    # 保存はあるが昇格が無い → version 省略は champion 不在で分かる ValueError。
    proj = make_project()
    model_store.save_model(proj.root, _fitted_classifier(), name="baseline", work="E-0001")
    proj.add_schema(_INPUT_SCHEMA)
    store.save(proj.root, _input_table(4, seed=1), "predict_input")
    with pytest.raises(ValueError, match="champion が無い"):
        _data_predict(work="E-0001", name="baseline", table="predict_input", root=proj.root)


def test_predict_classifier_outputs_positive_proba(make_project: Callable[..., Any], tmp_path: Any) -> None:
    # 分類 champion の prediction は陽性確率＝全行 [0,1]（predict_proba の性質から導く）。--out 明示の経路。
    proj = make_project()
    _setup_champion(proj, n_input=16)
    out = tmp_path / "preds"

    _data_predict(work="E-0001", name="baseline", table="predict_input", out=out, root=proj.root)

    result = pl.read_parquet(out / "predictions.parquet")
    pred = result["prediction"].to_numpy()
    assert pred.shape == (16,)  # 入力行数ぶんの 1 次元（陽性確率 1 列）
    assert np.all((pred >= 0.0) & (pred <= 1.0))
    assert (out / "manifest.yaml").is_file()  # --out 明示でも sidecar が同居する


def _fitted_multiclass() -> Pipeline:
    """3 クラス（x1 の3分位でラベル 0/1/2＝連番）の学習済み分類 Pipeline。"""
    df = data.generate_synthetic(n=60, seed=0)
    x1 = df["x1"].to_numpy()
    y = np.digitize(x1, np.quantile(x1, [1 / 3, 2 / 3])).astype(np.float64)  # 0/1/2（連番＝多クラス契約）
    est = Pipeline(
        [
            ("features", FeaturePipeline([("columns", Columns(["x1", "x2"]))])),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )
    est.fit(df, y)
    return est


def test_predict_multiclass_writes_per_class_columns(make_project: Callable[..., Any]) -> None:
    # 多クラス champion は陽性 1 列に潰さず proba_0/1/2（各∈[0,1]・行和 1）＝黙って Array 列にしない。
    proj = make_project()
    record = model_store.save_model(proj.root, _fitted_multiclass(), name="mc", work="E-0001", metrics={"roc_auc": 0.9})
    model_store.promote_model(
        proj.root, work="E-0001", name="mc", version=record.version, thresholds={"roc_auc": 0.8}, primary="roc_auc"
    )
    proj.add_schema(_INPUT_SCHEMA)
    store.save(proj.root, _input_table(8, seed=1), "predict_input")

    _data_predict(work="E-0001", name="mc", table="predict_input", root=proj.root)

    out = next(d for d in (proj.root / "artifacts" / "predictions" / "mc").iterdir() if d.is_dir())
    result = pl.read_parquet(out / "predictions.parquet")
    assert {"proba_0", "proba_1", "proba_2"} <= set(result.columns)  # クラス数ぶんの列
    assert "prediction" not in result.columns  # 陽性 1 列には潰さない
    probs = result.select("proba_0", "proba_1", "proba_2").to_numpy()
    assert np.all((probs >= 0.0) & (probs <= 1.0))
    np.testing.assert_allclose(probs.sum(axis=1), 1.0)  # 各行は確率分布
    manifest = storage.read_manifest(out / "manifest.yaml")
    assert manifest["prediction_kind"] == "multiclass_proba"  # 消費側が意味を取り違えないよう来歴に残す


_SCHEMA_WITH_PRED = {
    "id": "with_pred",
    "description": "既に prediction 列を持つ入力（衝突検査用）",
    "layer": "raw",
    "scope": "project",
    "primary_key": ["id"],
    "columns": [
        {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
        {"name": "x1", "dtype": "Float64", "nullable": False},
        {"name": "x2", "dtype": "Float64", "nullable": False},
        {"name": "prediction", "dtype": "Float64", "nullable": False},
    ],
}


def test_predict_rejects_prediction_column_collision(make_project: Callable[..., Any]) -> None:
    # 入力に既に prediction 列があると、黙って上書きせず ValueError（入力が消えると気づけないため中止）。
    proj = make_project()
    _setup_champion(proj, n_input=8)  # baseline champion（二値＝prediction 列を出す）
    proj.add_schema(_SCHEMA_WITH_PRED)
    tbl = _input_table(8, seed=1).with_columns(pl.lit(0.0).alias("prediction"))
    store.save(proj.root, tbl, "with_pred")
    with pytest.raises(ValueError, match="衝突"):
        _data_predict(work="E-0001", name="baseline", table="with_pred", root=proj.root)
