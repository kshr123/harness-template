"""final_eval_on_holdout（holdout 最終評価）のテスト。

期待値はすべてデータ構成から導く：x1 の符号がそのままラベルを決める完全分離データなら、
同じ規則の holdout は accuracy 1.0、規則を反転した holdout は accuracy 0.0 になる
（学習した規則は df_fit の構成から一意に決まり、holdout の指標は holdout 側の規則で決まる）。
乱数は使わない（データは決定的に構成する）。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness.ds.experiment import final_eval_on_holdout
from harness.ds.features import Columns, FeaturePipeline


def _separable_df(start_id: int, n_per_class: int, *, invert: bool = False) -> tuple[pl.DataFrame, NDArray[np.float64]]:
    """x1 の符号がラベルを決める完全分離データ（x1=-1→y=0・x1=+1→y=1）。invert で規則を反転する。"""
    x1 = np.array([-1.0] * n_per_class + [1.0] * n_per_class)
    y = (x1 > 0).astype(np.float64)
    if invert:
        y = 1.0 - y
    ids = np.arange(start_id, start_id + 2 * n_per_class, dtype=np.int64)
    return pl.DataFrame({"id": ids, "x1": x1}), y


def _estimator(model: LogisticRegression | None = None) -> Pipeline:
    """雛形と同じ構成（特徴量→モデルの 1 本の Pipeline）。"""
    return Pipeline(
        [
            ("features", FeaturePipeline([("cols", Columns(["x1"]))])),
            ("model", model if model is not None else LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )


@pytest.mark.integration
def test_holdout_metrics_follow_holdout_composition() -> None:
    # fit と同じ規則（x1 の符号＝ラベル）の holdout なら、完全分離なので accuracy・roc_auc は 1.0。
    df_fit, y_fit = _separable_df(0, 20)
    df_hold, y_hold = _separable_df(100, 10)
    result = final_eval_on_holdout(_estimator(), df_fit, y_fit, df_hold, y_hold, thresholds={"accuracy": 0.95})
    assert result.metrics["accuracy"] == 1.0
    assert result.metrics["roc_auc"] == 1.0
    assert result.passed is True


@pytest.mark.integration
def test_holdout_with_inverted_rule_scores_zero() -> None:
    # holdout だけ規則を反転（x1=+1→y=0）：学習した規則と全行で食い違う構成なので accuracy・roc_auc は 0.0。
    # fit 側の規則では 1.0 になるはずの指標が holdout の構成で決まる＝holdout を測っている証拠。
    df_fit, y_fit = _separable_df(0, 20)
    df_hold, y_hold = _separable_df(100, 10, invert=True)
    result = final_eval_on_holdout(_estimator(), df_fit, y_fit, df_hold, y_hold)
    assert result.metrics["accuracy"] == 0.0
    assert result.metrics["roc_auc"] == 0.0
    assert result.passed is None  # thresholds を渡さなければ合否判定はしない
    gated = final_eval_on_holdout(_estimator(), df_fit, y_fit, df_hold, y_hold, thresholds={"accuracy": 0.95})
    assert gated.passed is False


@pytest.mark.integration
def test_fit_uses_only_df_fit_rows() -> None:
    # fit に渡った行数を記録するモデルで固定：fit は 1 回だけ・行数は df_fit と一致（holdout 行は入らない）。
    fit_sizes: list[int] = []

    class Recorder(LogisticRegression):  # type: ignore[misc]  # sklearn の型は Any（既存テストと同様）
        def fit(self, x: object, y: object) -> Recorder:
            fit_sizes.append(len(np.asarray(y)))
            super().fit(x, y)
            return self

    df_fit, y_fit = _separable_df(0, 20)
    df_hold, y_hold = _separable_df(100, 10)
    estimator = _estimator(Recorder(random_state=0, max_iter=1000))
    final_eval_on_holdout(estimator, df_fit, y_fit, df_hold, y_hold)
    assert fit_sizes == [df_fit.height]  # 1 回だけ・df_fit の 40 行だけで学習
    # clone してから fit するので、渡した estimator は未学習のまま（元を汚さない＝run_cv と同じ流儀）。
    assert not hasattr(estimator.named_steps["model"], "coef_")


@pytest.mark.unit
def test_overlapping_ids_raise() -> None:
    # id 30..39 が両方に入る構成：黙って評価せず ValueError（メッセージに重複 id を挙げる）。
    df_fit, y_fit = _separable_df(0, 20)  # id 0..39
    df_hold, y_hold = _separable_df(30, 10)  # id 30..49（30..39 が重複）
    with pytest.raises(ValueError, match="重なっている") as excinfo:
        final_eval_on_holdout(_estimator(), df_fit, y_fit, df_hold, y_hold)
    assert "30" in str(excinfo.value)


@pytest.mark.unit
def test_id_type_mismatch_raises() -> None:
    # 同じ行を指す id でも型が違う（int 30 と str "30"）と set の重なり検出が黙って無効になる。
    # 別ソース由来の holdout でガードが素通りしないよう、型不一致は明示で止める。
    df_fit, y_fit = _separable_df(0, 20)  # id は int 0..39
    df_hold, y_hold = _separable_df(30, 10)  # 本来 30..39 が重複
    df_hold = df_hold.with_columns(pl.col("id").cast(pl.Utf8))  # holdout の id だけ文字列に
    with pytest.raises(ValueError, match="型が違う"):
        final_eval_on_holdout(_estimator(), df_fit, y_fit, df_hold, y_hold)


@pytest.mark.unit
def test_null_id_raises() -> None:
    # 欠損 id は同一性判定ができない → 重なり誤検出でなく「id 欠損」として明示で止める。
    df_fit, y_fit = _separable_df(0, 20)
    df_hold, y_hold = _separable_df(100, 10)  # 重複しない id
    df_hold = df_hold.with_columns(
        pl.when(pl.arange(0, df_hold.height) == 0).then(None).otherwise(pl.col("id")).alias("id")
    )
    with pytest.raises(ValueError, match="欠損"):
        final_eval_on_holdout(_estimator(), df_fit, y_fit, df_hold, y_hold)


def _three_class_df(start_id: int, n_per_class: int) -> tuple[pl.DataFrame, NDArray[np.float64]]:
    """x1 のクラスタ（-4・0・+4）がそのままクラス（0・1・2）になる完全分離の 3 クラスデータ。"""
    x1 = np.repeat([-4.0, 0.0, 4.0], n_per_class)
    y = np.repeat([0.0, 1.0, 2.0], n_per_class)
    ids = np.arange(start_id, start_id + 3 * n_per_class, dtype=np.int64)
    return pl.DataFrame({"id": ids, "x1": x1}), y


@pytest.mark.integration
def test_multiclass_holdout_via_task() -> None:
    # 多クラスも task="multiclass" 経由（evaluate_multiclass 経路）。完全分離なので accuracy・macro_f1 は 1.0。
    df_fit, y_fit = _three_class_df(0, 20)
    df_hold, y_hold = _three_class_df(100, 10)
    estimator = _estimator(LogisticRegression(random_state=0, max_iter=2000, C=10.0))
    result = final_eval_on_holdout(estimator, df_fit, y_fit, df_hold, y_hold, task="multiclass")
    assert result.metrics["accuracy"] == 1.0
    assert result.metrics["macro_f1"] == 1.0
