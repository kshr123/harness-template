"""交差検証（CV）と固定分割：fold 割当・添字対のリスト・run_cv。

- 分割は「行番号の対のリスト」で渡す（固定分割＝要素1・CV＝要素k）。形をそろえる。
- fold 割当は表 (id, fold) にして split 層に保存でき、再現をコードでなくデータで担保する。
- 分割の計算そのものは sklearn（KFold/StratifiedKFold）を使う（再発明しない）。
- run_cv は estimator（sklearn 互換の Pipeline 等）を **fold ごとに clone して train 側だけで fit** する。
  これで特徴量の学習も train でだけ起き、valid の統計が混ざらない（漏れ防止が規約でなく構造）。
- 未カバー行の黙認を避けるため CVResult は oof に加えて oof_mask を持つ（固定分割でも同じ関数が正しく使える）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

import numpy as np
import polars as pl
from numpy.typing import NDArray
from sklearn.base import clone
from sklearn.model_selection import GroupKFold, KFold, StratifiedGroupKFold, StratifiedKFold

from harness.ds.eval import evaluate

Splits = Sequence[tuple[NDArray[np.int64], NDArray[np.int64]]]
MetricFn = Callable[[NDArray[Any], NDArray[np.float64]], dict[str, float]]


@runtime_checkable
class SklearnLike(Protocol):
    """sklearn 互換の最小契約（clone できる＝get_params を持ち、fit できる）。

    LogisticRegression も LGBMClassifier も Pipeline も FeaturePipeline もこれを満たす。
    run_cv はこの型だけに依存し、モデルの具体を知らない（差し替えは estimator の交換だけ）。
    """

    def fit(self, x: object, y: object) -> object: ...
    def get_params(self, deep: bool = True) -> dict[str, object]: ...


def make_folds(
    df: pl.DataFrame,
    *,
    n_folds: int,
    seed: int,
    id_column: str = "id",
    stratify_by: str | None = None,
    group_by: str | None = None,
) -> pl.DataFrame:
    """fold 割当表 (id_column, fold) を作る。同じ (df, seed) なら必ず同じ表。

    分割は scikit-learn の標準実装を使う（再発明しない）：無層化は KFold、層化は StratifiedKFold
    （クラス比率を保つ）。group_by（同一実体が複数行にまたがるデータ）は GroupKFold、層化との併用は
    StratifiedGroupKFold（同じグループの行を train と valid に跨がせない＝グループ単位のリーク防止）。
    いずれも shuffle・random_state=seed で再現する（GroupKFold の shuffle/random_state は sklearn 1.6 以降）。
    注意：層化+group はグループ構造次第（1 グループが極端に大きい・クラスがグループに偏る等）では層化が保証されない
    （警告なくクラス比が崩れうる）。グループ数 < n_folds は sklearn が ValueError で止める（黙って壊れない）。
    """
    if n_folds < 2:
        raise ValueError("n_folds は 2 以上にすること")
    n = df.height
    if n < n_folds:
        raise ValueError(f"行数 {n} が n_folds {n_folds} より少ない")
    fold = np.empty(n, dtype=np.int64)
    rows = np.arange(n)
    if group_by is not None:
        groups = df[group_by].to_numpy()
        if stratify_by is not None:
            strat = df[stratify_by].to_numpy()
            strat_grouped = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
            for k, (_, valid) in enumerate(strat_grouped.split(rows, strat, groups=groups)):
                fold[valid] = k
        else:
            grouped = GroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
            for k, (_, valid) in enumerate(grouped.split(rows, groups=groups)):
                fold[valid] = k
    elif stratify_by is None:
        splitter = KFold(n_splits=n_folds, shuffle=True, random_state=seed)
        for k, (_, valid) in enumerate(splitter.split(rows)):
            fold[valid] = k
    else:
        strat = df[stratify_by].to_numpy()
        stratified = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
        for k, (_, valid) in enumerate(stratified.split(rows, strat)):
            fold[valid] = k
    return df.select(id_column).with_columns(pl.Series("fold", fold))


def make_time_folds(
    df: pl.DataFrame,
    *,
    n_folds: int,
    order_by: str,
    id_column: str = "id",
) -> pl.DataFrame:
    """時間順の fold 割当表 (id_column, fold)。order_by で並べ、時間の連続ブロックに等分する（fold 0 が最古）。

    shuffle しない・seed 不要（決定的）。fold 番号＝時間ブロック番号。既存 make_folds と同じ表形式なので
    split 層への保存・再現の担保はそのまま効く。`fold_indices(how="expanding")` と組で使う。
    前提：等間隔・時刻はほぼ一意（同一時刻の行が fold 境界で train/valid に割れると軽い時間リークになりうる）。
    同一時刻の行が多いデータは、時刻でまとめてから使う（複数系列・重複時刻の厳密な扱いは最初の時系列案件で足す）。
    """
    if n_folds < 2:
        raise ValueError("n_folds は 2 以上にすること")
    n = df.height
    if n < n_folds:
        raise ValueError(f"行数 {n} が n_folds {n_folds} より少ない")
    ordered = df.select(id_column, order_by).sort(order_by)
    fold = (np.arange(n) * n_folds // n).astype(np.int64)  # 先頭から連続ブロックに 0..n_folds-1
    return ordered.select(id_column).with_columns(pl.Series("fold", fold))


def make_backtest_folds(
    df: pl.DataFrame,
    *,
    order_by: str,
    horizon: int,
    n_windows: int = 1,
    id_column: str = "id",
) -> pl.DataFrame:
    """時間順バックテストの fold 割当表 (id_column, fold)。末尾から horizon 行ずつ n_windows 個の検証窓を切る。

    fold 0 ＝学習専用の頭・fold 1..n_windows ＝古い順の検証窓。表の意味は expanding と同一
    （fold k の train ＝ fold < k の全行）なので `fold_indices(how="expanding")` がそのまま使える（T-D の流用）。
    決定的（seed 不要・shuffle しない）。古典時系列の run_forecast が使う。
    """
    if horizon < 1 or n_windows < 1:
        raise ValueError("horizon・n_windows は 1 以上にすること")
    n = df.height
    if n_windows * horizon >= n:
        raise ValueError(f"検証窓 {n_windows}×{horizon} が行数 {n} 以上（学習の頭が空になる分割は誤り）")
    ordered = df.select(id_column, order_by).sort(order_by)
    if ordered[order_by].n_unique() != n:
        raise ValueError(f"order_by '{order_by}' に重複がある（複数系列の混在は未対応）")
    fold = np.zeros(n, dtype=np.int64)  # 既定 0＝学習専用の頭
    for w in range(n_windows):
        start = n - (n_windows - w) * horizon  # 古い窓ほど前
        fold[start : start + horizon] = w + 1
    return ordered.select(id_column).with_columns(pl.Series("fold", fold))


def fold_indices(
    df: pl.DataFrame,
    folds: pl.DataFrame,
    *,
    id_column: str = "id",
    how: Literal["cv", "expanding"] = "cv",
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """fold 表を df の行番号の対 [(train_idx, valid_idx)] × k に引き直す。

    df の id と fold 表の id が一致しないと失敗する（部分適用の黙認をしない）。
    how="cv"（既定）：fold k を valid・残り全部を train（通常の交差検証）。
    how="expanding"：fold k(>=1) を valid・fold < k 全部を train（過去→未来の拡大窓・時間順分割）。fold 0 は valid に
    ならない（最初の学習材料）＝その行は oof_mask が False のまま（CVResult は部分カバーを黙認しない設計）。
    """
    # 重複 id は黙って潰さない（dict の後勝ち・set 比較では行数のずれを検出できず、再現の契約が崩れる）。
    if df[id_column].n_unique() != df.height:
        raise ValueError(f"df の {id_column} が重複している（fold 表との 1:1 対応が前提）")
    if folds[id_column].n_unique() != folds.height:
        raise ValueError(f"fold 表の {id_column} が重複している（1 id = 1 fold が前提）")
    joined = df.select(id_column).join(folds, on=id_column, how="left", validate="1:1", maintain_order="left")
    if df.height != folds.height or joined["fold"].null_count() > 0:
        df_set = set(df[id_column].to_list())
        table_set = set(folds[id_column].to_list())
        only_df = sorted(df_set - table_set, key=str)[:3]
        only_table = sorted(table_set - df_set, key=str)[:3]
        raise ValueError(f"fold 表と df の id が一致しない（df のみ {only_df} / 表のみ {only_table}）")
    assigned = joined["fold"].to_numpy().astype(np.int64)
    ks = sorted(set(assigned.tolist()))
    out: list[tuple[NDArray[np.int64], NDArray[np.int64]]] = []
    # 実際に存在する fold 値だけを回す（欠番があっても valid が空の fold を作らない＝空で指標が nan になるのを防ぐ）。
    for k in ks:
        valid = np.nonzero(assigned == k)[0].astype(np.int64)
        if how == "expanding":
            if k == ks[0]:
                continue  # 最古の fold は valid にしない（過去が無い＝学習専用）
            train = np.nonzero(assigned < k)[0].astype(np.int64)  # 過去 fold だけ（未来を見ない）
        else:
            train = np.nonzero(assigned != k)[0].astype(np.int64)
        out.append((train, valid))
    return out


def holdout_indices(n_train: int, n_valid: int) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """固定分割用。train を先頭・valid を後ろに連結した行列を前提に、要素 1 のリストを返す。

    固定分割も CV も「添字対のリスト」で学習系へ渡す形をそろえる。
    """
    train = np.arange(0, n_train, dtype=np.int64)
    valid = np.arange(n_train, n_train + n_valid, dtype=np.int64)
    return [(train, valid)]


@dataclass(frozen=True)
class CVResult:
    """CV の結果。oof は全行ぶんの器で、oof_mask が True の行だけ予測が入っている。

    oof の形は予測に合わせる：二値の proba・回帰の値は (n,)・多クラスの proba は (n, n_classes)。
    """

    oof: NDArray[np.float64]
    oof_mask: NDArray[np.bool_]
    fold_metrics: list[dict[str, float]]
    estimators: list[object]  # fold ごとに学習済みの estimator（Pipeline 丸ごと）
    oof_metrics: dict[str, float]


def _predict(estimator: object, x: pl.DataFrame, how: Literal["proba", "value"]) -> NDArray[np.float64]:
    """valid への予測。二値分類は陽性（ラベル 1）の確率 1 列・多クラスは predict_proba の (n, n_classes)・回帰は値。

    predict_proba の列順は classes_ の並び（ソート順）であってラベルの値ではない。二値でラベルが {1,2} 等だと
    列 1 固定は別クラスの確率を黙って返すため、陽性の列は classes_ からラベル 1 を探して解決する。
    classes_ が 3 つ以上（多クラス）は陽性列を選ばず全列 (n, n_classes) をそのまま返す
    （evaluate_multiclass はラベル 0..n_classes-1 前提＝列順と一致）。列の意味がラベル番号とズレると黙って
    誤った指標になるため、多クラスも classes_ が連番 0..k-1 であることを検査する（二値のラベル 1 検査と対）。
    fold 間でクラス集合が違う（例：ある fold の train に一部クラスが出ない）場合もここで止まる。
    二値の proba は両クラスがある前提（predict_proba が 2 列）。fold の train が単一クラスだと壊れるが、
    層化（make_folds の stratify_by）で各 fold にクラスが揃うため段階1では起きない。
    なお valid に稀クラスが出ないと macro_roc_auc は nan になりうる（passes は NaN で fail-closed・昇格は防がれる）。
    """
    if how == "proba":
        classes = np.asarray(estimator.classes_)  # type: ignore[attr-defined]
        proba: NDArray[np.float64] = np.asarray(estimator.predict_proba(x), dtype=np.float64)  # type: ignore[attr-defined]
        if len(classes) > 2:  # 多クラス：クラス数分の列（列順は classes_ のソート順）
            # 契約：ラベルは 0..n_classes-1（列 i＝クラス i）。連番でないと列の意味が黙ってズレるため止める。
            if not np.array_equal(classes, np.arange(len(classes))):
                raise ValueError(
                    "多クラスのラベルは 0..n_classes-1 が前提（列順＝クラス番号）。"
                    f"実際のラベル: {classes.tolist()}（fold 間でクラス集合が違う場合もここで止まる）"
                )
            return proba
        pos_at = np.flatnonzero(classes == 1)
        if pos_at.size == 0:
            raise ValueError(f"classes_ にラベル 1 が無い（陽性=ラベル 1 が前提。実際のラベル: {classes.tolist()}）")
        return proba[:, int(pos_at[0])]
    value: NDArray[np.float64] = np.asarray(estimator.predict(x), dtype=np.float64)  # type: ignore[attr-defined]
    return value


def run_cv(
    estimator: SklearnLike,
    x: pl.DataFrame,
    y: NDArray[np.float64],
    splits: Splits,
    *,
    predict: Literal["proba", "value"] = "proba",
    metric_fn: MetricFn = evaluate,
) -> CVResult:
    """fold ごとに estimator を clone して train 側だけで fit し、valid の予測を oof に格納する。

    - clone するので特徴量の学習も fold の train でだけ起きる（valid の統計が混ざらない＝構造的な漏れ防止）。
    - x と y の行数が違えば失敗（ずれたまま fit すると黙って別の行の答えを学習する）。
    - train と valid が重なる分割は失敗（valid の答えを学習に使う＝漏れ。splits は公開の入り口なので構造で守る）。
    - valid_idx が重複していたら失敗（同じ行に 2 回書く分割は分割の誤り）。
    - 指標は分類（evaluate＝accuracy・roc_auc）を既定にし、y_true は整数ラベルとして渡す（段階1）。
    - 多クラスは predict="proba" のまま使える（_predict が (n_valid, n_classes) を返し、oof の器も (n, n_classes) に
      切り替わる）。metric_fn には eval.metric_fn_for("multiclass") を渡すこと（既定の evaluate は二値用）。
    - 再現性は estimator が持つ random_state に委ねる（fold ごとの独立種は作らない。clone で足りる）。
    """
    n = len(y)
    if x.height != n:
        raise ValueError(f"x の行数 {x.height} と y の長さ {n} が一致しない")
    oof: NDArray[np.float64] = np.zeros(n, dtype=np.float64)
    oof_mask = np.zeros(n, dtype=np.bool_)
    fold_metrics: list[dict[str, float]] = []
    estimators: list[object] = []
    for train_idx, valid_idx in splits:
        # 先に「同じ行に 2 回書く分割」を弾く（fold をまたいだ valid の重複＝既存の契約）。
        if oof_mask[valid_idx].any():
            raise ValueError("valid_idx が重複している（同じ行に 2 回予測を書く分割は誤り）")
        if np.intersect1d(train_idx, valid_idx).size:
            raise ValueError("train と valid が重なる分割は誤り（valid の答えを学習に使う＝漏れ）")
        fitted = clone(estimator)
        fitted.fit(x[train_idx], y[train_idx])
        pred = _predict(fitted, x[valid_idx], predict)
        # 多クラスの proba は (n_valid, n_classes) → 最初の fold の列数で oof の器を 2 次元に切り替える。
        # fold 間で形（クラス数）が食い違ったら黙って書かず失敗（層化していない分割で train のクラスが欠けると起きる）。
        shape_msg = "fold 間で予測の形が違う（多クラスの proba は全 fold で同じクラス数が前提＝層化分割を使うこと）"
        if pred.ndim == 2:
            if oof.ndim == 1:
                if oof_mask.any():
                    raise ValueError(shape_msg)
                oof = np.zeros((n, pred.shape[1]), dtype=np.float64)
            elif oof.shape[1] != pred.shape[1]:
                raise ValueError(shape_msg)
        elif oof.ndim == 2:
            raise ValueError(shape_msg)
        oof[valid_idx] = pred
        oof_mask[valid_idx] = True
        # y は元の dtype のまま metric_fn へ渡す（分類か回帰かで型の扱いが違う。分類の int 化は evaluate 側が担う。
        # ここで int に丸めると回帰の目的変数（連続値）が壊れる）。
        fold_metrics.append(metric_fn(y[valid_idx], pred))
        estimators.append(fitted)
    oof_metrics = metric_fn(y[oof_mask], oof[oof_mask])
    return CVResult(
        oof=oof, oof_mask=oof_mask, fold_metrics=fold_metrics, estimators=estimators, oof_metrics=oof_metrics
    )
