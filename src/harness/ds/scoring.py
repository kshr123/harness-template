"""配信予測×実績の答え合わせ（`data score` の中身・純関数）。

分布監視（`ds/monitor.py`）は「入力の分布がずれたか」の**代理**しか見ない：入力が安定したまま
現実の正解率だけが崩れた champion は、psi/drift では見えない。この不足を塞ぐのがこのモジュール＝
**後から届く実績（正解）と、配信時の予測を突き合わせて、実際に測った指標を出す**。

serve は「予測を書く側」・ds は「読む側」。結合は予測 JSONL の行スキーマ（正本は docs/serve.md・コード側の
正は serve/runtime.py の PREDICTION_LOG_FIELDS）**だけ**で、serve パッケージは import しない（プロファイル
境界）。突き合わせの鍵は `input_fingerprint`（features の正準 JSON の sha256）＝予測 1 行に必ず付く決定的な
指紋。実績テーブルは「この指紋 → 実際の正解」を持って後から来る（利用者が業務 id から結合して用意する）。

答え合わせは**門番にしない**（監視と同じ思想）：壊れ行は警告して読み飛ばす・実測指標と昇格時に約束した
指標との差は band（相対劣化の離散化）として人が読む数字で返し、exit code には載せない。指標の算出そのものは
`ds/eval` の evaluate 系（sklearn 素通し・METRICS レジストリ）へ委譲する（再発明しない）。

**保証しないこと（docs/ops.md に同じ宣言）**：実績が届かない案件（正解ラベルが決して来ない配信）では
この答え合わせは動かせない。劣化の band 閾値（DEGRADE_WATCH/ALERT）は表示のための既定であって、
「どれだけ悪化したら対処するか」は案件ごとの人の判断（門番でない）。
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from harness.ds import eval as ds_eval
from harness.ds.monitor import _contract_error
from harness.fingerprint import input_fingerprint

# 相対劣化の目安（表示のための離散化であって門番の閾値ではない。psi の 0.1/0.25 と同じ役どころ）。
DEGRADE_WATCH = 0.05
DEGRADE_ALERT = 0.10

# 予測の種類 → 評価の課題（eval の EvalTask）。答え合わせはログの kind から課題を導ける。
_KIND_TASK: dict[str, str] = {"proba": "binary", "multiclass_proba": "multiclass", "value": "regression"}


def _is_nan(value: object) -> bool:
    """float の NaN か（分類ラベルの int・str は NaN になりえない＝False）。"""
    return isinstance(value, float) and math.isnan(value)


def _prediction_has_nan(prediction: object) -> bool:
    """予測値（float または list[float]）に NaN が含まれるか（含む行は答え合わせに使えない＝読み飛ばす）。"""
    values = prediction if isinstance(prediction, list) else [prediction]
    return any(_is_nan(v) for v in values)


def degradation_band(relative_degradation: float | None) -> str:
    """相対劣化を言葉にする（0.05 未満=安定・0.05〜0.10=要注意・0.10 以上=大変化・基準なし=約束が無い）。"""
    if relative_degradation is None:
        return "基準なし"
    if relative_degradation < DEGRADE_WATCH:
        return "安定"
    if relative_degradation < DEGRADE_ALERT:
        return "要注意"
    return "大変化"


@dataclass(frozen=True)
class ScoredPredictions:
    """答え合わせに使う最小の列（input_fingerprint・予測値・種類）だけ取り出した配信ログ。"""

    input_fingerprints: list[str]
    predictions: list[Any]  # 行ごとの予測（float または list[float]＝multiclass_proba）
    prediction_kinds: list[str]  # 行ごとの prediction_kind（proba | multiclass_proba | value）
    n_skipped: int

    @property
    def n_rows(self) -> int:
        return len(self.predictions)


def read_scored_predictions(
    files: Sequence[Path], *, since: date | None = None, role: str = "primary", version: str | None = None
) -> ScoredPredictions:
    """予測 JSONL（docs/serve.md の契約）を読み、答え合わせに要る列（指紋・予測・種類）を集める。

    契約検査は `monitor._contract_error`（同じ行スキーマ）に加え、答え合わせが消費する `input_fingerprint`
    （str）を要求する。壊れ行（JSON でない・契約違反・指紋が無い/str でない）は**ファイルごとに 1 回警告して
    読み飛ばす**（門番にしない）。since は time（ISO 8601）の日付での絞り込み（境界日を含む）。role は
    "primary"（既定）| "shadow" | "all"（shadow 配信＝docs/serve.md。既定 primary＝並走行を除外）。
    version を渡すと model.version が一致する行だけ残す（champion の版に限定＝混在ログを取り違えない）。
    """
    import json
    from datetime import datetime

    if role not in ("primary", "shadow", "all"):
        raise ValueError(f'role は "primary" | "shadow" | "all"（契約は docs/serve.md）: {role!r}')

    fingerprints: list[str] = []
    predictions: list[Any] = []
    kinds: list[str] = []
    n_skipped = 0
    multiclass_len: int | None = None  # 多クラスの確率の長さの基準（揃わない行は読み飛ばす＝monitor と同じ）
    for path in files:
        bad = 0
        first_reason = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                first_reason = first_reason or "JSON として読めない"
                continue
            reason = _contract_error(row)
            if reason is None and not isinstance(row.get("input_fingerprint"), str):
                reason = "input_fingerprint（str）が無い"
            if reason is not None:
                bad += 1
                first_reason = first_reason or reason
                continue
            if role != "all" and row.get("role", "primary") != role:
                continue  # role 対象外＝壊れ行ではない（警告しない。無い旧ログ行は primary 扱い）
            if version is not None:
                model = row.get("model")
                if not isinstance(model, dict):
                    bad += 1  # 版で絞るのに model が dict でない＝壊れ行（黙って握り潰さず読み飛ばす）
                    first_reason = first_reason or "model（dict）が壊れている"
                    continue
                if model.get("version") != version:
                    continue  # 版が違う＝対象外（壊れ行ではない）
            if since is not None:
                try:
                    at = datetime.fromisoformat(row["time"])
                except ValueError:
                    bad += 1
                    first_reason = first_reason or "time が ISO 8601 でない"
                    continue
                if at.date() < since:
                    continue  # 期間外＝壊れ行ではない
            prediction = row["prediction"]
            if _prediction_has_nan(prediction):
                bad += 1  # NaN の予測は答え合わせに使えない＝壊れ行（sklearn で不透明に落ちる前に読み飛ばす）
                first_reason = first_reason or "prediction に NaN が含まれる"
                continue
            if row["prediction_kind"] == "multiclass_proba":
                if multiclass_len is None:
                    multiclass_len = len(prediction)
                elif len(prediction) != multiclass_len:
                    bad += 1  # 確率の長さが揃わない＝壊れ行（np.asarray で不透明に落ちる前に読み飛ばす）
                    first_reason = first_reason or "multiclass_proba の確率の長さが揃わない"
                    continue
            fingerprints.append(row["input_fingerprint"])
            predictions.append(prediction)
            kinds.append(row["prediction_kind"])
        if bad:
            warnings.warn(
                f"{path}: 壊れ行 {bad} 行を読み飛ばした（最初の理由: {first_reason}。契約は docs/serve.md）",
                stacklevel=2,
            )
        n_skipped += bad
    return ScoredPredictions(
        input_fingerprints=fingerprints, predictions=predictions, prediction_kinds=kinds, n_skipped=n_skipped
    )


@dataclass(frozen=True)
class MetricComparison:
    """指標 1 つの答え合わせ：実測値・昇格時に約束した値・差・相対劣化・band。"""

    metric: str
    realized: float
    promised: float | None  # 昇格時の manifest metrics（無い指標は None）
    delta: float | None  # realized - promised（promised が無ければ None）
    relative_degradation: float | None  # 悪化の割合（良化・同等 0.0／0 の約束から悪化は inf／約束無しは None）
    band: str


@dataclass(frozen=True)
class AnswerCheckReport:
    """答え合わせの表（monitor の MonitorReport と同じ「正本→to_dict→YAML」の写像）。"""

    task: str
    n_predicted: int  # 予測ログの一意な input_fingerprint 数（衝突除外後）
    n_actual: int  # 実績テーブルの行数（一意な鍵）
    n_matched: int  # 予測と実績の両方にある指紋の数（実測指標はこの集合で計算）
    n_unmatched_predictions: int  # 予測はあるが実績がまだ来ていない
    n_unmatched_actuals: int  # 実績はあるが予測ログに無い
    n_skipped: int  # 読み飛ばした壊れ行
    comparisons: list[MetricComparison] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "n_predicted": self.n_predicted,
            "n_actual": self.n_actual,
            "n_matched": self.n_matched,
            "n_unmatched_predictions": self.n_unmatched_predictions,
            "n_unmatched_actuals": self.n_unmatched_actuals,
            "n_skipped": self.n_skipped,
            "comparisons": [
                {
                    "metric": c.metric,
                    "realized": c.realized,
                    "promised": c.promised,
                    "delta": c.delta,
                    "relative_degradation": c.relative_degradation,
                    "band": c.band,
                }
                for c in self.comparisons
            ],
        }


def _relative_degradation(realized: float, promised: float, *, higher_is_better: bool) -> float:
    """向きを考慮した悪化の割合。良化・同等は 0.0。基準が 0 から悪化したら inf（比は定義できないが劣化は本物）。

    higher_is_better なら promised より低いほど悪化、そうでなければ高いほど悪化。分母は |promised|。
    約束が 0（rmse=0 のような完全予測の約束）で実測が悪化した場合、比は定義できないが「劣化なし」ではない
    ＝inf を返す（band=大変化になり、--file-issue も起票する。0 を「基準なし」に丸めて劣化を見逃さない）。
    """
    worse = (promised - realized) if higher_is_better else (realized - promised)
    if worse <= 0.0:
        return 0.0  # 同等以上＝劣化なし（約束が 0 でもここに入る）
    if promised == 0.0:
        return math.inf  # 0 の約束から悪化＝比が定義できない＝無限大の劣化（見逃さない）
    return worse / abs(promised)


def _dedup_predictions(scored: ScoredPredictions) -> tuple[dict[str, Any], list[str]]:
    """指紋 → 予測の対応を作る。同じ指紋が食い違う予測を持つ（版混在・非決定）ときはその指紋を除外して返す。

    決定的なモデルなら同じ入力（同じ指紋）は同じ予測になる。食い違い＝版を絞り忘れた／非決定＝取り違えの
    元なので、黙って片方を採らずに除外し、呼び手が警告する（門番にしない・盲目にもしない）。
    """
    seen: dict[str, Any] = {}
    conflicts: set[str] = set()
    for fp, pred in zip(scored.input_fingerprints, scored.predictions, strict=True):
        if fp in conflicts:
            continue
        if fp not in seen:
            seen[fp] = pred
        elif seen[fp] != pred:
            del seen[fp]
            conflicts.add(fp)
    return seen, sorted(conflicts)


def answer_check(
    scored: ScoredPredictions,
    actuals: pl.DataFrame,
    *,
    actual_column: str,
    key_column: str = "input_fingerprint",
    task: str | None = None,
    metrics: Sequence[str] | None = None,
    threshold: float = 0.5,
    promised: Mapping[str, float] | None = None,
) -> AnswerCheckReport:
    """配信予測を実績で答え合わせして、実測指標と（あれば）昇格時の約束との差を表で返す。

    突き合わせは `key_column`（既定 input_fingerprint）での内部結合。実績テーブルは key_column と
    actual_column を持つ（key は一意＝重複は ValueError。利用者の入力の契約違反は黙って握り潰さない）。
    task はログの prediction_kind から導ける（proba→binary・multiclass_proba→multiclass・value→regression）。
    明示指定と食い違う・ログに複数種が混ざる場合は ValueError（取り違えて評価しない）。指標の算出は
    `ds/eval` の evaluate 系へ委譲。promised（昇格時 manifest の metrics）があれば指標ごとに delta・相対劣化・
    band を付ける。門番にしない（band は人が読む数字・exit code に載せない＝呼び手が exit 0 のまま扱う）。
    """
    if key_column not in actuals.columns:
        raise ValueError(f"実績テーブルに鍵の列 '{key_column}' が無い（列: {actuals.columns}）")
    if actual_column not in actuals.columns:
        raise ValueError(f"実績テーブルに正解の列 '{actual_column}' が無い（列: {actuals.columns}）")

    kinds = set(scored.prediction_kinds)
    if len(kinds) > 1:
        raise ValueError(f"予測ログに種類が混在している（{sorted(kinds)}）。--version でモデルの版を絞ること")
    resolved_task = task
    if kinds:
        kind = next(iter(kinds))
        derived = _KIND_TASK.get(kind)
        if derived is None:
            raise ValueError(f"未知の prediction_kind '{kind}'（契約は docs/serve.md）")
        if resolved_task is None:
            resolved_task = derived
        elif resolved_task != derived:
            raise ValueError(f"task={resolved_task!r} が予測ログの種類（{kind}→{derived}）と食い違う")
    if resolved_task is None:
        # 予測が 0 行（版フィルタ・--since で全部落ちた・まだ流入していない）。門番にしない＝空の表を返して
        # 呼び手が exit 0 のまま扱えるようにする（data monitor の空ログと同じ挙動。ここで落とすと昇格直後の
        # 定期実行を毎回失敗させてしまう＝「門番にしない」の中心が壊れる）。
        warnings.warn("予測ログに対象行が 0（版フィルタ・--since・未流入）。答え合わせは空で返す", stacklevel=2)
        resolved_task = task or "unknown"

    pred_by_fp, conflicts = _dedup_predictions(scored)
    if conflicts:
        warnings.warn(
            f"同じ入力指紋で予測が食い違う {len(conflicts)} 件を除外した（版の絞り忘れ・非決定の疑い。--version で"
            "版を絞ること）",
            stacklevel=2,
        )

    # 実績側：鍵の欠損は突き合わせ不能＝警告して除外・鍵の重複は入力の契約違反＝ValueError。
    keys = actuals.get_column(key_column)
    if keys.null_count() > 0:
        n_null = keys.null_count()
        warnings.warn(f"実績テーブルの鍵 '{key_column}' に欠損 {n_null} 件（突き合わせ不能＝除外）", stacklevel=2)
        actuals = actuals.filter(keys.is_not_null())
        keys = actuals.get_column(key_column)
    if keys.is_duplicated().any():
        dup = keys.filter(keys.is_duplicated()).unique().to_list()
        raise ValueError(f"実績テーブルの鍵 '{key_column}' が重複している（一意でないと答え合わせできない）: {dup[:5]}")
    actual_by_key = dict(zip(keys.to_list(), actuals.get_column(actual_column).to_list(), strict=True))

    n_predicted = len(pred_by_fp)
    n_actual = len(actual_by_key)
    matched_fps = [fp for fp in pred_by_fp if fp in actual_by_key]
    # 実績が NaN の行は指標を歪める（sklearn も NaN で不透明に落ちる）＝警告して除外（門番にしない）。
    nan_fps = {fp for fp in matched_fps if _is_nan(actual_by_key[fp])}
    if nan_fps:
        warnings.warn(f"実績が NaN の {len(nan_fps)} 行を除外した（答え合わせに使えない）", stacklevel=2)
        matched_fps = [fp for fp in matched_fps if fp not in nan_fps]
    n_matched = len(matched_fps)

    comparisons: list[MetricComparison] = []
    if n_matched > 0:
        realized = _compute_metrics(
            resolved_task,
            [pred_by_fp[fp] for fp in matched_fps],
            [actual_by_key[fp] for fp in matched_fps],
            metrics=metrics,
            threshold=threshold,
        )
        directions = ds_eval.directions(realized)
        for name, value in realized.items():
            prom = promised.get(name) if promised is not None else None
            delta = (value - prom) if prom is not None else None
            rel = _relative_degradation(value, prom, higher_is_better=directions[name]) if prom is not None else None
            comparisons.append(
                MetricComparison(
                    metric=name,
                    realized=value,
                    promised=prom,
                    delta=delta,
                    relative_degradation=rel,
                    band=degradation_band(rel),
                )
            )
        if promised is not None:  # 約束したのに実測側に無い指標は黙って未照合にしない（--metrics で絞った・task 違い）
            unmatched = sorted(m for m in promised if m not in realized)
            if unmatched:
                warnings.warn(
                    f"約束した指標 {unmatched} は実測側に無く未照合（--metrics の絞り込み・task 違いを確認）",
                    stacklevel=2,
                )
    else:
        warnings.warn("突き合わさった行が 0（実績がまだ来ていない・鍵が合わない）。指標は出さない", stacklevel=2)

    return AnswerCheckReport(
        task=resolved_task,
        n_predicted=n_predicted,
        n_actual=n_actual,
        n_matched=n_matched,
        n_unmatched_predictions=n_predicted - n_matched,
        n_unmatched_actuals=n_actual - n_matched,
        n_skipped=scored.n_skipped,
        comparisons=comparisons,
    )


def _compute_metrics(
    task: str,
    predictions: Sequence[Any],
    actuals: Sequence[Any],
    *,
    metrics: Sequence[str] | None,
    threshold: float,
) -> dict[str, float]:
    """突き合わせた予測・実績から実測指標を計算する（eval の evaluate 系へ委譲・task で分岐）。"""
    if task == "regression":
        y_true = np.asarray(actuals, dtype=np.float64)
        y_pred = np.asarray(predictions, dtype=np.float64)
        return ds_eval.evaluate_regression(y_true, y_pred, metrics=metrics)
    y_true = np.asarray(actuals).astype(np.int_)
    if task == "multiclass":
        y_proba = np.asarray(predictions, dtype=np.float64)  # 各行 list[float]＝(n, n_classes)
        return ds_eval.evaluate_multiclass(y_true, y_proba, metrics=metrics)
    y_score = np.asarray(predictions, dtype=np.float64)
    return ds_eval.evaluate(y_true, y_score, threshold=threshold, metrics=metrics)


# ---- 答え合わせ→課題起票（`data score --file-issue`）の内容組み立て（純関数。書き込みは CLI 側） ----


@dataclass(frozen=True)
class ScoreIssueContent:
    """--file-issue が起票する課題の内容。同じ入力（モデル×大変化の指標集合）なら同じ title/body。"""

    title: str
    body: str
    fingerprint: str


def score_issue_content(
    *, model: str, log: str, actuals: str, degraded: Sequence[MetricComparison], today: date
) -> ScoreIssueContent:
    """band=大変化（相対劣化 >= DEGRADE_ALERT）の指標から課題の title/body/指紋を組み立てる（決定的）。

    指紋は harness.fingerprint.input_fingerprint（正準 JSON の sha256）で、モデル×大変化の指標名集合だけから
    作る（劣化率・日付を含めない＝同じ劣化事象の再実行で重複起票しない）。drift_issue_content と同じ流儀。
    """
    names = sorted(c.metric for c in degraded)
    fp = input_fingerprint({"kind": "answer_degraded", "model": model, "metrics": names})
    by_name = {c.metric: c for c in degraded}
    lines = [
        "## 事象",
        f"`data score --model {model} --log '{log}' --actuals {actuals}` で実測指標が昇格時の約束から"
        f"大変化（相対劣化 >= {DEGRADE_ALERT}）（{today.isoformat()}）。",
        "",
        *[
            f"- {n}: 実測 {by_name[n].realized:.6f}・約束 "
            f"{by_name[n].promised:.6f}・相対劣化 {by_name[n].relative_degradation:.4f}（大変化）"
            for n in names
        ],
        "",
        "## 根拠・影響",
        "実測指標は後から届いた実績（正解）×配信予測の突き合わせ（input_fingerprint 結合）で計算。分布監視",
        "（psi/drift）が安定でも、現実の正解率が崩れていればここで初めて分かる。0.10 以上＝大変化は人が読む",
        "目安であって門番ではない（score は exit 0 のまま）。対処すると決めたら promoted_to で作業単位",
        "（再学習・特徴の見直し・切り戻し）に結びつける。閉ループの正本は docs/ops.md の「答え合わせの閉ループ」。",
        "",
        f"答え合わせ指紋: {fp}",
    ]
    title = f"実測劣化 {model}（大変化: {', '.join(names)}）"
    return ScoreIssueContent(title=title, body="\n".join(lines) + "\n", fingerprint=fp)
