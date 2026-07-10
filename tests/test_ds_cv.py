"""cv.py の単体テスト（fold 割当・添字対）。期待値はテストデータの構成から導ける。"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.linear_model import LogisticRegression

from harness.ds import cv
from harness.ds.eval import metric_fn_for

pytestmark = pytest.mark.unit


def test_make_folds_even_sizes() -> None:
    # 20 行を 4 fold → 各 fold ちょうど 5 行（差 0）。
    df = pl.DataFrame({"id": np.arange(20, dtype=np.int64)})
    folds = cv.make_folds(df, n_folds=4, seed=0)
    counts = folds["fold"].value_counts().sort("fold")["count"].to_list()
    assert counts == [5, 5, 5, 5]


def test_make_folds_stratified_keeps_class_balance() -> None:
    # y が 8 個の 1 と 12 個の 0。4 fold で層化 → 各 fold は 1 が 2 個・0 が 3 個。
    df = pl.DataFrame({"id": np.arange(20, dtype=np.int64), "y": np.array([1] * 8 + [0] * 12, dtype=np.int64)})
    folds = cv.make_folds(df, n_folds=4, seed=0, stratify_by="y").join(df, on="id")
    for k in range(4):
        part = folds.filter(pl.col("fold") == k)
        assert part.filter(pl.col("y") == 1).height == 2
        assert part.filter(pl.col("y") == 0).height == 3


def test_make_folds_deterministic() -> None:
    df = pl.DataFrame({"id": np.arange(30, dtype=np.int64)})
    a = cv.make_folds(df, n_folds=5, seed=7)
    b = cv.make_folds(df, n_folds=5, seed=7)
    c = cv.make_folds(df, n_folds=5, seed=8)
    assert a.equals(b)  # 同じ (df, seed) → 同じ表
    assert not a.equals(c)  # 種が違えば別の表


def test_make_folds_rejects_bad_args() -> None:
    df = pl.DataFrame({"id": np.arange(3, dtype=np.int64)})
    with pytest.raises(ValueError, match="n_folds"):
        cv.make_folds(df, n_folds=1, seed=0)
    with pytest.raises(ValueError, match="少ない"):
        cv.make_folds(df, n_folds=5, seed=0)  # 行数 3 < 5


def test_make_folds_group_no_leak() -> None:
    # group 0..9 が各 5 行（計 50 行）。group_by 指定 → 各グループの全行が同じ fold 値になる
    # （cv では fold k が valid・残りが train なので、fold 値が単一＝同一グループが train/valid を跨がない）。
    g = np.repeat(np.arange(10, dtype=np.int64), 5)
    df = pl.DataFrame({"id": np.arange(50, dtype=np.int64), "g": g})
    folds = cv.make_folds(df, n_folds=5, seed=0, group_by="g")
    joined = folds.join(df, on="id")
    per_group = joined.group_by("g").agg(pl.col("fold").n_unique().alias("nf"))
    assert per_group["nf"].to_list() == [1] * 10  # 全グループが単一 fold の valid にのみ入る
    # 等サイズ 10 グループを 5 fold へ → 各 fold ちょうど 2 グループ＝10 行（構成から導出）。
    counts = joined["fold"].value_counts().sort("fold")["count"].to_list()
    assert counts == [10] * 5
    # 同じ (df, seed) → 同じ表（再現性の契約は group 分割でも保つ）。
    assert folds.equals(cv.make_folds(df, n_folds=5, seed=0, group_by="g"))


def test_make_folds_stratified_group_keeps_balance_and_no_leak() -> None:
    # 12 グループ×各 5 行（計 60 行）。グループは単一クラス：クラス 1 が 4 グループ・クラス 0 が 8 グループ
    # （全体の陽性率 1/3）。4 fold の StratifiedGroupKFold → 各 fold は 3 グループ＝15 行で、取りうる陽性率は
    # {0, 1/3, 2/3} のみ（グループ単位で動く）。±0.15 は実質「各 fold に陽性グループがちょうど 1 個」＝完全層化を
    # 要求する（陽性 4 グループ / 4 fold ＝ 各 1 個で達成可能）。かつグループは fold を跨がない。両方を 1 テストで。
    g = np.repeat(np.arange(12, dtype=np.int64), 5)
    y = np.repeat(np.array([1] * 4 + [0] * 8, dtype=np.int64), 5)
    df = pl.DataFrame({"id": np.arange(60, dtype=np.int64), "g": g, "y": y})
    joined = cv.make_folds(df, n_folds=4, seed=0, stratify_by="y", group_by="g").join(df, on="id")
    per_group = joined.group_by("g").agg(pl.col("fold").n_unique().alias("nf"))
    assert per_group["nf"].to_list() == [1] * 12  # グループ非跨ぎ
    for k in range(4):
        part = joined.filter(pl.col("fold") == k)
        assert part.height > 0  # 空 fold を作らない
        rate = part.filter(pl.col("y") == 1).height / part.height
        assert abs(rate - 1 / 3) <= 0.15  # 層化が効く（全体 1/3 の近傍）


def test_make_folds_group_by_none_matches_sklearn_kfold() -> None:
    # group_by 未指定は素の KFold（shuffle=True・random_state=seed）の分割そのもの＝ラッパが余計をしない。
    # 実装と同じ引数で sklearn を独立に呼んだ fold 割当と一致（自己比較でなく外部オラクル＝回帰テスト）。
    from sklearn.model_selection import KFold

    df = pl.DataFrame({"id": np.arange(20, dtype=np.int64)})
    got = cv.make_folds(df, n_folds=4, seed=3)
    fold = np.empty(20, dtype=np.int64)
    for k, (_, valid) in enumerate(KFold(n_splits=4, shuffle=True, random_state=3).split(np.arange(20))):
        fold[valid] = k
    expected = df.select("id").with_columns(pl.Series("fold", fold))
    assert got.equals(expected)


def test_fold_indices_roundtrip() -> None:
    df = pl.DataFrame({"id": np.arange(6, dtype=np.int64)})
    folds = pl.DataFrame({"id": np.arange(6, dtype=np.int64), "fold": np.array([0, 1, 0, 1, 0, 1], dtype=np.int64)})
    splits = cv.fold_indices(df, folds)
    assert len(splits) == 2
    # fold 0：valid＝行位置 0,2,4／train＝1,3,5（構成から厳密）。
    np.testing.assert_array_equal(splits[0][1], [0, 2, 4])
    np.testing.assert_array_equal(splits[0][0], [1, 3, 5])
    np.testing.assert_array_equal(splits[1][1], [1, 3, 5])


def test_fold_indices_rejects_id_mismatch() -> None:
    df = pl.DataFrame({"id": np.arange(3, dtype=np.int64)})
    folds = pl.DataFrame({"id": np.array([0, 1], dtype=np.int64), "fold": np.array([0, 1], dtype=np.int64)})
    with pytest.raises(ValueError, match="一致しない"):
        cv.fold_indices(df, folds)  # id=2 に fold が無い


def test_holdout_indices() -> None:
    splits = cv.holdout_indices(n_train=3, n_valid=2)
    assert len(splits) == 1
    np.testing.assert_array_equal(splits[0][0], [0, 1, 2])
    np.testing.assert_array_equal(splits[0][1], [3, 4])


def test_predict_proba_uses_class_label_1_column() -> None:
    # ラベル {1, 2} だと classes_ == [1, 2] で「ラベル 1」は列 0。列 1 固定だと P(y==2) を返してしまう。
    x = pl.DataFrame({"f": [0.0, 0.0, 0.0, 10.0, 10.0, 10.0]})
    y = np.array([1, 1, 1, 2, 2, 2], dtype=np.int64)
    clf = LogisticRegression(random_state=0).fit(x, y)
    pred = cv._predict(clf, x, "proba")
    # 期待値＝classes_ からラベル 1 の列を引いた確率（構成から導ける・列番号のハードコードなし）。
    expected = clf.predict_proba(x)[:, list(clf.classes_).index(1)]
    np.testing.assert_allclose(pred, expected)
    # f=0 の行はラベル 1 側に分離してある → P(y==1) > 0.5（データ構成から導ける向き）。
    assert (pred[:3] > 0.5).all()


def test_predict_proba_requires_label_1() -> None:
    # ラベルに 1 が無い（{2, 3}）と「陽性=ラベル 1」を選べない → 黙って別クラスを返さず明確に失敗する。
    x = pl.DataFrame({"f": [0.0, 0.0, 10.0, 10.0]})
    y = np.array([2, 2, 3, 3], dtype=np.int64)
    clf = LogisticRegression(random_state=0).fit(x, y)
    with pytest.raises(ValueError, match="ラベル 1"):
        cv._predict(clf, x, "proba")


def test_predict_multiclass_returns_full_proba_matrix() -> None:
    # 3 クラス（平均 0/8/16・σ0.5 のガウス＝ほぼ完全分離）。多クラスは陽性列を選ばず (n, n_classes) を返す。
    rng = np.random.default_rng(0)
    x = pl.DataFrame({"f": np.concatenate([rng.normal(c, 0.5, 10) for c in (0.0, 8.0, 16.0)])})
    y = np.repeat(np.arange(3), 10)
    clf = LogisticRegression(random_state=0).fit(x, y)
    pred = cv._predict(clf, x, "proba")
    assert pred.shape == (30, 3)  # クラス数分の列
    np.testing.assert_allclose(pred.sum(axis=1), 1.0)  # 各行は確率分布（和 1）
    np.testing.assert_allclose(pred, clf.predict_proba(x))  # predict_proba 素通し（列順は classes_）


def test_predict_multiclass_requires_contiguous_labels() -> None:
    # 多クラスのラベルが 0..k-1 の連番でない（{0,2,4}）と列の意味（列 i＝クラス i）が黙ってズレる。
    # 二値の「ラベル 1」検査と対に、連番でなければ ValueError で止める（fold 間のクラス集合ズレも同じ検査で閉じる）。
    rng = np.random.default_rng(0)
    x = pl.DataFrame({"f": np.concatenate([rng.normal(c, 0.5, 8) for c in (0.0, 8.0, 16.0)])})
    y = np.repeat(np.array([0, 2, 4], dtype=np.int64), 8)  # 3 クラスだが連番でない
    clf = LogisticRegression(random_state=0).fit(x, y)
    assert list(clf.classes_) == [0, 2, 4]  # 前提：classes_ が連番でない
    with pytest.raises(ValueError, match="前提"):
        cv._predict(clf, x, "proba")


def test_run_cv_multiclass_oof_and_macro_f1() -> None:
    # 平均 0/8/16・σ0.5 ＝クラス間 16σ の完全分離 → OOF でも argmax が真値と一致し macro_f1 ≈ 1.0
    # （境界はデータ構成から導く・実装出力の写経ではない）。oof の器は (n, 3) に切り替わり、各行は和 1。
    rng = np.random.default_rng(7)
    n_per = 12
    n = 3 * n_per
    x = pl.DataFrame({"f": np.concatenate([rng.normal(c, 0.5, n_per) for c in (0.0, 8.0, 16.0)])})
    y = np.repeat(np.arange(3), n_per).astype(np.float64)
    df = pl.DataFrame({"id": np.arange(n, dtype=np.int64), "y": y.astype(np.int64)})
    folds = cv.make_folds(df, n_folds=3, seed=0, stratify_by="y")  # 層化＝各 fold に 3 クラスが揃う
    splits = cv.fold_indices(df, folds)
    result = cv.run_cv(
        LogisticRegression(random_state=0),
        x,
        y,
        splits,
        predict="proba",
        metric_fn=metric_fn_for("multiclass", metrics=["macro_f1", "accuracy"]),
    )
    assert result.oof.shape == (n, 3)
    assert result.oof_mask.all()
    np.testing.assert_allclose(result.oof.sum(axis=1), 1.0)
    assert result.oof_metrics["macro_f1"] >= 0.95
    assert result.oof_metrics["accuracy"] >= 0.95


def test_fold_indices_rejects_duplicate_df_ids() -> None:
    # df 側に同じ id が 2 回 → fold 表 (id, fold) との 1:1 対応（再現の契約）が崩れるので失敗する。
    df = pl.DataFrame({"id": np.array([0, 1, 1, 2], dtype=np.int64)})
    folds = pl.DataFrame({"id": np.arange(3, dtype=np.int64), "fold": np.array([0, 1, 0], dtype=np.int64)})
    with pytest.raises(ValueError, match="重複"):
        cv.fold_indices(df, folds)


def test_fold_indices_rejects_duplicate_fold_table_ids() -> None:
    # fold 表側に同じ id が 2 回（fold の値は食い違う）→ 後勝ちで黙って潰さず失敗する。
    df = pl.DataFrame({"id": np.arange(3, dtype=np.int64)})
    folds = pl.DataFrame({"id": np.array([0, 1, 1, 2], dtype=np.int64), "fold": np.array([0, 0, 1, 1], dtype=np.int64)})
    with pytest.raises(ValueError, match="重複"):
        cv.fold_indices(df, folds)


def test_fold_indices_expanding_equivalence() -> None:
    # 既知の小さな fold 表（時間順ブロック 0,0,1,1,2,2）で expanding の分割が構成どおりであること
    # （1:1 の正常系が修正前と同じ分割を返すことの確認）。
    df = pl.DataFrame({"id": np.arange(6, dtype=np.int64)})
    folds = pl.DataFrame({"id": np.arange(6, dtype=np.int64), "fold": np.array([0, 0, 1, 1, 2, 2], dtype=np.int64)})
    splits = cv.fold_indices(df, folds, how="expanding")
    assert len(splits) == 2  # fold 0 は valid にならない（学習専用の頭）
    np.testing.assert_array_equal(splits[0][0], [0, 1])  # fold 1 の train ＝ fold < 1
    np.testing.assert_array_equal(splits[0][1], [2, 3])
    np.testing.assert_array_equal(splits[1][0], [0, 1, 2, 3])  # fold 2 の train ＝ fold < 2
    np.testing.assert_array_equal(splits[1][1], [4, 5])


def test_run_cv_rejects_overlapping_train_valid() -> None:
    # 行位置 3 が train と valid の両方に居る＝valid の答えを学習に使う分割（漏れ）→ 失敗する。
    x = pl.DataFrame({"f": [0.0, 0.0, 10.0, 10.0, 0.0, 10.0]})
    y = np.array([0, 0, 1, 1, 0, 1], dtype=np.float64)
    splits = [(np.array([0, 1, 2, 3], dtype=np.int64), np.array([3, 4, 5], dtype=np.int64))]
    with pytest.raises(ValueError, match="重なる"):
        cv.run_cv(LogisticRegression(random_state=0), x, y, splits)


def test_run_cv_rejects_length_mismatch() -> None:
    # x は 6 行・y は 4 個 → 行がずれたまま fit する前に失敗する。
    x = pl.DataFrame({"f": [0.0, 0.0, 10.0, 10.0, 0.0, 10.0]})
    y = np.array([0, 0, 1, 1], dtype=np.float64)
    with pytest.raises(ValueError, match="行数"):
        cv.run_cv(LogisticRegression(random_state=0), x, y, cv.holdout_indices(3, 3))


def test_run_cv_valid_split_still_runs() -> None:
    # 正常な固定分割（train 4 行・valid 2 行・重なりなし）は通る。valid 側だけ oof_mask が True・予測は確率。
    x = pl.DataFrame({"f": [0.0, 0.0, 10.0, 10.0, 0.0, 10.0]})
    y = np.array([0, 0, 1, 1, 0, 1], dtype=np.float64)
    result = cv.run_cv(LogisticRegression(random_state=0), x, y, cv.holdout_indices(4, 2))
    np.testing.assert_array_equal(result.oof_mask, [False] * 4 + [True] * 2)
    assert ((result.oof[4:] >= 0.0) & (result.oof[4:] <= 1.0)).all()
