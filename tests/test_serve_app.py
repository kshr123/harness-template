"""serve プロファイルの FastAPI アプリのテスト（TestClient・ネットワーク無し・fastapi は importorskip）。

期待値はテストデータの構成から導く：/predict の値は同じ df への cv._predict 直呼びと一致（写経でなく
同値性）、確率は [0,1]・多クラスの行和は 1（predict_proba の性質）、JSONL の行数は送った records の数、
input_fingerprint は runtime.input_fingerprint での再計算と一致。実装出力の固定値コピーはしない。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
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

pytestmark = pytest.mark.integration


def test_input_fingerprint_is_sha256_of_canonical_json() -> None:
    """input_fingerprint のアルゴリズムを独立に固定する（正準 JSON＝キー昇順・区切り最小の sha256）。

    再計算一致だけだと関数が黙って変わっても緑のまま。ここでは正準 JSON の定義（docs/serve.md）を
    テスト側に書き下してハッシュを独立に計算し、runtime と一致することを固定する（sort_keys を外す・
    区切りを変える等のアルゴリズム変異を赤にするアンカー）。後続 monitor が過去ログと突き合わせる正本。
    """
    import hashlib

    features = {"x2": 2.0, "x1": 1.0}  # あえてキー順を逆に＝正準化（sort_keys）で並べ替わることを確かめる
    canonical = json.dumps(features, sort_keys=True, separators=(",", ":"))
    assert canonical == '{"x1":1.0,"x2":2.0}'  # 正準 JSON の定義（キー昇順・区切り最小）をここで固定
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert runtime.input_fingerprint(features) == expected


def _pipeline(model: Any) -> Pipeline:
    """特徴 x1/x2 だけを選ぶ最小の Pipeline（学習と配信で同じ物が動く前提の器）。"""
    return Pipeline([("features", FeaturePipeline([("columns", Columns(["x1", "x2"]))])), ("model", model)])


def _fitted_binary(n: int = 60, seed: int = 0) -> Pipeline:
    """二値分類の学習済み Pipeline（generate_synthetic は seed 決め打ち＝決定的）。"""
    df = data.generate_synthetic(n=n, seed=seed)
    est = _pipeline(LogisticRegression(random_state=0, max_iter=1000))
    est.fit(df, df["y"].to_numpy().astype(np.float64))
    return est


def _fitted_multiclass(n: int = 90, seed: int = 0) -> Pipeline:
    """3 クラス分類の学習済み Pipeline。ラベルは x1 の 3 区分（-0.4/0.4 区切り）＝0..2 の連番。"""
    df = data.generate_synthetic(n=n, seed=seed)
    y3 = np.digitize(df["x1"].to_numpy(), [-0.4, 0.4]).astype(np.int64)
    assert set(y3) == {0, 1, 2}  # 3 クラス全部が現れる規模で作る（cv._predict の連番前提）
    est = _pipeline(LogisticRegression(random_state=0, max_iter=1000))
    est.fit(df, y3)
    return est


def _fitted_regression(n: int = 60, seed: int = 0) -> Pipeline:
    """回帰の学習済み Pipeline。y = 2*x1 - 3*x2（構成から予測値を説明できる線形則）。"""
    df = data.generate_synthetic(n=n, seed=seed)
    y = 2.0 * df["x1"].to_numpy() - 3.0 * df["x2"].to_numpy()
    est = _pipeline(LinearRegression())
    est.fit(df, y)
    return est


def _save_and_promote(root: Path, est: Pipeline, *, name: str = "baseline") -> Any:
    """モデルを 1 版保存して昇格する（champion 1 つの最小構成）。record を返す。"""
    record = model_store.save_model(root, est, name=name, work="E-0001", metrics={"rmse": 0.5})
    model_store.promote_model(
        root, work="E-0001", name=name, version=record.version, thresholds={"rmse": 1.0}, primary="rmse"
    )
    return record


def _records(n: int, seed: int) -> list[dict[str, Any]]:
    """予測リクエストの行（x1/x2 のみ＝推論入力）。"""
    df = data.generate_synthetic(n=n, seed=seed).select("x1", "x2")
    return df.to_dicts()


def test_health_returns_status_and_model_version(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    record = _save_and_promote(proj.root, _fitted_binary())
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model"] == {"work": "E-0001", "name": "baseline", "version": record.version}


def test_health_reports_stale_503_when_champion_changed_under_running_server(
    make_project: Callable[..., Any],
) -> None:
    # version 指定なしで起動＝現 champion を配る。起動後に別版が champion になったら、走行中のサーバは
    # 古い版を配り続ける。/health はディスクの champion と載っている版を突き合わせ、食い違えば 503+stale。
    # 期待値は構成から導ける：起動時 champion=v1、その後 v2 を昇格→現 champion=v2≠載っている v1。
    proj = make_project()
    v1 = _save_and_promote(proj.root, _fitted_binary(seed=0))
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    assert client.get("/health").status_code == 200  # 起動直後は一致＝ok

    # 走行中に別版を champion へ（rmse をはっきり改善させて昇格を通す）。
    v2 = model_store.save_model(
        proj.root, _fitted_binary(seed=1), name="baseline", work="E-0001", metrics={"rmse": 0.1}
    )
    model_store.promote_model(
        proj.root, work="E-0001", name="baseline", version=v2.version, thresholds={"rmse": 1.0}, primary="rmse"
    )
    assert v2.version != v1.version

    resp = client.get("/health")
    assert resp.status_code == 503  # k8s readinessProbe / compose healthcheck がこの配信を自動で外せる
    body = resp.json()
    assert body["status"] == "stale"
    assert body["model"]["version"] == v1.version  # 載っている（古い）版
    assert body["champion"] == v2.version  # ディスク上の現 champion


def test_health_pinned_version_does_not_flag_stale(make_project: Callable[..., Any]) -> None:
    # version を明示して起動＝運用が意図して版を固定。後から別版が champion になっても stale 扱いにしない
    # （固定は意図した状態なので、champion との食い違いを異常と見なさない）。
    proj = make_project()
    v1 = _save_and_promote(proj.root, _fitted_binary(seed=0))
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline", version=v1.version))
    v2 = model_store.save_model(
        proj.root, _fitted_binary(seed=1), name="baseline", work="E-0001", metrics={"rmse": 0.1}
    )
    model_store.promote_model(
        proj.root, work="E-0001", name="baseline", version=v2.version, thresholds={"rmse": 1.0}, primary="rmse"
    )
    assert client.get("/health").status_code == 200  # 固定起動は突合しない


def test_metadata_matches_saved_record(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    record = _save_and_promote(proj.root, _fitted_binary())
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    body = client.get("/metadata").json()
    # manifest（record）と一致（構造化して返す）。feature_names は Columns(["x1","x2"]) の構成どおり。
    assert body["work"] == record.work and body["name"] == record.name
    assert body["version"] == record.version
    assert body["format"] == record.format
    assert body["fingerprint"] == record.fingerprint
    assert body["feature_names"] == list(record.feature_names) == ["x1", "x2"]
    assert body["metrics"] == record.metrics
    assert body["prediction_kind"] == "proba"  # 二値分類＝陽性確率


def test_predict_binary_matches_direct_cv_predict(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    est = _fitted_binary()
    record = _save_and_promote(proj.root, est)
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    records = _records(5, seed=1)
    resp = client.post("/predict", json={"records": records})
    assert resp.status_code == 200
    body = resp.json()
    # 同じ df への cv._predict 直呼びと一致（保存→load は pickle 往復＝同じモデル）。
    expected = np.asarray(cv._predict(est, pl.DataFrame(records), "proba"))
    got = np.asarray(body["predictions"])
    assert got.shape == (5,)
    assert np.allclose(got, expected)
    assert np.all((got >= 0.0) & (got <= 1.0))  # 確率の性質
    assert body["prediction_kind"] == "proba"
    assert body["model"]["version"] == record.version
    assert body["n"] == 5
    assert isinstance(body["request_id"], str) and body["request_id"]


def test_predict_multiclass_returns_proba_per_class(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    est = _fitted_multiclass()
    _save_and_promote(proj.root, est, name="triple")
    app = create_app(proj.root, work="E-0001", name="triple")
    client = TestClient(app)
    assert client.get("/metadata").json()["prediction_kind"] == "multiclass_proba"
    records = _records(4, seed=2)
    body = client.post("/predict", json={"records": records}).json()
    got = np.asarray(body["predictions"])
    assert got.shape == (4, 3)  # クラス数（3 区分の構成）ぶんの確率列＝陽性 1 列に潰さない
    assert np.allclose(got.sum(axis=1), 1.0)  # 確率の行和は 1
    assert np.allclose(got, np.asarray(cv._predict(est, pl.DataFrame(records), "proba")))
    assert body["prediction_kind"] == "multiclass_proba"


def test_predict_regression_returns_values(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    est = _fitted_regression()
    _save_and_promote(proj.root, est, name="reg")
    client = TestClient(create_app(proj.root, work="E-0001", name="reg"))
    records = _records(6, seed=3)
    body = client.post("/predict", json={"records": records}).json()
    got = np.asarray(body["predictions"])
    assert got.shape == (6,)
    assert np.allclose(got, np.asarray(cv._predict(est, pl.DataFrame(records), "value")))
    assert body["prediction_kind"] == "value"


def test_predict_empty_records_is_422(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    _save_and_promote(proj.root, _fitted_binary())
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    assert client.post("/predict", json={"records": []}).status_code == 422


def test_predict_missing_column_is_422(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    _save_and_promote(proj.root, _fitted_binary())
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    # モデルは x1/x2 を使う（構成）。x2 の欠けた行は予測できない＝422（黙って 200 にしない）。
    assert client.post("/predict", json={"records": [{"x1": 0.1}]}).status_code == 422


def test_predict_mismatched_keys_across_rows_is_422(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    _save_and_promote(proj.root, _fitted_binary())
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    records = [{"x1": 0.1, "x2": 0.2}, {"x1": 0.3}]
    assert client.post("/predict", json={"records": records}).status_code == 422


def test_create_app_without_champion_raises(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    # 保存だけして昇格しない＝champion 不在。起動（create_app）で明示的に失敗する。
    record = model_store.save_model(proj.root, _fitted_binary(), name="baseline", work="E-0001")
    with pytest.raises(FileNotFoundError, match="champion"):
        create_app(proj.root, work="E-0001", name="baseline")
    # version を明示すれば昇格前の版でも出せる（緊急・検証用の入口）。
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline", version=record.version))
    assert client.get("/health").status_code == 200


def test_predictions_are_appended_as_jsonl_with_contract_keys(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    record = _save_and_promote(proj.root, _fitted_binary())
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline"))
    first = _records(3, seed=4)
    second = _records(2, seed=5)
    rid1 = client.post("/predict", json={"records": first}).json()["request_id"]
    rid2 = client.post("/predict", json={"records": second}).json()["request_id"]

    log_dir = proj.root / "artifacts" / "serve" / "predictions" / "baseline"  # 既定の置き場（契約）
    files = sorted(log_dir.glob("*.jsonl"))
    assert len(files) == 1  # 同じ日（UTC）の追記は 1 ファイル
    assert files[0].name == f"{datetime.now(UTC).strftime('%Y%m%d')}.jsonl"
    lines = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert len(lines) == len(first) + len(second)  # 1 行＝1 予測行
    for entry in lines:
        assert set(entry) == set(runtime.PREDICTION_LOG_FIELDS)  # 行スキーマ（契約）どおりのキー
        assert entry["input_fingerprint"] == runtime.input_fingerprint(entry["features"])  # 再計算一致
        assert entry["model"] == {
            "work": "E-0001",
            "name": "baseline",
            "version": record.version,
            "fingerprint": record.fingerprint,
        }
        assert entry["prediction_kind"] == "proba"
        assert 0.0 <= entry["prediction"] <= 1.0  # 二値＝陽性確率の float
    # リクエストごとに request_id が共通・row は 0 始まりの連番・features は送った record そのまま。
    assert [e["request_id"] for e in lines] == [rid1] * 3 + [rid2] * 2
    assert [e["row"] for e in lines] == [0, 1, 2, 0, 1]
    assert [e["features"] for e in lines[:3]] == first


def test_log_dir_overrides_default_location(make_project: Callable[..., Any], tmp_path: Path) -> None:
    proj = make_project()
    _save_and_promote(proj.root, _fitted_binary())
    custom = tmp_path / "custom-logs"
    client = TestClient(create_app(proj.root, work="E-0001", name="baseline", log_dir=custom))
    client.post("/predict", json={"records": _records(2, seed=6)})
    files = sorted(custom.glob("*.jsonl"))
    assert len(files) == 1
    assert len(files[0].read_text(encoding="utf-8").splitlines()) == 2
    assert not (proj.root / "artifacts").exists()  # 既定の置き場には書かない
