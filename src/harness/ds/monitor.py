"""配信ログ（予測 JSONL）×学習基準テーブルの分布監視（`data monitor` の中身・純関数）。

serve は「ログを書く側」・ds は「読む側」。結合は JSONL の行スキーマ（正本は docs/serve.md・コード側の正は
serve/runtime.py の PREDICTION_LOG_FIELDS）**だけ**で、serve パッケージは import しない（プロファイル境界）。
計算は既存部品へ委譲する：psi はビン境界を基準（学習側）の分位からのみ作る＝リーク無し（eda.psi がそう
実装している・ここでは呼ぶだけ）。drift_auc も eda に委譲（adversarial validation）。

監視は**門番にしない**：壊れ行・スキーマ不一致は警告して読み飛ばす（監視が盲目になるより縮退）。
判定は band（psi の目安 0.1/0.25 の離散化）として人が読む数字で返し、exit code に載せない。
消費するキーだけを検証する（time/prediction_kind/features/prediction。使わないキーは見ない＝受け側は寛容に）。
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from numpy.typing import NDArray

from harness.ds import eda

# psi の目安（eda.psi の docstring と同じ 0.1 / 0.25）。表示のための離散化であって門番の閾値ではない。
PSI_WATCH = 0.1
PSI_ALERT = 0.25

# 予測の要約に使う分位（p05〜p95。基準側に対応物が無いので比較でなく要約）。
_QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)


def psi_band(value: float) -> str:
    """psi の目安を言葉にする（0.1 未満=安定・0.1〜0.25=要注意・0.25 以上=大変化）。"""
    if value < PSI_WATCH:
        return "安定"
    if value < PSI_ALERT:
        return "要注意"
    return "大変化"


@dataclass(frozen=True)
class ServedLog:
    """読めた配信ログ。features＝unnest 済みの配信入力・predictions＝予測値（kind ごとの要約に使う）。"""

    features: pl.DataFrame  # 1 行 = 1 予測行（JSONL の features struct を unnest したもの）
    prediction_kinds: list[str]  # 行ごとの prediction_kind（proba | multiclass_proba | value）
    predictions: list[Any]  # 行ごとの prediction（float または list[float]）
    n_skipped: int  # 読み飛ばした壊れ行の数（警告済み。--since で落ちた行は含まない）

    @property
    def n_rows(self) -> int:
        return len(self.predictions)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _contract_error(row: object) -> str | None:
    """monitor が消費するキーの契約違反を返す（違反なし＝None）。契約は docs/serve.md。"""
    if not isinstance(row, dict):
        return "行が dict でない"
    if not isinstance(row.get("features"), dict):
        return "features（dict）が無い"
    if not isinstance(row.get("time"), str):
        return "time（str）が無い"
    kind = row.get("prediction_kind")
    if not isinstance(kind, str):
        return "prediction_kind（str）が無い"
    prediction = row.get("prediction")
    if kind == "multiclass_proba":
        if not (isinstance(prediction, list) and prediction and all(_is_number(v) for v in prediction)):
            return "prediction が数の list でない（multiclass_proba）"
    elif not _is_number(prediction):
        return "prediction が数でない（proba/value）"
    return None


def read_prediction_logs(files: Sequence[Path], *, since: date | None = None) -> ServedLog:
    """予測 JSONL（docs/serve.md の行スキーマ）を読み、配信入力（features の unnest）と予測を集める。

    壊れ行（JSON でない・消費キーの欠け/型違い・features のキー集合が先頭の有効行と不一致・多クラスの
    確率の長さが揃わない）は**ファイルごとに 1 回警告して読み飛ばす**（門番にしない）。since を渡すと
    time（ISO 8601）の日付がその日以降の行だけ残す（境界日を含む。絞り込みは壊れ行に数えない）。
    """
    feature_rows: list[dict[str, Any]] = []
    kinds: list[str] = []
    predictions: list[Any] = []
    n_skipped = 0
    reference_keys: set[str] | None = None  # 先頭の有効行の features キー集合＝unnest の基準
    multiclass_len: int | None = None
    for path in files:
        bad = 0
        first_reason = ""

        def _skip(reason: str) -> None:
            nonlocal bad, first_reason
            bad += 1
            first_reason = first_reason or reason

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                _skip("JSON として読めない")
                continue
            reason = _contract_error(row)
            if reason is not None:
                _skip(reason)
                continue
            if since is not None:
                try:
                    at = datetime.fromisoformat(row["time"])
                except ValueError:
                    _skip("time が ISO 8601 でない")
                    continue
                if at.date() < since:
                    continue  # 期間外＝壊れ行ではない（警告しない）
            feats: dict[str, Any] = row["features"]
            if reference_keys is None:
                reference_keys = set(feats)
            elif set(feats) != reference_keys:
                _skip("features のキー集合が先頭行と不一致")
                continue
            prediction = row["prediction"]
            if row["prediction_kind"] == "multiclass_proba":
                if multiclass_len is None:
                    multiclass_len = len(prediction)
                elif len(prediction) != multiclass_len:
                    _skip("multiclass_proba の確率の長さが揃わない")
                    continue
            feature_rows.append(dict(feats))
            kinds.append(row["prediction_kind"])
            predictions.append(prediction)
        if bad:
            warnings.warn(
                f"{path}: 壊れ行 {bad} 行を読み飛ばした（最初の理由: {first_reason}。契約は docs/serve.md）",
                stacklevel=2,
            )
        n_skipped += bad
    if feature_rows:
        features = pl.from_dicts(feature_rows, infer_schema_length=None)
    else:
        features = pl.DataFrame()
    return ServedLog(features=features, prediction_kinds=kinds, predictions=predictions, n_skipped=n_skipped)


def _summary(values: NDArray[np.float64]) -> dict[str, Any]:
    quantiles = np.quantile(values, _QUANTILES)
    return {
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "quantiles": {f"p{int(q * 100):02d}": float(v) for q, v in zip(_QUANTILES, quantiles, strict=True)},
    }


def prediction_summary(served: ServedLog) -> list[dict[str, Any]]:
    """予測列の要約（prediction_kind ごとに 件数・平均・標準偏差・分位）。

    基準テーブルに予測の対応物は無いので比較（psi）でなく要約。multiclass_proba はクラス別
    （読み込みが長さを揃えている）。log の glob が複数モデルをまたぐと kind が混ざり得るため kind 別に出す。
    """
    out: list[dict[str, Any]] = []
    for kind in sorted(set(served.prediction_kinds)):
        values = [p for k, p in zip(served.prediction_kinds, served.predictions, strict=True) if k == kind]
        entry: dict[str, Any] = {"prediction_kind": kind, "n": len(values)}
        arr = np.asarray(values, dtype=np.float64)
        if kind == "multiclass_proba":
            entry["classes"] = [{"class": i, **_summary(arr[:, i])} for i in range(arr.shape[1])]
        else:
            entry.update(_summary(arr))
        out.append(entry)
    return out


@dataclass(frozen=True)
class MonitorReport:
    """監視表（data compare の CompareReport と同じ「正本→to_dict→YAML」の写像）。"""

    n_baseline: int
    n_served: int
    n_skipped: int
    psi: pl.DataFrame  # column, psi, band（band は psi_band の離散化）
    drift: dict[str, Any] | None  # --auc 時のみ（auc/fold_aucs/columns。計算不能なら None）
    prediction_summary: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "n_baseline": self.n_baseline,
            "n_served": self.n_served,
            "n_skipped": self.n_skipped,
            "psi": self.psi.to_dicts(),
        }
        if self.drift is not None:
            out["drift"] = self.drift
        out["prediction_summary"] = self.prediction_summary
        return out


def monitor(
    baseline: pl.DataFrame,
    served: ServedLog,
    *,
    columns: Sequence[str] | None = None,
    auc: bool = False,
    seed: int = 0,
) -> MonitorReport:
    """学習基準×配信ログの監視表。共通列ごとの psi/band・（--auc）drift_auc・予測の要約。

    psi のビン境界は基準側の分位からのみ作られる（eda.psi の実装＝リーク無し・ここでは呼ぶだけ）。
    columns で対象列を絞れる（省略時は共通列すべて）。基準と配信で型の種類（数値/非数値）が違う列は
    警告して読み飛ばす（スキーマ不一致の縮退）。配信 0 行のときは psi/drift を出さない（0 行との比は
    数字として意味を持たない＝黙って大変化に見せない）。
    """
    common = [c for c in baseline.columns if c in served.features.columns]
    if columns is not None:
        common = [c for c in columns if c in common]

    psi_schema: dict[str, Any] = {"column": pl.String, "psi": pl.Float64, "band": pl.String}
    rows: list[dict[str, Any]] = []
    if served.n_rows == 0:
        warnings.warn("配信ログの行が 0（glob・--since・serve の稼働を確認）。psi は出さない", stacklevel=2)
    else:
        for c in common:
            if baseline.schema[c].is_numeric() != served.features.schema[c].is_numeric():
                warnings.warn(f"{c}: 基準と配信ログで型の種類（数値/非数値）が違うため読み飛ばした", stacklevel=2)
                continue
            value = eda.psi(baseline[c], served.features[c])
            rows.append({"column": c, "psi": value, "band": psi_band(value)})
    psi_table = pl.DataFrame(rows, schema=psi_schema) if rows else pl.DataFrame(schema=psi_schema)

    drift: dict[str, Any] | None = None
    if auc:
        numeric = [
            c
            for c in common
            if c != "id" and baseline.schema[c].is_numeric() and served.features.schema[c].is_numeric()
        ]
        if served.n_rows == 0 or not numeric:
            warnings.warn("--auc: 配信行または数値の共通列が無く drift_auc を計算できない", stacklevel=2)
        else:
            result = eda.drift_auc(baseline, served.features, columns=numeric, seed=seed)
            drift = {"auc": result.auc, "fold_aucs": result.fold_aucs, "columns": numeric}

    return MonitorReport(
        n_baseline=baseline.height,
        n_served=served.n_rows,
        n_skipped=served.n_skipped,
        psi=psi_table,
        drift=drift,
        prediction_summary=prediction_summary(served),
    )
