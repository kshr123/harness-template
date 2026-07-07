"""shadow 配信（T-0113）のテスト：/predict の 1 プロセス内分岐・role: primary|shadow の JSONL 契約。

期待値はテストデータの構成から導く：primary/shadow 各行の prediction は、それぞれの学習済み Pipeline への
cv._predict 直呼びと一致（写経でなく同値性）。JSONL の行数は「records の行数 ×（shadow 有効なら 2、
無効なら 1）」＝構成から導出。応答は常に primary のみ（呼び手の契約は不変）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

pytest.importorskip("fastapi")  # optional extra `serve`（ISS ではない）
pytest.importorskip("httpx")  # TestClient の実体（dev 依存）

from fastapi.testclient import TestClient  # noqa: E402
from sklearn.linear_model import LinearRegression, LogisticRegression  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402

from harness.ds import cv, data  # noqa: E402
from harness.ds import models as model_store  # noqa: E402
from harness.ds.features import Columns, FeaturePipeline  # noqa: E402
from harness.serve import runtime  # noqa: E402
from harness.serve.app import create_app  # noqa: E402

# 応答スキーマ（docs/serve.md の契約）。shadow の有無で 1 バイトも増減しないことをこの集合で固定する。
_RESPONSE_KEYS = {"predictions", "prediction_kind", "model", "request_id", "n"}


def _pipeline(model: Any) -> Pipeline:
    """特徴 x1/x2 だけを選ぶ最小の Pipeline（test_serve_app.py と同じ構成）。"""
    return Pipeline([("features", FeaturePipeline([("columns", Columns(["x1", "x2"]))])), ("model", model)])


def _fitted_binary(n: int = 60, seed: int = 0) -> Pipeline:
    """二値分類の学習済み Pipeline（primary 用。generate_synthetic は seed 決め打ち＝決定的）。"""
    df = data.generate_synthetic(n=n, seed=seed)
    est = _pipeline(LogisticRegression(random_state=0, max_iter=1000))
    est.fit(df, df["y"].to_numpy().astype(np.float64))
    return est


def _fitted_regression(n: int = 60, seed: int = 0) -> Pipeline:
    """回帰の学習済み Pipeline（shadow 用。y = 2*x1 - 3*x2 の線形則＝primary と種類ごと区別できる）。"""
    df = data.generate_synthetic(n=n, seed=seed)
    y = 2.0 * df["x1"].to_numpy() - 3.0 * df["x2"].to_numpy()
    est = _pipeline(LinearRegression())
    est.fit(df, y)
    return est


def _save_and_promote(root: Path, est: Pipeline, *, name: str) -> Any:
    """モデルを 1 版保存して昇格する（champion 1 つの最小構成）。record を返す。"""
    record = model_store.save_model(root, est, name=name, work="E-0001", metrics={"rmse": 0.5})
    model_store.promote_model(
        root, work="E-0001", name=name, version=record.version, thresholds={"rmse": 1.0}, primary="rmse"
    )
    return record


def _records(n: int, seed: int) -> list[dict[str, Any]]:
    """予測リクエストの行（x1/x2 のみ＝推論入力）。"""
    return data.generate_synthetic(n=n, seed=seed).select("x1", "x2").to_dicts()


def _log_lines(root: Path, name: str) -> list[dict[str, Any]]:
    """既定の置き場（artifacts/serve/predictions/<primary 名>）の JSONL を全部読む。"""
    files = sorted((root / "artifacts" / "serve" / "predictions" / name).glob("*.jsonl"))
    assert len(files) == 1  # 同じ日（UTC）の追記は 1 ファイル（shadow 行も primary と同じファイル）
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


@pytest.mark.integration
def test_predict_logs_primary_and_shadow_roles(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """shadow 設定時：/predict 1 回で JSONL がちょうど 2 行（role={primary, shadow}）・応答は primary のみ。"""
    proj = make_project()
    primary_est = _fitted_binary()
    shadow_est = _fitted_regression()
    primary_record = _save_and_promote(proj.root, primary_est, name="baseline")
    shadow_record = _save_and_promote(proj.root, shadow_est, name="challenger")
    monkeypatch.setenv("SERVE_SHADOW_NAME", "challenger")  # 有効化は env のみ（work は primary と同じが既定）
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))

    # /metadata は shadow モデル名を含む（後方互換のキー追加のみ）。
    meta = client.get("/metadata").json()
    assert meta["shadow"] == {"work": "E-0001", "name": "challenger", "version": shadow_record.version}

    records = _records(1, seed=1)
    resp = client.post("/predict", json={"records": records})
    assert resp.status_code == 200
    body = resp.json()
    # 応答は primary の結果のみ・スキーマ不変（shadow が入り込まない）。
    assert set(body) == _RESPONSE_KEYS
    import polars as pl

    expected_primary = np.asarray(cv._predict(primary_est, pl.DataFrame(records), "proba"))
    expected_shadow = np.asarray(cv._predict(shadow_est, pl.DataFrame(records), "value"))
    assert np.allclose(np.asarray(body["predictions"]), expected_primary)
    assert body["model"] == {"work": "E-0001", "name": "baseline", "version": primary_record.version}

    lines = _log_lines(proj.root, "baseline")
    assert len(lines) == 2  # 1 リクエスト 1 行 × {primary, shadow} ＝ 2 行
    by_role = {entry["role"]: entry for entry in lines}
    assert set(by_role) == {"primary", "shadow"}
    for entry in lines:
        assert set(entry) == set(runtime.PREDICTION_LOG_FIELDS)  # 契約どおりのキー（両 role 共通）
        assert entry["request_id"] == body["request_id"]  # 同じリクエストの行は同じ request_id
    # 同一入力の突き合わせ＝両行の input_fingerprint が一致し、features から再計算できる。
    assert by_role["primary"]["input_fingerprint"] == by_role["shadow"]["input_fingerprint"]
    assert by_role["primary"]["input_fingerprint"] == runtime.input_fingerprint(records[0])
    # 各行の prediction・来歴は、それぞれのモデルの構成から導ける。
    assert np.isclose(by_role["primary"]["prediction"], expected_primary[0])
    assert by_role["primary"]["prediction_kind"] == "proba"
    assert by_role["primary"]["model"]["name"] == "baseline"
    assert np.isclose(by_role["shadow"]["prediction"], expected_shadow[0])
    assert by_role["shadow"]["prediction_kind"] == "value"
    assert by_role["shadow"]["model"] == {
        "work": "E-0001",
        "name": "challenger",
        "version": shadow_record.version,
        "fingerprint": shadow_record.fingerprint,
    }


@pytest.mark.integration
def test_no_shadow_env_behaves_as_before(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """env 未設定＝従来どおり：1 行のみ・role は primary・応答スキーマも従来と同一（後方互換の実証）。"""
    monkeypatch.delenv("SERVE_SHADOW_NAME", raising=False)
    proj = make_project()
    est = _fitted_binary()
    _save_and_promote(proj.root, est, name="baseline")
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    assert "shadow" not in client.get("/metadata").json()  # 無効時は /metadata にも現れない（完全に従来）

    records = _records(2, seed=2)
    resp = client.post("/predict", json={"records": records})
    assert resp.status_code == 200
    assert set(resp.json()) == _RESPONSE_KEYS  # 応答スキーマは従来と同一

    lines = _log_lines(proj.root, "baseline")
    assert len(lines) == len(records)  # shadow 無し＝1 予測行につき 1 行のまま
    for entry in lines:
        assert entry["role"] == "primary"  # role は常時付与（既定 primary）＝読み手は場合分け不要
        assert set(entry) == set(runtime.PREDICTION_LOG_FIELDS)


@pytest.mark.unit
def test_shadow_failure_does_not_break_response(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """shadow の predict が例外でも HTTP 200・primary の結果が返る（shadow はベストエフォート）。"""
    proj = make_project()
    primary_est = _fitted_binary()
    _save_and_promote(proj.root, primary_est, name="baseline")
    _save_and_promote(proj.root, _fitted_regression(), name="challenger")
    monkeypatch.setenv("SERVE_SHADOW_NAME", "challenger")
    app = create_app(proj.root, work="E-0001", name="baseline")
    client = TestClient(app)

    real_predict_frame = runtime.predict_frame

    def _boom(model: object, df: Any) -> Any:
        if model is app.state.shadow_model:  # shadow だけ壊す（primary の経路は本物のまま）
            raise RuntimeError("shadow が壊れた（テスト用）")
        return real_predict_frame(model, df)

    monkeypatch.setattr(runtime, "predict_frame", _boom)
    records = _records(1, seed=3)
    resp = client.post("/predict", json={"records": records})
    assert resp.status_code == 200  # primary の応答は落ちない
    import polars as pl

    expected = np.asarray(cv._predict(primary_est, pl.DataFrame(records), "proba"))
    assert np.allclose(np.asarray(resp.json()["predictions"]), expected)

    lines = _log_lines(proj.root, "baseline")
    assert len(lines) == 1  # 失敗した shadow の行は書かない（docs/serve.md に明記の方針）
    assert lines[0]["role"] == "primary"


@pytest.mark.unit
def test_build_log_rows_rejects_unknown_role() -> None:
    """契約外の role は ValueError（role 値検証の分岐を固定＝canary 等の混入を静かに許さない）。"""
    with pytest.raises(ValueError, match="role"):
        runtime.build_log_rows(
            record=cast(Any, None),  # role 検証が最初に走るので record は参照されない
            prediction_kind="value",
            features_rows=[{"x1": 1.0, "x2": 2.0}],
            predictions=[0.5],
            request_id="r-0",
            time="2026-07-07T00:00:00Z",
            role="canary",
        )
