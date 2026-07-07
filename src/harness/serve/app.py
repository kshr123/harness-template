"""champion を配信する FastAPI アプリ（sync 配信・DEC-0013）。

fastapi・polars はこのモジュールの top で import する（profile.py/__init__.py からは辿られない＝
`import harness.serve` の軽 import を壊さない）。モデルは起動時（create_app）に読み込み、champion が
無ければ明示エラーで落とす（リクエスト時に初めて壊れる・黙って空で立つ、をしない）。
予測は 1 リクエストごとに来歴つき JSONL（runtime.PREDICTION_LOG_FIELDS の契約）へ追記する。

shadow 配信（T-0113）：環境変数 SERVE_SHADOW_NAME を設定したときだけ、同じ入力を shadow 版でも予測して
同じ JSONL に `role: "shadow"` の行を追記する（1 プロセス内の分岐・応答は常に primary のみ＝契約不変）。
未設定なら挙動は完全に従来どおり。shadow の予測失敗は応答を落とさない（警告ログのみ・shadow 行は書かない）。
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:  # 型だけ（実体は runtime.load_champion が返す）
    from harness.ds.models import ModelRecord

from harness.serve import runtime

logger = logging.getLogger(__name__)


class PredictRequest(BaseModel):
    """POST /predict の本文。records＝予測したい行の一覧（列名→値。全行同じ列であること）。"""

    records: list[dict[str, Any]]


def create_app(root: Path, *, work: str, name: str, version: str | None = None, log_dir: Path | None = None) -> FastAPI:
    """champion（version 指定時はその版）を載せた FastAPI アプリを作る。

    - GET /health … 生存確認（載っているモデルの work/name/version つき）。
    - GET /metadata … ModelRecord の構造化（来歴・指標）＋prediction_kind/feature_names。
    - POST /predict … `{"records": [{列名: 値}, ...]}` を予測。空 records・行ごとの列の食い違い・
      列不足や型不一致で予測できない入力は 422（黙って 200 にしない）。成功時は予測ごとに
      来歴つき JSONL（既定 artifacts/serve/predictions/<name>/<YYYYMMDD>.jsonl）へ 1 行追記する。

    shadow（任意・env のみ・docs/serve.md）：SERVE_SHADOW_NAME を設定すると shadow 版も起動時に読み込み
    （無ければ primary と同様に明示エラー＝設定ミスをリクエスト時まで持ち越さない）、/predict のたびに
    同じ入力で予測して `role: "shadow"` の行を primary と同じ JSONL に追記する。応答は primary のみ。
    SERVE_SHADOW_WORK（既定＝primary の work）・SERVE_SHADOW_VERSION（既定＝shadow 名の現 champion）で
    参照先を変えられる。
    """
    model, record = runtime.load_champion(root, work=work, name=name, version=version)
    prediction_kind = runtime.prediction_kind_of(model)
    shadow_model: object | None = None
    shadow_record: ModelRecord | None = None
    shadow_name = os.environ.get("SERVE_SHADOW_NAME")
    if shadow_name:  # 空文字は未設定扱い（有効化は明示の名前だけ）
        shadow_model, shadow_record = runtime.load_champion(
            root,
            work=os.environ.get("SERVE_SHADOW_WORK") or work,
            name=shadow_name,
            version=os.environ.get("SERVE_SHADOW_VERSION") or None,
        )
    app = FastAPI(title=f"harness serve {record.work}/{record.name}")
    # テスト・運用ツールが起動済みアプリから来歴を確認できるよう state にも持つ（handler は closure で参照）。
    app.state.model = model
    app.state.record = record
    app.state.prediction_kind = prediction_kind
    app.state.shadow_model = shadow_model
    app.state.shadow_record = shadow_record

    @app.get("/health")
    def health() -> dict[str, Any]:
        """生存確認。何が載っているか（モデルの版）まで返す＝取り違えの早期発見。"""
        return {
            "status": "ok",
            "model": {"work": record.work, "name": record.name, "version": record.version},
        }

    @app.get("/metadata")
    def metadata() -> dict[str, Any]:
        """載っているモデルの来歴（manifest の内容）＋予測の種類。path はローカル事情なので出さない。

        shadow が有効なときだけ `shadow`（work/name/version）を足す（後方互換のキー追加のみ）。
        """
        body: dict[str, Any] = {
            "work": record.work,
            "name": record.name,
            "version": record.version,
            "format": record.format,
            "fingerprint": record.fingerprint,
            "data_fingerprint": record.data_fingerprint,
            "feature_names": list(record.feature_names),
            "metrics": dict(record.metrics),
            "python": record.python,
            "dependencies": dict(record.dependencies),
            "created": record.created,
            "prediction_kind": prediction_kind,
        }
        if shadow_record is not None:
            body["shadow"] = {
                "work": shadow_record.work,
                "name": shadow_record.name,
                "version": shadow_record.version,
            }
        return body

    @app.post("/predict")
    def predict(request: PredictRequest) -> dict[str, Any]:
        """records を予測する。predictions の形は prediction_kind に応じる（docs/serve.md の契約）。"""
        records = request.records
        if not records:
            raise HTTPException(status_code=422, detail="records が空（予測する行を 1 行以上入れること）")
        keys = set(records[0])
        for i, rec in enumerate(records[1:], start=1):
            if set(rec) != keys:
                raise HTTPException(
                    status_code=422,
                    detail=f"行 {i} の列 {sorted(rec)} が行 0 の列 {sorted(keys)} と違う（全行同じ列にする）",
                )
        try:
            df = pl.DataFrame(records)
            predictions, kind = runtime.predict_frame(model, df)
        except Exception as exc:
            # モデルは起動時に検証済み＝この経路の失敗は入力起因（列不足・型不一致・値の形）とみなす。
            raise HTTPException(
                status_code=422, detail=f"この入力では予測できない（列不足・型不一致など）: {exc}"
            ) from exc
        request_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        rows = runtime.build_log_rows(
            record=record,
            prediction_kind=kind,
            features_rows=records,
            predictions=predictions,
            request_id=request_id,
            time=now.isoformat(),
            role="primary",
        )
        if shadow_model is not None and shadow_record is not None:
            # shadow はベストエフォート：失敗しても primary の応答・ログは守る（行は書かず警告だけ残す）。
            try:
                shadow_predictions, shadow_kind = runtime.predict_frame(shadow_model, df)
                rows += runtime.build_log_rows(
                    record=shadow_record,
                    prediction_kind=shadow_kind,
                    features_rows=records,
                    predictions=shadow_predictions,
                    request_id=request_id,
                    time=now.isoformat(),
                    role="shadow",
                )
            except Exception:
                logger.warning(
                    "shadow（%s/%s v%s）の予測に失敗（primary の応答は返す・shadow 行は書かない）",
                    shadow_record.work,
                    shadow_record.name,
                    shadow_record.version,
                    exc_info=True,
                )
        runtime.append_jsonl(runtime.log_path(root, name=record.name, log_dir=log_dir, when=now), rows)
        return {
            "predictions": predictions.tolist(),
            "prediction_kind": kind,
            "model": {"work": record.work, "name": record.name, "version": record.version},
            "request_id": request_id,
            "n": len(records),
        }

    return app
