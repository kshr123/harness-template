"""配信の実行時部品：champion 解決・予測・来歴つき JSONL 予測ログ（prediction_log の翻案）。

app.py（FastAPI）と cli.py（uvicorn 起動）が共有する土台。fastapi はここから import しない
（profile 経路の軽 import を壊さない）。polars/numpy/sklearn は関数内で遅延取り込みする。

JSONL 予測ログの行スキーマ（キー・型）は PREDICTION_LOG_FIELDS が正本（docs/serve.md に同じ契約を明記）。
後続の監視（data monitor・T-0087）はこの契約だけに依存する（勝手にキーを増減・改名しない）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

# 中核へ移設（T-0091）。`as` 付きで明示的に再輸出する＝serve の呼び手（app.py・テスト・
# docs/serve.md）は従来どおり `runtime.input_fingerprint(features)` で再計算できる（指紋の値も不変）。
from harness.fingerprint import input_fingerprint as input_fingerprint

if TYPE_CHECKING:  # 型だけ。実行時は関数内の遅延 import（このモジュールの取り込みを軽く保つ）
    import numpy as np
    import polars as pl
    from numpy.typing import NDArray

    from harness.ds.models import ModelRecord

# 予測 JSONL の行スキーマ（キー→型と意味）。1 行＝1 予測行。この辞書のキー集合と各行のキー集合は一致する
# （build_log_rows が検査する）。変更は契約の変更＝docs/serve.md と消費側（data monitor）を同時に直すこと。
PREDICTION_LOG_FIELDS: dict[str, str] = {
    "time": "str（ISO 8601・UTC。同じリクエストの行は同じ値）",
    "request_id": "str（uuid4 hex。同じリクエストの行は同じ値）",
    "row": "int（リクエスト内の行番号。0 始まり）",
    "model": "dict（work: str・name: str・version: str・fingerprint: str＝manifest と同じ来歴）",
    "prediction_kind": "str（proba＝二値の陽性確率 | multiclass_proba＝クラス数ぶんの確率 | value＝回帰の値）",
    "input_fingerprint": "str（features の正準 JSON の sha256。input_fingerprint(features) で再計算できる）",
    "features": "dict（列名→入力値。受信した record そのまま）",
    "prediction": "float（proba/value）| list[float]（multiclass_proba＝クラス 0..k-1 の確率）",
    # T-0113 で後方互換追加：常に付与（shadow 未設定でも "primary"）＝読み手は role の有無で場合分けしない。
    "role": 'str（"primary"＝応答を返した champion | "shadow"＝並走した shadow 版。同じ入力は同じ input_fingerprint）',
}


def load_champion(root: Path, *, work: str, name: str, version: str | None = None) -> tuple[object, ModelRecord]:
    """配信するモデルを解決して読む。version=None は現 champion（無ければ明示エラー＝黙って空で立たない）。"""
    from harness.ds import models as model_store

    if version is None:
        champ = model_store.champion(root, work=work, name=name)
        if champ is None:
            raise FileNotFoundError(
                f"{work}/{name}: champion が無い（先に promote_model で昇格するか version= で版を明示する）"
            )
        version = champ.version
    return model_store.load_model(root, name=name, work=work, version=version)


def current_champion_version(root: Path, *, work: str, name: str) -> str | None:
    """現 champion の版だけを返す（モデル本体は読まない＝/health の軽い突合用）。昇格が無ければ None。

    version 指定なしで起動した配信が、走行中に起きた昇格・切り戻しに気づくため（app.py の /health）。
    実体解決の徹底 fail-closed（異物 yaml があれば ValueError 等）は champion 解決の規則をそのまま共有する。
    """
    from harness.ds import models as model_store

    champ = model_store.champion(root, work=work, name=name)
    return None if champ is None else champ.version


def prediction_kind_of(model: object) -> str:
    """モデルの予測の種類（proba | multiclass_proba | value）。/metadata が起動時に確定して見せる。

    分類（predict_proba あり）は classes_ の数で二値/多クラスを分ける（predict_frame の出力形と同じ規則）。
    回帰（predict_proba なし）は value。
    """
    if not hasattr(model, "predict_proba"):
        return "value"
    classes = getattr(model, "classes_", None)
    if classes is not None and len(classes) > 2:
        return "multiclass_proba"
    return "proba"


def predict_frame(model: object, df: pl.DataFrame) -> tuple[NDArray[np.float64], str]:
    """df への予測と prediction_kind。`data predict`（ds/cli.py）の cv._predict 分岐と同じ規則の関数化。

    二値分類＝陽性（ラベル 1）の確率 1 列（"proba"）・多クラス＝(n, n_classes) の確率（"multiclass_proba"）・
    回帰＝値（"value"）。列の意味の検査（陽性列の解決・多クラスのラベル 0..k-1）は cv._predict が担う。
    """
    import numpy as np

    from harness.ds import cv

    if hasattr(model, "predict_proba"):
        proba = np.asarray(cv._predict(model, df, "proba"), dtype=np.float64)
        if proba.ndim == 1:  # 二値＝陽性（ラベル 1）確率の 1 列
            return proba, "proba"
        return proba, "multiclass_proba"  # 多クラス＝クラス数ぶんの確率列（陽性 1 列に潰さない）
    return np.asarray(cv._predict(model, df, "value"), dtype=np.float64), "value"


def log_path(root: Path, *, name: str, log_dir: Path | None = None, when: datetime | None = None) -> Path:
    """予測 JSONL の置き場。既定 `artifacts/serve/predictions/<name>/<YYYYMMDD>.jsonl`（UTC の日付で 1 ファイル）。

    log_dir を渡すと `<log_dir>/<YYYYMMDD>.jsonl`（モデル名のディレクトリを掘らない＝呼び手が置き場を決める）。
    """
    stamp = (when if when is not None else datetime.now(UTC)).strftime("%Y%m%d")
    base = log_dir if log_dir is not None else root / "artifacts" / "serve" / "predictions" / name
    return base / f"{stamp}.jsonl"


def build_log_rows(
    *,
    record: ModelRecord,
    prediction_kind: str,
    features_rows: Sequence[Mapping[str, Any]],
    predictions: object,
    request_id: str,
    time: str,
    role: str = "primary",
) -> list[dict[str, Any]]:
    """予測 1 リクエスト分の JSONL 行（PREDICTION_LOG_FIELDS の契約どおり）を組み立てる。

    1 行＝1 予測行。prediction は proba/value なら float・multiclass_proba なら list[float]（クラス 0..k-1）。
    role は "primary"（既定＝応答を返す champion）| "shadow"（並走版・T-0113）。契約外の role・
    行の数と予測の数が合わない・キー集合が契約とずれる場合は失敗にする（黙って欠けたログを書かない）。
    """
    import numpy as np

    if role not in ("primary", "shadow"):
        raise ValueError(f'role は "primary" | "shadow"（契約）: {role!r}')
    preds = np.asarray(predictions, dtype=np.float64)
    if preds.shape[0] != len(features_rows):
        raise ValueError(f"予測 {preds.shape[0]} 件と入力 {len(features_rows)} 行が合わない")
    rows: list[dict[str, Any]] = []
    for i, features in enumerate(features_rows):
        prediction: float | list[float] = preds[i].tolist() if preds.ndim == 2 else float(preds[i])
        entry: dict[str, Any] = {
            "time": time,
            "request_id": request_id,
            "row": i,
            "model": {
                "work": record.work,
                "name": record.name,
                "version": record.version,
                "fingerprint": record.fingerprint,
            },
            "prediction_kind": prediction_kind,
            "input_fingerprint": input_fingerprint(features),
            "features": dict(features),
            "prediction": prediction,
            "role": role,
        }
        if entry.keys() != PREDICTION_LOG_FIELDS.keys():  # 契約からのドリフトをここで止める
            raise ValueError(f"ログ行のキーが契約とずれている: {sorted(entry)} != {sorted(PREDICTION_LOG_FIELDS)}")
        rows.append(entry)
    return rows


def append_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """JSONL に行を追記する（1 行＝1 JSON・UTF-8・非 ASCII 素通し）。親ディレクトリは無ければ作る。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
