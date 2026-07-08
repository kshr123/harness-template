"""pipeline.build_estimator の組み立てとエンコーダ既定の単体テスト（原則 fit しない・構成から導出）。

疎行列の境界（_to_numpy が疎を密化しない）だけは fit を伴う結線テスト（integration 印）を併置する。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
import pytest
import scipy.sparse as sp
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.decomposition import TruncatedSVD
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import KFold, RandomizedSearchCV, StratifiedKFold

from harness.ds import cv
from harness.ds.pipeline import ENCODERS, MODELS, SELECTORS, _to_numpy, build_estimator, build_model

_COLS = {"kind": "columns", "columns": ["c"]}


def _model() -> LogisticRegression:
    return LogisticRegression(max_iter=1000)


@pytest.mark.unit
def test_build_estimator_assembles_three_and_two_stages() -> None:
    est = build_estimator({"features": [_COLS], "encode": [{"kind": "onehot", "columns": ["c"]}]}, _model(), seed=0)
    assert [n for n, _ in est.steps] == ["features", "encode", "to_numpy", "model"]
    assert isinstance(est.named_steps["encode"], ColumnTransformer)
    two = build_estimator({"features": [_COLS]}, _model(), seed=0)  # encode 無し → features→to_numpy→model
    assert [n for n, _ in two.steps] == ["features", "to_numpy", "model"]


@pytest.mark.unit
def test_build_estimator_validates() -> None:
    with pytest.raises(ValueError, match="features"):
        build_estimator({"features": []}, _model(), seed=0)
    with pytest.raises(ValueError, match="未知の特徴量"):
        build_estimator({"features": [{"kind": "nope"}]}, _model(), seed=0)
    with pytest.raises(ValueError, match="未知のエンコーダ"):
        build_estimator({"features": [_COLS], "encode": [{"kind": "nope", "columns": ["c"]}]}, _model(), seed=0)
    with pytest.raises(ValueError, match="重複"):
        build_estimator(
            {
                "features": [_COLS],
                "encode": [{"kind": "onehot", "columns": ["c"]}, {"kind": "onehot", "columns": ["c"]}],
            },
            _model(),
            seed=0,
        )


@pytest.mark.unit
def test_onehot_safe_default_and_override() -> None:
    spec = {"features": [_COLS], "encode": [{"kind": "onehot", "columns": ["c"], "min_frequency": 2}]}
    oh = build_estimator(spec, _model(), seed=0).named_steps["encode"].transformers[0][1]
    assert oh.get_params()["min_frequency"] == 2  # params は sklearn へ素通し（上書き）
    assert oh.get_params()["handle_unknown"] == "infrequent_if_exist"  # 落ちない安全既定は焼き込み


@pytest.mark.unit
def test_target_encoder_cv_is_seeded_kfold() -> None:
    # 回帰（Ridge）：従来どおり非推奨 shuffle/random_state を使わず cv=KFold(seed)（連続 y は層化できない）。
    spec = {"features": [_COLS], "encode": [{"kind": "target", "columns": ["c"], "cv": 3}]}
    te = build_estimator(spec, Ridge(), seed=7).named_steps["encode"].transformers[0][1]
    kfold = te.get_params()["cv"]
    assert type(kfold) is KFold  # 回帰＝非層化（StratifiedKFold は連続 y で落ちる）
    assert kfold.get_n_splits() == 3
    assert (kfold.shuffle, kfold.random_state) == (True, 7)  # seed 配線（決定的な OOF）


@pytest.mark.unit
def test_target_encoder_cv_is_stratified_for_classification() -> None:
    # 分類（logreg）：内側 OOF の分割が StratifiedKFold(shuffle=True, random_state=seed)。task は encode 節に
    # 書かせず model から知る（build_estimator が is_classifier で注入・sklearn の cv=int 既定と同じ振る舞いを決定化）。
    spec = {"features": [_COLS], "encode": [{"kind": "target", "columns": ["c"], "cv": 3}]}
    te = build_estimator(spec, _model(), seed=7).named_steps["encode"].transformers[0][1]
    inner = te.get_params()["cv"]
    assert type(inner) is StratifiedKFold  # 分類＝層化（不均衡でも内側 fold がクラス比を保つ）
    assert inner.get_n_splits() == 3
    assert (inner.shuffle, inner.random_state) == (True, 7)  # seed 明示で決定的（グローバル種なし）


@pytest.mark.unit
def test_target_encoder_unknown_task_fails_loud() -> None:
    # task の typo は黙って KFold に落とさない（ENCODERS.build から直接使う経路の fail-loud）。
    with pytest.raises(ValueError, match="未知の task"):
        ENCODERS.build({"kind": "target", "columns": ["c"], "task": "nope"}, seed=0)


@pytest.mark.integration
def test_target_encoder_classification_inner_folds_keep_class_ratio() -> None:
    # 構成：100 行＝カテゴリ 10 種 × 10 行・陽性 20 行（陽性率 0.2・seed 固定の並べ替え）。層化の定義から、
    # 内側 5 fold の各 valid（20 行）に陽性はちょうど 20/5=4 行（クラス比 0.2 を厳密に保つ・構成から導出）。
    # 非層化 KFold ではこの均等配分は保証されない（G2：不均衡で内側エンコーディングが静かに劣化する、の核心）。
    rng = np.random.default_rng(3)
    df = pl.DataFrame({"c": [f"c{k}" for k in range(10)] * 10})
    y = rng.permutation(np.array([1.0] * 20 + [0.0] * 80))
    spec = {"features": [{"kind": "columns", "columns": ["c"]}], "encode": [{"kind": "target", "columns": ["c"]}]}
    te = build_estimator(spec, _model(), seed=11).named_steps["encode"].transformers[0][1]
    inner = te.get_params()["cv"]
    assert type(inner) is StratifiedKFold
    for _, valid in inner.split(np.zeros(len(y)), y):
        assert len(valid) == 20
        assert y[valid].sum() == 4.0  # 各 fold の陽性 4/20 ＝クラス比 0.2 を厳密に保つ
    # 決定性：同じ seed で 2 回組み直して fit → OOF エンコード結果が完全一致（seed 固定で 2 回同一）。
    out_a = np.asarray(build_estimator(spec, _model(), seed=11)[:2].fit_transform(df, y))
    out_b = np.asarray(build_estimator(spec, _model(), seed=11)[:2].fit_transform(df, y))
    np.testing.assert_array_equal(out_a, out_b)
    assert out_a.shape == (100, 1)  # target 1 列だけがエンコードされて届く


@pytest.mark.unit
def test_build_model_from_registry() -> None:
    m = build_model({"kind": "logreg"}, seed=7)
    assert m.get_params()["random_state"] == 7  # seed 配線（決定的）
    assert m.get_params()["max_iter"] == 1000  # 落ちない安全既定は焼き込み
    over = build_model({"kind": "logreg", "max_iter": 50}, seed=0)
    assert over.get_params()["max_iter"] == 50  # params は sklearn へ素通し（上書き）


@pytest.mark.unit
def test_build_model_unknown() -> None:
    assert "logreg" in MODELS  # レジストリに既定モデルが載る
    with pytest.raises(ValueError, match="未知のモデル"):
        build_model({"kind": "nope"}, seed=0)


@pytest.mark.unit
def test_build_model_task_mismatch() -> None:
    # 回帰モデルを分類 task に使うと config 段階で止まる（ModelEntry.task で検査）。
    assert MODELS["ridge"].task == "regression"
    with pytest.raises(ValueError, match="regression 用"):
        build_model({"kind": "ridge"}, seed=0, task="classification")
    # task 一致・task=None は通る（互換）。
    assert build_model({"kind": "ridge"}, seed=0, task="regression") is not None
    assert build_model({"kind": "ridge"}, seed=0) is not None


@pytest.mark.unit
def test_build_model_multiclass_uses_classification_models() -> None:
    # 多クラスもモデル種は classification（クラス数は fit 時のラベルで決まる）→ task="multiclass" で分類モデルが通る。
    assert build_model({"kind": "logreg"}, seed=0, task="multiclass") is not None
    # 回帰モデルは multiclass でも止まる（classification へ正規化した上で不一致）。
    with pytest.raises(ValueError, match="regression 用"):
        build_model({"kind": "ridge"}, seed=0, task="multiclass")


@pytest.mark.integration
def test_dummy_returns_prior_probabilities() -> None:
    # 陽性 2・陰性 8（陽性率 0.2）の不均衡データ → strategy="prior"（既定）の predict_proba は
    # 全行 [陰性 0.8, 陽性 0.2]（事前確率＝データ構成から厳密に導出・入力 X には依存しない）。
    from sklearn.dummy import DummyClassifier

    x = np.arange(10, dtype=float).reshape(-1, 1)
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    model = build_model({"kind": "dummy"}, seed=0, task="classification")
    assert isinstance(model, DummyClassifier)
    assert model.get_params()["strategy"] == "prior"  # 既定＝事前確率（predict_proba を持つ）
    model.fit(x, y)
    proba = model.predict_proba(x)
    np.testing.assert_allclose(proba[:, 0], 0.8)  # classes_=[0,1] → 列 0 は陰性 8/10
    np.testing.assert_allclose(proba[:, 1], 0.2)  # 列 1 は陽性 2/10


@pytest.mark.unit
def test_dummy_task_check_and_strategy_override() -> None:
    # 分類ベースライン：task="classification" は通る・task="regression" は config 段階で止まる（既存の task 検査）。
    assert MODELS["dummy"].task == "classification"
    assert build_model({"kind": "dummy"}, seed=0, task="classification") is not None
    with pytest.raises(ValueError, match="classification 用"):
        build_model({"kind": "dummy"}, seed=0, task="regression")
    # strategy は params で上書き可（sklearn へ素通し）。
    over = build_model({"kind": "dummy", "strategy": "most_frequent"}, seed=0)
    assert over.get_params()["strategy"] == "most_frequent"
    # stratified/uniform は乱数を使う → random_state=seed を配線（seed 固定なのに再現しない罠を防ぐ）。
    strat = build_model({"kind": "dummy", "strategy": "stratified"}, seed=42)
    assert strat.get_params()["random_state"] == 42


@pytest.mark.integration
def test_dummy_reg_predicts_mean() -> None:
    # y=[0,10,0,10] → strategy="mean"（既定）は平均 (0+10+0+10)/4 = 5 を全行返す（構成から導出）。
    from sklearn.dummy import DummyRegressor

    x = np.arange(4, dtype=float).reshape(-1, 1)
    y = np.array([0.0, 10.0, 0.0, 10.0])
    model = build_model({"kind": "dummy_reg"}, seed=0, task="regression")
    assert isinstance(model, DummyRegressor)
    assert MODELS["dummy_reg"].task == "regression"
    model.fit(x, y)
    np.testing.assert_allclose(model.predict(x), 5.0)


@pytest.mark.unit
def test_to_numpy_keeps_sparse_sparse() -> None:
    # 疎行列を密化しない：tfidf の大語彙（例 50k 語 × 50 万行）を toarray すると OOM になる。
    # 登録モデル（logreg・木・LightGBM）はすべて scipy 疎を直接受けるので、疎はそのまま通す。
    x = sp.csr_matrix(np.eye(3))
    out = _to_numpy(x)
    assert sp.issparse(out)  # 疎のまま（密 ndarray に展開しない）
    assert hasattr(out, "toarray")
    assert not isinstance(out, np.ndarray)
    assert out.shape == (3, 3)  # 中身は変えない（3×3 の単位行列のまま）
    np.testing.assert_array_equal(out.toarray(), np.eye(3))


# --- 数値前処理エンコーダ（T-0054：scale / impute / missing_flags）。期待値はテストデータの構成から導出。 ---


def _encoder_of(encode_spec: dict[str, object]) -> Any:
    """encode 節 1 個から ColumnTransformer 内の sklearn エンコーダ本体を取り出す（既存テストと同じ経路）。

    戻りは sklearn の変換器（fit_transform を持つ）だが、レジストリ工場の戻りは object 型なので Any で受ける。
    """
    spec = {"features": [_COLS], "encode": [encode_spec]}
    return build_estimator(spec, _model(), seed=0).named_steps["encode"].transformers[0][1]


@pytest.mark.integration
def test_scale_fixes_nan_hole_for_linear_model() -> None:
    # 穴の対比：columns 素通しだけだと NaN で logreg の fit が落ち、scale を挟むと fit/predict が通る。
    df = pl.DataFrame({"x": [0.0, 10.0, None, 0.0, 10.0, None, 0.0, 10.0]})  # polars null → to_numpy で NaN
    y = np.array([0, 1, 0, 0, 1, 1, 0, 1])
    bare = {"features": [{"kind": "columns", "columns": ["x"]}]}
    with pytest.raises(ValueError, match="NaN"):  # sklearn の入力検査（LogisticRegression は NaN を受けない）
        build_estimator(bare, _model(), seed=0).fit(df, y)
    scaled = {**bare, "encode": [{"kind": "scale", "columns": ["x"]}]}
    est = build_estimator(scaled, _model(), seed=0)
    est.fit(df, y)  # 中央値埋め＋標準化で NaN 穴が塞がる
    assert est.predict(df).shape == (8,)


@pytest.mark.unit
def test_scale_standardizes_and_imputes_median() -> None:
    # 構成：観測値 [1,2,9]（中央値 2 ≠ 平均 4）＋ NaN 1 個。median 埋めなら NaN 行は観測値 2 の行と同じ値に。
    # mean 埋めなら 4 で別値＝この一致で「median を使う」ことを判別する（mean/var 検査だけでは両者を区別不可）。
    tr = _encoder_of({"kind": "scale", "columns": ["x"]})
    x = np.array([[1.0], [2.0], [np.nan], [9.0]])
    out = tr.fit_transform(x)
    assert not np.isnan(out).any()  # NaN は埋まる
    assert out.mean() == pytest.approx(0.0)  # StandardScaler の定義（平均 0）
    assert out.var() == pytest.approx(1.0)  # StandardScaler の定義（分散 1）
    assert out[2, 0] == pytest.approx(
        out[1, 0]
    )  # NaN 行は median=2 で埋まり、観測値 2 の行と一致（mean 埋めなら不一致）


@pytest.mark.unit
def test_impute_median_default_and_mean_override() -> None:
    # 構成：[1, 2, NaN, 9] → 中央値 2（既定）・平均 (1+2+9)/3 = 4（strategy=mean を params で上書き）。
    x = np.array([[1.0], [2.0], [np.nan], [9.0]])
    med = _encoder_of({"kind": "impute", "columns": ["x"]})
    assert med.fit_transform(x)[2, 0] == pytest.approx(2.0)  # 既定 = median
    mean = _encoder_of({"kind": "impute", "columns": ["x"], "strategy": "mean"})
    assert mean.fit_transform(x)[2, 0] == pytest.approx(4.0)  # strategy は sklearn へ素通し
    np.testing.assert_allclose(med.fit_transform(x)[[0, 1, 3], 0], [1.0, 2.0, 9.0])  # 観測値は変えない


@pytest.mark.unit
def test_missing_flags_marks_cells_and_keeps_all_columns() -> None:
    # 構成：列 a は欠損なし・列 b は行 0,2 が欠損。features="all" なので出力は入力と同じ 2 列（a の列も出る）。
    tr = _encoder_of({"kind": "missing_flags", "columns": ["a", "b"]})
    x = np.array([[1.0, np.nan], [2.0, 3.0], [4.0, np.nan]])
    out = np.asarray(tr.fit_transform(x), dtype=np.int64)
    assert out.shape == (3, 2)  # 列数一致（既定 features="missing-only" なら 1 列になるはず）
    np.testing.assert_array_equal(out, [[0, 1], [0, 0], [0, 1]])  # 欠損セルだけ 1


@pytest.mark.integration
def test_tfidf_output_reaching_model_stays_sparse() -> None:
    # tfidf 入り config の 3 段 Pipeline が fit まで通り、model 直前（encode→to_numpy）の出力が疎のままなこと。
    rng = np.random.default_rng(0)
    vocab = [f"w{k}" for k in range(30)]  # 疎になる程度の語彙
    rows = [" ".join(rng.choice(vocab, size=4)) for _ in range(100)]
    df = pl.DataFrame({"txt": rows})
    y = np.array([1.0 if "w0" in t else 0.0 for t in rows])  # w0 の有無で決まる
    spec = {"features": [{"kind": "columns", "columns": ["txt"]}], "encode": [{"kind": "tfidf", "columns": "txt"}]}
    est = build_estimator(spec, _model(), seed=0)
    est.fit(df, y)  # 疎のままでも logreg が受けるので end-to-end で落ちない
    reaching_model = est[:-1].transform(df)  # model 直前の出力（to_numpy 通過後）
    assert sp.issparse(reaching_model)  # 密化されていない（OOM 回避の核心）
    assert reaching_model.shape[0] == 100  # 行数は入力どおり
    assert est.predict_proba(df).shape == (100, 2)


# --- 確率較正（T-0060：calibrate を model に被せる拡張ポイント・tune と同じ流儀）。 ---


@pytest.mark.unit
def test_build_model_with_calibrate_wraps_and_wires_seed() -> None:
    # calibrate 節があれば model を CalibratedClassifierCV で包む。内側 cv は seed 付き StratifiedKFold（決定的）。
    m = build_model({"kind": "logreg", "calibrate": {"method": "isotonic", "cv": 4}}, seed=5)
    assert isinstance(m, CalibratedClassifierCV)
    assert m.method == "isotonic"  # method は spec から素通し
    assert type(m.estimator) is LogisticRegression
    assert m.estimator.get_params()["random_state"] == 5  # "calibrate" は model の params に混ざらない
    inner = m.cv
    assert isinstance(inner, StratifiedKFold)
    assert (inner.n_splits, inner.shuffle, inner.random_state) == (4, True, 5)


@pytest.mark.unit
def test_build_model_calibrate_defaults() -> None:
    # 既定：method="sigmoid"・cv=3（spec が空でも seed だけで決定的に組める）。
    m = build_model({"kind": "logreg", "calibrate": {}}, seed=3)
    assert isinstance(m, CalibratedClassifierCV)
    assert m.method == "sigmoid"
    assert isinstance(m.cv, StratifiedKFold)
    assert (m.cv.n_splits, m.cv.shuffle, m.cv.random_state) == (3, True, 3)


@pytest.mark.unit
def test_build_model_without_calibrate_is_unchanged() -> None:
    # calibrate 無しの spec は従来どおり素の model（包まれない＝既存挙動は不変）。
    model = build_model({"kind": "logreg"}, seed=0)
    assert type(model) is LogisticRegression


@pytest.mark.unit
def test_build_model_tune_then_calibrate_order() -> None:
    # 併用時は tuned を包む（tune→calibrate の順）：外側=CalibratedClassifierCV・内側=SearchCV・その中に素の model。
    spec = {"kind": "logreg", "tune": {"param_grid": {"C": [0.1, 1.0]}}, "calibrate": {"cv": 3}}
    m = build_model(spec, seed=2)
    assert isinstance(m, CalibratedClassifierCV)
    assert isinstance(m.estimator, RandomizedSearchCV)  # tuner 省略 → 既定 random
    assert type(m.estimator.estimator) is LogisticRegression
    assert m.estimator.estimator.get_params()["random_state"] == 2  # "tune"/"calibrate" は params に混ざらない


@pytest.mark.unit
def test_calibrate_unknown_key_fails_loud() -> None:
    # calibrate の未知キー（typo）は黙って既定に落とさず TypeError で即死（build_tuned と対称・fail-loud）。
    # "metod" は typo なので CalibratedClassifierCV の未知 kwarg として落ちる（isotonic のつもりが sigmoid、を防ぐ）。
    with pytest.raises(TypeError):
        build_model({"kind": "logreg", "calibrate": {"metod": "isotonic"}}, seed=0)


@pytest.mark.unit
def test_calibrate_on_regression_model_rejected_at_config() -> None:
    # 確率較正は predict_proba が要る＝分類のみ。回帰モデルに calibrate を付けたら fit を待たず config 段で止める。
    with pytest.raises(ValueError, match="calibrate は分類のみ"):
        build_model({"kind": "ridge", "calibrate": {}}, seed=0, task="regression")


@pytest.mark.integration
def test_calibrated_model_runs_through_run_cv() -> None:
    # 較正モデルを model 段のまま run_cv へ → 外=run_cv の fold・内=CalibratedClassifierCV の cv の nested 構造で
    # fit/predict が通る（二値）。構成：特徴 1 本の線形分離データ（class0 は x∈[-3,-1]・class1 は x∈[1,3]・
    # クラス均衡・x が 0 対称）→ 較正はスコアの単調変換＋対称性で p(x=0)=0.5 → 閾値 0.5 で oof 全問正解。
    x = pl.DataFrame({"f": np.concatenate([np.linspace(-3.0, -1.0, 30), np.linspace(1.0, 3.0, 30)])})
    y = np.array([0.0] * 30 + [1.0] * 30, dtype=np.float64)
    calibrated = build_model({"kind": "logreg", "calibrate": {"cv": 3}}, seed=0)
    splits = list(StratifiedKFold(n_splits=3, shuffle=True, random_state=0).split(np.zeros(len(y)), y))
    result = cv.run_cv(calibrated, x, y, splits)
    assert result.oof_mask.all()
    assert result.oof_metrics["accuracy"] == 1.0  # 分離データ＝oof 全問正解（構成から導出）
    # cv._predict がそのまま使える＝CalibratedClassifierCV が classes_ / predict_proba を持つ。
    fitted = result.estimators[0]
    assert np.array_equal(np.asarray(fitted.classes_), np.array([0.0, 1.0]))  # type: ignore[attr-defined]
    pred = cv._predict(fitted, x, "proba")
    assert pred.shape == (60,)  # 二値 → 陽性（ラベル 1）の確率 1 列
    assert ((0.0 <= pred) & (pred <= 1.0)).all()


# --- 特徴選択段（SELECTORS・select 節・T-0064） ---


@pytest.mark.unit
def test_variance_threshold_drops_constant_column() -> None:
    # 構成：列0 は全行 7.0（分散 0）・列1 は 0..9（分散 > 0）→ 既定 threshold=0.0 で定数列だけ落ちる（構成から）。
    x = np.column_stack([np.full(10, 7.0), np.arange(10, dtype=np.float64)])
    sel = SELECTORS.build({"kind": "variance_threshold"}, seed=0)
    out = sel.fit_transform(x)
    assert out.shape == (10, 1)  # 2 列 → 定数列が落ちて 1 列
    assert np.array_equal(out[:, 0], np.arange(10, dtype=np.float64))  # 残るのは変動列


@pytest.mark.unit
def test_selectkbest_picks_correlated_column() -> None:
    # 構成：列0 = y ＋微小ジッタ（class0 は [0,0.1]・class1 は [1,1.1] ＝クラス間差 1 ≫ クラス内幅 0.1 → F 値が巨大）・
    # 列1 = seed 固定の乱数（y と無関係 → F 値は O(1)）→ k=1 で選ばれるのは列0（get_support は構成から [True, False]）。
    # score_func は文字列 "f_classif" が sklearn 関数に写像される。
    rng = np.random.default_rng(0)
    y = np.array([0, 1] * 10)
    x = np.column_stack([y.astype(np.float64) + 0.1 * np.linspace(0.0, 1.0, 20), rng.normal(size=20)])
    sel = SELECTORS.build({"kind": "selectkbest", "k": 1, "score_func": "f_classif"}, seed=0)
    sel.fit(x, y)
    assert list(sel.get_support()) == [True, False]
    with pytest.raises(ValueError, match="未知の score_func"):  # typo は黙って既定に落とさない（fail-loud）
        SELECTORS.build({"kind": "selectkbest", "score_func": "nope"}, seed=0)


@pytest.mark.unit
def test_selectkbest_mutual_info_regression_registered_and_seeded() -> None:
    # G9：mutual_info_regression が score_func 文字列で選べる（回帰の MI 特徴選択を config から）。
    # 構成：列0 は y と決定的な単調関係（y=x0³ ＝ MI 大）・列1 は y と独立の seed 固定乱数（MI ≈ 0）
    # → k=1 で選ばれるのは列0（構成から導出・実装出力のコピペではない）。
    from functools import partial

    from sklearn.feature_selection import mutual_info_regression

    rng = np.random.default_rng(0)
    x0 = np.linspace(0.0, 1.0, 60)
    x = np.column_stack([x0, rng.normal(size=60)])
    y = x0**3  # 連続値（回帰）＝列0 の決定的な単調変換
    sel = SELECTORS.build({"kind": "selectkbest", "k": 1, "score_func": "mutual_info_regression"}, seed=7)
    sel.fit(x, y)
    assert list(sel.get_support()) == [True, False]
    # seed 決定化を構造で確認（2 回一致は非決定の証明にならない＝タイ破りノイズが順序を変えないことがある）。
    # 登録 score_func は mutual_info_regression を random_state=seed で焼き込んだ partial＝seed 配線を外すと必ず崩れる。
    score_func = sel.score_func
    assert isinstance(score_func, partial)
    assert score_func.func is mutual_info_regression
    assert score_func.keywords == {"random_state": 7}  # seed が焼き込まれている（決定化の構造的担保）


@pytest.mark.unit
def test_from_model_estimator_spec_supports_regression() -> None:
    # from_model の estimator を model spec で選べる＝config から回帰選択器も組める（既定 logreg は連続 y で落ちる）。
    from sklearn.feature_selection import SelectFromModel

    rng = np.random.default_rng(0)
    x = np.column_stack([np.linspace(0.0, 1.0, 20), rng.normal(size=20)])
    y = 3.0 * x[:, 0]  # 連続値（回帰）＝列0 だけが効く
    sel = SELECTORS.build({"kind": "from_model", "estimator": {"kind": "ridge"}}, seed=0)
    assert isinstance(sel, SelectFromModel)
    sel.fit(x, y)  # 回帰モデル（ridge）なので連続 y で落ちない
    assert bool(sel.get_support()[0])  # 効く列0 が選ばれる（構成から＝coef が大きい）
    # 既定（estimator 未指定）は分類器＝連続 y では sklearn が落とす（回帰は estimator 指定が要る、を固定）。
    with pytest.raises(ValueError):
        SELECTORS.build({"kind": "from_model"}, seed=0).fit(x, y)


@pytest.mark.unit
def test_build_estimator_inserts_select_between_to_numpy_and_model() -> None:
    # select: 付き spec → "select" が to_numpy と model の間に入る。select 無し → steps は従来どおり（回帰なし）。
    spec = {"features": [_COLS], "select": {"kind": "variance_threshold"}}
    est = build_estimator(spec, _model(), seed=0)
    assert [n for n, _ in est.steps] == ["features", "to_numpy", "select", "model"]
    with_encode = build_estimator({**spec, "encode": [{"kind": "onehot", "columns": ["c"]}]}, _model(), seed=0)
    assert [n for n, _ in with_encode.steps] == ["features", "encode", "to_numpy", "select", "model"]
    plain = build_estimator({"features": [_COLS]}, _model(), seed=0)
    assert [n for n, _ in plain.steps] == ["features", "to_numpy", "model"]  # "select" が入らない


@pytest.mark.integration
def test_select_estimator_runs_through_run_cv() -> None:
    # リーク無しの結線：select 付き estimator を run_cv へ → clone-per-fold で選択も fold の train でだけ fit。
    # 構成：f は線形分離（class0 x∈[-3,-1]・class1 x∈[1,3]）・n は seed 固定の乱数（y と無関係）。
    # selectkbest(k=1, f_classif) は F 値最大の f を選ぶ（分離データ＝クラス間分散 ≫ クラス内分散・構成から）
    # → logreg は f だけで学習 → 分離データ＝oof 全問正解（accuracy 1.0）。
    rng = np.random.default_rng(0)
    x = pl.DataFrame(
        {
            "f": np.concatenate([np.linspace(-3.0, -1.0, 30), np.linspace(1.0, 3.0, 30)]),
            "n": rng.normal(size=60),
        }
    )
    y = np.array([0.0] * 30 + [1.0] * 30, dtype=np.float64)
    spec = {
        "features": [{"kind": "columns", "columns": ["f", "n"]}],
        "select": {"kind": "selectkbest", "k": 1, "score_func": "f_classif"},
    }
    est = build_estimator(spec, _model(), seed=0)
    splits = list(StratifiedKFold(n_splits=3, shuffle=True, random_state=0).split(np.zeros(len(y)), y))
    result = cv.run_cv(est, x, y, splits)
    assert result.oof_mask.all()
    assert result.oof_metrics["accuracy"] == 1.0  # 分離列だけ残る＝oof 全問正解（構成から導出）
    # 各 fold の select 段が f（列0）を選んでいる（Pipeline が fit(y) を伝えた証拠・train のみで fit）。
    for fitted in result.estimators:
        # estimators は object 型で返る（fold 別の学習済み Pipeline）＝select 段へは動的にアクセスする。
        support = fitted.named_steps["select"].get_support()  # type: ignore[attr-defined]
        assert list(support) == [True, False]


# --- target_transform（T-0081：log1p を TransformedTargetRegressor で包む・回帰のみ・pickle 可） ---


@pytest.mark.unit
def test_target_transform_log1p_wraps_regressor_with_module_functions() -> None:
    # target_transform: log1p → TransformedTargetRegressor(func=np.log1p, inverse_func=np.expm1) で包む。
    # func/inverse は**モジュール関数**（lambda 不可）＝pickle で名前参照になり save/load 往復できる。
    m = build_model({"kind": "ridge", "target_transform": "log1p"}, seed=5, task="regression")
    assert isinstance(m, TransformedTargetRegressor)
    assert m.func is np.log1p  # モジュール関数そのもの（部分適用や lambda で包まない）
    assert m.inverse_func is np.expm1
    assert type(m.regressor) is Ridge
    assert m.regressor.get_params()["random_state"] == 5  # seed 配線は内側の回帰器へ
    assert "target_transform" not in m.regressor.get_params()  # 配線キーは params に混ざらない


@pytest.mark.unit
def test_target_transform_fails_loud_on_classification_and_unknown() -> None:
    # 逆変換して原スケールで測る仕組み＝回帰のみ。分類モデルに付けたら fit を待たず config 段で止める。
    with pytest.raises(ValueError, match="回帰のみ"):
        build_model({"kind": "logreg", "target_transform": "log1p"}, seed=0)
    # 未知の変換名（typo）は黙って素通ししない（fail-loud）。
    with pytest.raises(ValueError, match="未知の target_transform"):
        build_model({"kind": "ridge", "target_transform": "sqrt"}, seed=0)


@pytest.mark.unit
def test_target_transform_absent_is_unchanged() -> None:
    # target_transform 無しの spec は従来どおり素の model（包まれない＝既存挙動は不変）。
    assert type(build_model({"kind": "ridge"}, seed=0)) is Ridge


@pytest.mark.unit
def test_target_transform_wraps_tuned_model_outermost() -> None:
    # tune 併用時は tuned を包む（TTR が最外・param_grid のキーは素の名前のまま書ける）。
    spec = {"kind": "ridge", "target_transform": "log1p", "tune": {"param_grid": {"alpha": [0.1, 1.0]}}}
    m = build_model(spec, seed=2)
    assert isinstance(m, TransformedTargetRegressor)
    assert isinstance(m.regressor, RandomizedSearchCV)  # tuner 省略 → 既定 random
    assert type(m.regressor.estimator) is Ridge


@pytest.mark.integration
def test_target_transform_predicts_in_original_scale() -> None:
    # 構成：y = expm1(0.5 + 1.2 x)（正・右に歪む）→ log1p(y) = 0.5 + 1.2 x は x の厳密な一次式。
    # ridge(alpha≈0) は変換後空間でこの直線を復元し、TTR の逆変換（expm1）で予測は**原スケール**の y に一致する。
    x = np.linspace(0.0, 3.0, 50).reshape(-1, 1)
    y = np.expm1(0.5 + 1.2 * x[:, 0])
    m = build_model({"kind": "ridge", "alpha": 1e-8, "target_transform": "log1p"}, seed=0, task="regression")
    assert isinstance(m, TransformedTargetRegressor)
    m.fit(x, y)
    np.testing.assert_allclose(m.predict(x), y, rtol=1e-4)  # rmse 等を原スケールで測れる（逆変換は TTR が背負う）


@pytest.mark.integration
def test_target_transform_model_save_load_roundtrip(tmp_path: Any) -> None:
    # log1p 包みの Pipeline が既存 models.py の pickle 経路で save/load 往復し、予測が一致する
    # （func/inverse がモジュール関数＝pickle 可、の実測）。
    from harness.ds.models import load_model, save_model

    df = pl.DataFrame({"x": np.linspace(0.0, 3.0, 30)})
    y = np.expm1(0.5 + 1.0 * df["x"].to_numpy())
    model = build_model({"kind": "ridge", "alpha": 1e-8, "target_transform": "log1p"}, seed=0, task="regression")
    est = build_estimator({"features": [{"kind": "columns", "columns": ["x"]}]}, model, seed=0)
    est.fit(df, y)
    save_model(tmp_path, est, name="ttr", work="T-0081", feature_names=["x"])
    loaded, record = load_model(tmp_path, name="ttr", work="T-0081")
    assert record.format == "pickle"
    np.testing.assert_allclose(
        loaded.predict(df),  # type: ignore[attr-defined]
        est.predict(df),
    )


# --- svd エンコーダ（T-0081：TruncatedSVD・疎対応の次元圧縮＝テキスト経路の穴埋め） ---


@pytest.mark.unit
def test_svd_encoder_registered_and_seeded() -> None:
    # ENCODERS.build で TruncatedSVD がそのまま出る（impute/scale を前置しない＝疎を密化しない）。
    svd = ENCODERS.build({"kind": "svd", "columns": ["a", "b"], "n_components": 2}, seed=9)
    assert isinstance(svd, TruncatedSVD)
    assert svd.get_params()["n_components"] == 2  # n_components は必須（既定 2 を黙って使わせない）
    assert svd.get_params()["random_state"] == 9  # 決定的：seed 配線（randomized SVD の乱数）
    over = ENCODERS.build({"kind": "svd", "columns": ["a"], "n_components": 1, "n_iter": 7}, seed=0)
    assert over.get_params()["n_iter"] == 7  # params は sklearn へ素通し


@pytest.mark.integration
def test_tfidf_svd_model_chain_fits_sparse() -> None:
    # tfidf→svd→model の直列が**疎のまま** fit する：svd 直前（tfidf 出力）が scipy 疎で、
    # TruncatedSVD がそれを密化せず受けて n_components 列に落とす（PCA には無い疎対応＝この部品の存在理由）。
    rng = np.random.default_rng(0)
    vocab = [f"w{k}" for k in range(30)]
    rows = [" ".join(rng.choice(vocab, size=4)) for _ in range(100)]
    txt = pl.Series("txt", rows)
    y = np.array([1.0 if "w0" in t else 0.0 for t in rows])
    from sklearn.pipeline import Pipeline as SkPipeline

    chain = SkPipeline(
        [
            ("tfidf", ENCODERS.build({"kind": "tfidf", "columns": "txt"}, seed=0)),
            ("svd", ENCODERS.build({"kind": "svd", "columns": "txt", "n_components": 5}, seed=0)),
            ("model", build_model({"kind": "logreg"}, seed=0)),
        ]
    )
    chain.fit(txt, y)
    assert sp.issparse(chain[:1].transform(txt))  # svd の入力（tfidf 出力）は疎のまま（密化しない）
    reduced = chain[:2].transform(txt)
    assert reduced.shape == (100, 5)  # 列数が n_components に落ちる
    assert chain.predict_proba(txt).shape == (100, 2)


@pytest.mark.integration
def test_svd_in_encode_stage_reduces_numeric_columns() -> None:
    # config の入口（encode 節）からも使える：数値 3 列 → svd(n_components=2) → model 直前は 2 列。
    rng = np.random.default_rng(1)
    df = pl.DataFrame({"a": rng.normal(size=40), "b": rng.normal(size=40), "c": rng.normal(size=40)})
    y = (df["a"].to_numpy() > 0).astype(np.float64)
    spec = {
        "features": [{"kind": "columns", "columns": ["a", "b", "c"]}],
        "encode": [{"kind": "svd", "columns": ["a", "b", "c"], "n_components": 2}],
    }
    est = build_estimator(spec, _model(), seed=0)
    est.fit(df, y)
    assert est[:-1].transform(df).shape == (40, 2)  # model に届くのは n_components 列


# --- poisson_reg / quantile_reg（T-0081：件数・分位型ターゲットの線形基準） ---


@pytest.mark.unit
def test_poisson_and_quantile_reg_registered_as_regression() -> None:
    from sklearn.linear_model import PoissonRegressor, QuantileRegressor

    assert MODELS["poisson_reg"].task == "regression"
    assert MODELS["quantile_reg"].task == "regression"
    assert isinstance(build_model({"kind": "poisson_reg"}, seed=0, task="regression"), PoissonRegressor)
    q = build_model({"kind": "quantile_reg", "quantile": 0.9, "alpha": 0.0}, seed=0, task="regression")
    assert isinstance(q, QuantileRegressor)
    assert q.get_params()["quantile"] == 0.9  # 分位は quantile=（alpha は L1 正則化・sklearn の語彙）
    assert q.get_params()["alpha"] == 0.0
    # 回帰モデル×分類 task は config 段階で止まる（既存の task 検査に載る）。
    with pytest.raises(ValueError, match="regression 用"):
        build_model({"kind": "poisson_reg"}, seed=0, task="classification")
    with pytest.raises(ValueError, match="regression 用"):
        build_model({"kind": "quantile_reg"}, seed=0, task="classification")


@pytest.mark.integration
def test_poisson_reg_beats_dummy_on_poisson_counts() -> None:
    # 構成：λ(x) = exp(0.3 + 1.0 x)・y ~ Poisson(λ)（seed 固定）。ポアソン回帰は生成構造（対数リンクの一次式）
    # そのものを当てられるので、x を見ない定数平均（dummy_reg）より train の poisson deviance が必ず小さい
    # （GLM の最尤解は定数モデルを含む集合の最適＝構成から導出。alpha≈0 で正則化の縮みを消す）。
    from sklearn.dummy import DummyRegressor
    from sklearn.linear_model import PoissonRegressor
    from sklearn.metrics import mean_poisson_deviance

    rng = np.random.default_rng(0)
    x = rng.uniform(0.0, 2.0, size=400).reshape(-1, 1)
    y = rng.poisson(np.exp(0.3 + 1.0 * x[:, 0])).astype(np.float64)
    poisson = build_model({"kind": "poisson_reg", "alpha": 1e-6}, seed=0, task="regression")
    dummy = build_model({"kind": "dummy_reg"}, seed=0, task="regression")
    assert isinstance(poisson, PoissonRegressor)
    assert isinstance(dummy, DummyRegressor)
    poisson.fit(x, y)
    dummy.fit(x, y)
    assert mean_poisson_deviance(y, poisson.predict(x)) < mean_poisson_deviance(y, dummy.predict(x))


@pytest.mark.integration
def test_quantile_reg_prediction_covers_requested_quantile() -> None:
    # 構成：y = 0..99 の等間隔 100 点・特徴は定数 0（切片だけのモデル）・alpha=0（無正則化）。
    # pinball 損失の切片最適解は y の標本分位（分位回帰の定義）＝予測以下の割合が quantile に一致する
    # （q=0.9 → 最適解は順序統計量 y_(90)〜y_(91) の間＝被覆率 0.90〜0.91・構成から導出）。
    from sklearn.linear_model import QuantileRegressor

    x = np.zeros((100, 1))
    y = np.linspace(0.0, 99.0, 100)
    preds = {}
    for q in (0.1, 0.5, 0.9):
        m = build_model({"kind": "quantile_reg", "quantile": q, "alpha": 0.0}, seed=0, task="regression")
        assert isinstance(m, QuantileRegressor)
        m.fit(x, y)
        preds[q] = float(m.predict(x)[0])
        coverage = float((y <= preds[q]).mean())
        assert abs(coverage - q) <= 0.02  # 予測が指定分位側に寄る（被覆率＝分位）
    assert preds[0.1] < preds[0.5] < preds[0.9]  # 分位の単調性（構成から自明）
