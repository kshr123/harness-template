"""実験ループの一気通貫（薄い接着）。

`run_experiment` が「fold 作成 → 交差検証 → 合否判定」を 1 本で通す。保存や results の書き出しは
実験スクリプト（work/…/code/train.py）が担い、ここは計算の流れだけを持つ（テストしやすく・再利用できる）。
特徴量→モデルは呼び出し側が 1 本の sklearn Pipeline として渡す（run_cv が fold ごとに clone する）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
import yaml
from numpy.typing import NDArray
from sklearn.base import clone

from harness.ds.cv import (
    CVResult,
    MetricFn,
    SklearnLike,
    _predict,
    fold_indices,
    make_folds,
    make_time_folds,
    run_cv,
)
from harness.ds.eval import metric_fn_for, passes

Task = Literal["classification", "regression"]


@dataclass(frozen=True)
class ExperimentResult:
    """実験 1 回ぶんの結果。folds は再現のため保存でき、cv は OOF・fold 別モデル・指標を持つ。"""

    folds: pl.DataFrame
    cv: CVResult
    passed: bool

    @property
    def metrics(self) -> dict[str, float]:
        return self.cv.oof_metrics


def run_experiment(
    df: pl.DataFrame,
    y: NDArray[np.float64],
    estimator: SklearnLike,
    *,
    n_folds: int,
    seed: int,
    thresholds: Mapping[str, float],
    id_column: str = "id",
    stratify_by: str | None = None,
    order_by: str | None = None,
    task: Task = "classification",
    threshold: float = 0.5,
    metrics: Sequence[str] | None = None,
    predict: Literal["proba", "value"] | None = None,
) -> ExperimentResult:
    """fold を作り、estimator を交差検証し、OOF 指標が閾値を満たすか（passed）まで一気に返す。

    estimator は特徴量→モデルの 1 本の Pipeline。run_cv が fold ごとに clone→train で fit するので、
    特徴量の学習も train でだけ起き、漏れは構造的に起きない。task で分類/回帰を切り替える（指標と予測の種類が
    task から決まる）。predict 未指定は task から導く（分類=proba・回帰=value）。
    order_by を渡すと時間順分割（過去→未来の拡大窓）になる＝時間の順序があるデータで shuffle CV の誤用を防ぐ
    （stratify_by との同時指定はエラー）。fold 0 は学習専用で OOF に入らない。
    """
    if order_by is not None and stratify_by is not None:
        raise ValueError("order_by（時間順）と stratify_by（層化）は同時に使えない")
    if predict is None:
        predict = "value" if task == "regression" else "proba"
    metric_fn = metric_fn_for(task, threshold=threshold, metrics=metrics)
    if order_by is not None:
        folds = make_time_folds(df, n_folds=n_folds, order_by=order_by, id_column=id_column)
        splits = fold_indices(df, folds, id_column=id_column, how="expanding")
    else:
        folds = make_folds(df, n_folds=n_folds, seed=seed, id_column=id_column, stratify_by=stratify_by)
        splits = fold_indices(df, folds, id_column=id_column)
    cv_result = run_cv(estimator, df, y, splits, predict=predict, metric_fn=metric_fn)
    return ExperimentResult(folds=folds, cv=cv_result, passed=passes(cv_result.oof_metrics, dict(thresholds)))


def leaderboard(results_dir: Path, *, sort_by: str | None = None) -> pl.DataFrame:
    """results/metrics_*.yaml を集約した変種比較表（変種×指標・sort_by で降順）。

    実験スクリプトが変種ごとに残す `metrics_<variant>.yaml` を横串で読み、1 ファイル＝1 行の表にする。
    列は variant（無ければファイル名 stem の `metrics_` を除いて補完）・passed・model_version（`model.version`）＋
    metrics の各指標を展開（flatten）。変種で指標集合が違えば和集合の列（無い所は null）。
    sort_by 指定時はその指標で降順、未指定は最初のファイルの metrics に現れた最初の指標で降順
    （null・NaN は末尾・安定ソート＝決定的。NaN な指標が優勝に見えないよう最下位へ）。指標が 1 つも無ければ
    variant 昇順。空ディレクトリは空表（variant/passed/model_version の列だけ）。ディレクトリが存在しない・トップが
    辞書でない・metrics が辞書でない・指標値が数値でない（int/float 混在含む）は、どのファイルかを含む ValueError
    （黙って polars の TypeError にしない）。metrics キーの欠落は空 metrics 扱い（行は出す）。
    """
    if not results_dir.is_dir():  # 打ち間違いを空表と取り違えない（存在しない場所は空ディレクトリと区別して止める）
        raise ValueError(f"{results_dir}: results ディレクトリが無い（場所を確認する）")
    fixed_columns = ("variant", "passed", "model_version")
    rows: list[dict[str, Any]] = []
    metric_names: list[str] = []  # 出現順の和集合（列順とソート既定を決定的にする）
    for path in sorted(results_dir.glob("metrics_*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"{path}: トップが辞書でない（metrics yaml として読めない）")
        metrics = loaded.get("metrics") or {}
        if not isinstance(metrics, dict):
            raise ValueError(f"{path}: metrics が辞書でない（指標名→値の形で書く）")
        model = loaded.get("model")
        passed = loaded.get("passed")
        if passed is not None and not isinstance(passed, bool):
            raise ValueError(f"{path}: passed が真偽値でない（{passed!r}）")
        row: dict[str, Any] = {
            "variant": str(loaded.get("variant", path.stem.removeprefix("metrics_"))),  # 変種名は文字列に揃える
            "passed": passed,
            "model_version": str(model["version"]) if isinstance(model, dict) and "version" in model else None,
        }
        for name, value in metrics.items():
            if name in fixed_columns:
                raise ValueError(f"{path}: 指標名 {name!r} は固定列と衝突する（黙って上書きしない）")
            if name not in metric_names:
                metric_names.append(name)
            try:  # 指標値は float に正規化（int/float 混在で polars 構築が TypeError になるのを防ぐ）
                row[name] = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path}: 指標 {name!r} の値が数値でない（{value!r}）") from exc
        rows.append(row)
    if not rows:
        return pl.DataFrame(schema={"variant": pl.String, "passed": pl.Boolean, "model_version": pl.String})
    columns = [*fixed_columns, *metric_names]
    df = pl.DataFrame({col: [r.get(col) for r in rows] for col in columns})
    if sort_by is None:
        sort_by = metric_names[0] if metric_names else None
    elif sort_by not in metric_names:
        raise ValueError(f"sort_by {sort_by!r} は表に無い指標（あるのは {metric_names}）")
    if sort_by is None:  # 指標が 1 つも無い＝比べようがないので変種名の昇順
        return df.sort("variant")
    # NaN/null を最下位に（退化した変種を優勝に見せない）：is_null|is_nan を第 1 キー（False=良い行が先）に。
    bad_last = pl.col(sort_by).is_null() | pl.col(sort_by).is_nan()
    return df.sort([bad_last, pl.col(sort_by)], descending=[False, True], maintain_order=True)


@dataclass(frozen=True)
class HoldoutResult:
    """holdout（触っていない test）での最終評価。passed は thresholds を渡したときだけ判定（無指定は None）。"""

    metrics: dict[str, float]
    passed: bool | None = None


def final_eval_on_holdout(
    estimator: SklearnLike,
    df_fit: pl.DataFrame,
    y_fit: NDArray[np.float64],
    df_holdout: pl.DataFrame,
    y_holdout: NDArray[np.float64],
    *,
    task: Literal["classification", "multiclass", "regression"] = "classification",
    threshold: float = 0.5,
    metrics: Sequence[str] | None = None,
    thresholds: Mapping[str, float] | None = None,
    id_column: str = "id",
) -> HoldoutResult:
    """OOF で選抜した champion を、触っていない holdout（test）で一度だけ最終評価する。

    段取り：選抜・閾値調整は全行 OOF（`run_experiment`）で済ませ、champion 確定後にこの関数を 1 回だけ呼ぶ。
    holdout は選抜・閾値調整に**使わない**（使うとリーク）。estimator は clone してから **df_fit だけ**で fit する
    （run_cv と同じ流儀・渡した estimator は汚さない）。予測種別は task から導く（回帰=value・分類/多クラス=proba）。
    指標は eval.metric_fn_for（多クラスは task="multiclass" で evaluate_multiclass 経路）。thresholds を渡すと
    `passes` で合否も返す。df_fit と df_holdout の id が重なっていたら ValueError（黙って評価しない＝リーク・ガード）。
    test の取り分けは `data.fixed_split`（id ハッシュの安定分割）が使える。
    """
    fit_ids, holdout_ids = df_fit[id_column], df_holdout[id_column]
    # 型が違うと set の重なり検出が黙って無効になる（int 30 と str "30" は別物扱い＝同じ行を見逃す）。
    # 別ソース（CSV は str・parquet は int 等）から holdout を組むと起きるので、揃っていなければ止める。
    if fit_ids.dtype != holdout_ids.dtype:
        raise ValueError(
            f"df_fit と df_holdout の {id_column} の型が違う（{fit_ids.dtype} と {holdout_ids.dtype}）"
            "＝重なり検出が黙って無効になるため停止する（同じ型に揃えてから渡す）"
        )
    # 欠損 id は同一性の判定ができない（null 同士は等しくない）。重なり誤検出でなく id 欠損として明示で止める。
    if fit_ids.null_count() or holdout_ids.null_count():
        raise ValueError(f"{id_column} に欠損（null）がある＝id として使えない（重なり検出も曖昧になるため停止）")
    overlap = sorted(set(fit_ids.to_list()) & set(holdout_ids.to_list()), key=str)
    if overlap:
        raise ValueError(
            f"df_fit と df_holdout の {id_column} が重なっている（例: {overlap[:5]}）"
            "＝holdout が学習に混ざるため評価しない"
        )
    if df_fit.height != len(y_fit):
        raise ValueError(f"df_fit の行数 {df_fit.height} と y_fit の長さ {len(y_fit)} が一致しない")
    if df_holdout.height != len(y_holdout):
        raise ValueError(f"df_holdout の行数 {df_holdout.height} と y_holdout の長さ {len(y_holdout)} が一致しない")
    predict: Literal["proba", "value"] = "value" if task == "regression" else "proba"
    # y は run_cv と同じく元の dtype のまま渡す（分類の int 化は evaluate 側が担う）＝cv.MetricFn の契約で受ける。
    metric_fn: MetricFn = metric_fn_for(task, threshold=threshold, metrics=metrics)
    fitted = clone(estimator)
    fitted.fit(df_fit, y_fit)
    holdout_metrics = metric_fn(y_holdout, _predict(fitted, df_holdout, predict))
    passed = passes(holdout_metrics, dict(thresholds)) if thresholds is not None else None
    return HoldoutResult(metrics=holdout_metrics, passed=passed)
