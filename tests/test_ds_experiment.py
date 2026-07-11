"""experiment.run_experiment の結線テスト（統合）。一気通貫（fold→CV→合否）を確かめる。"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness.ds import data
from harness.ds.experiment import run_experiment
from harness.ds.features import Columns, FeaturePipeline

pytestmark = pytest.mark.integration


def _estimator() -> Pipeline:
    return Pipeline(
        [
            ("features", FeaturePipeline([("cols", Columns(["x1", "x2"]))])),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )


def test_run_experiment_end_to_end() -> None:
    df = data.generate_synthetic(n=200, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    result = run_experiment(df, y, _estimator(), n_folds=5, seed=1, thresholds={"roc_auc": 0.80}, stratify_by="y")

    assert result.folds.height == 200  # 全行に fold が付く
    assert result.cv.oof_mask.all()  # OOF は全行埋まる
    # 学習可能な合成データなので AUC は 0.8 を超え、passed になる（構成から言える）。
    assert result.metrics["roc_auc"] > 0.8
    assert result.passed


def test_run_experiment_multiclass_task() -> None:
    # G6：task="multiclass" が型（mypy strict）でも実行でも通ること。3 クラスは x1 の値域で線形分離できる構成
    # （中心 0/5/10・sd 0.5 で重なりが実質ない）なので accuracy はほぼ 1 ＝閾値 0.9 を超える（構成から言える）。
    rng = np.random.default_rng(0)
    n_per = 30
    x1 = np.concatenate([rng.normal(c, 0.5, n_per) for c in (0.0, 5.0, 10.0)])
    x2 = rng.normal(0.0, 1.0, 3 * n_per)
    y = np.repeat(np.arange(3), n_per).astype(np.float64)
    df = pl.DataFrame({"id": np.arange(3 * n_per), "x1": x1, "x2": x2, "y": y})
    result = run_experiment(
        df, y, _estimator(), n_folds=3, seed=1, thresholds={"accuracy": 0.9}, stratify_by="y", task="multiclass"
    )
    assert result.cv.oof.shape == (3 * n_per, 3)  # 多クラス OOF は (n, n_classes) の proba 行列
    assert result.metrics["accuracy"] > 0.9
    assert result.passed


def _grouped_df(n_groups: int, per_group: int, seed: int) -> tuple[pl.DataFrame, np.ndarray]:
    """1 グループ per_group 行のデータ。id は 0..N-1、g はグループ番号（各グループが連続する行）。"""
    rng = np.random.default_rng(seed)
    n = n_groups * per_group
    g = np.repeat(np.arange(n_groups), per_group)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    # ラベルは行ごとに両クラスが混ざる（各 fold にクラスが揃い、CV の縮退警告を避ける）。分離は問わない
    # （このテストが確かめるのは fold の構造＝グループが跨がないこと）。
    y = (np.arange(n) % 2).astype(np.float64)
    df = pl.DataFrame({"id": np.arange(n), "x1": x1, "x2": x2, "g": g, "y": y})
    return df, g


def test_run_experiment_group_by_prevents_group_leak() -> None:
    """group_by を通すと、同じグループの行が train と valid に跨がらない（グループ単位のリーク防止）。

    構成：10 グループ × 各 5 行。fold 表を group 列で突き合わせ、各グループが 1 つの fold にだけ入ることを
    確かめる（=fold_indices が valid=1 fold・train=残りに割るので、同一グループが train/valid に割れない）。
    期待値はデータの構成（どの id がどの g か）から導く（実装の出力の写経ではない）。
    """
    n_groups, per_group = 10, 5
    df, g = _grouped_df(n_groups, per_group, seed=0)
    y = df["y"].to_numpy()
    result = run_experiment(df, y, _estimator(), n_folds=5, seed=1, thresholds={}, group_by="g")
    # fold 表（id, fold）に真のグループ g を突き合わせる。各グループの fold が 1 種類だけなら跨がっていない。
    joined = result.folds.join(df.select("id", "g"), on="id")
    nf = joined.group_by("g").agg(pl.col("fold").n_unique().alias("nf"))["nf"].to_list()
    assert nf == [1] * n_groups  # どのグループも単一 fold＝train/valid に割れない（構成から導出）


def test_run_experiment_without_group_by_leaks_groups() -> None:
    """group_by を指定しない従来経路では、同じグループが複数 fold に割れる（=リークが起きる）。

    これが T-0186 の欠陥（黙って良い指標に見える）。group_by 版と同じ構成で、跨がるグループが出ることを示す。
    KFold（shuffle=True, seed=1）は各グループ 5 行を fold 境界で切るので、少なくとも 1 グループは複数 fold に跨る。
    """
    n_groups, per_group = 10, 5
    df, g = _grouped_df(n_groups, per_group, seed=0)
    y = df["y"].to_numpy()
    result = run_experiment(df, y, _estimator(), n_folds=5, seed=1, thresholds={})  # group_by なし
    joined = result.folds.join(df.select("id", "g"), on="id")
    nf = joined.group_by("g").agg(pl.col("fold").n_unique().alias("nf"))["nf"].to_list()
    assert max(nf) > 1  # 跨がるグループがある＝リーク（従来挙動は変えていない）


def test_run_experiment_group_by_rejects_with_order_by() -> None:
    """group_by と order_by（時間順）は同時に使えない（make_time_folds は group を扱わない）。"""
    df, _ = _grouped_df(4, 5, seed=0)
    y = df["y"].to_numpy()
    with pytest.raises(ValueError, match="order_by.*group_by|group_by.*order_by"):
        run_experiment(df, y, _estimator(), n_folds=2, seed=1, thresholds={}, order_by="id", group_by="g")


def test_decision_threshold_renamed_and_reaches_eval() -> None:
    # decision_threshold=0.0 → proba >= 0.0 で全行が陽性ラベル → recall はデータの中身によらず 1.0
    # （本当の陽性を全部拾う＝構成から導ける）。値が eval まで届いている証拠。
    df = data.generate_synthetic(n=120, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    result = run_experiment(
        df, y, _estimator(), n_folds=3, seed=1, thresholds={}, stratify_by="y", decision_threshold=0.0
    )
    assert result.metrics["recall"] == 1.0
    # 旧 threshold= は残さない（改名の証拠＝TypeError で使えない）。
    with pytest.raises(TypeError):
        run_experiment(
            df,
            y,
            _estimator(),
            n_folds=3,
            seed=1,
            thresholds={},
            stratify_by="y",
            threshold=0.4,  # type: ignore[call-arg]
        )
