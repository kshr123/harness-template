"""pipeline.build_estimator の組み立てとエンコーダ既定の単体テスト（fit しない・構成から導出）。"""

from __future__ import annotations

import pytest
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression

from harness.ds.pipeline import MODELS, build_estimator, build_model

pytestmark = pytest.mark.unit

_COLS = {"kind": "columns", "columns": ["c"]}


def _model() -> LogisticRegression:
    return LogisticRegression(max_iter=1000)


def test_build_estimator_assembles_three_and_two_stages() -> None:
    est = build_estimator({"features": [_COLS], "encode": [{"kind": "onehot", "columns": ["c"]}]}, _model(), seed=0)
    assert [n for n, _ in est.steps] == ["features", "encode", "to_numpy", "model"]
    assert isinstance(est.named_steps["encode"], ColumnTransformer)
    two = build_estimator({"features": [_COLS]}, _model(), seed=0)  # encode 無し → features→to_numpy→model
    assert [n for n, _ in two.steps] == ["features", "to_numpy", "model"]


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


def test_onehot_safe_default_and_override() -> None:
    spec = {"features": [_COLS], "encode": [{"kind": "onehot", "columns": ["c"], "min_frequency": 2}]}
    oh = build_estimator(spec, _model(), seed=0).named_steps["encode"].transformers[0][1]
    assert oh.get_params()["min_frequency"] == 2  # params は sklearn へ素通し（上書き）
    assert oh.get_params()["handle_unknown"] == "infrequent_if_exist"  # 落ちない安全既定は焼き込み


def test_target_encoder_cv_is_seeded_kfold() -> None:
    spec = {"features": [_COLS], "encode": [{"kind": "target", "columns": ["c"], "cv": 3}]}
    te = build_estimator(spec, _model(), seed=7).named_steps["encode"].transformers[0][1]
    kfold = te.get_params()["cv"]
    assert kfold.get_n_splits() == 3  # 非推奨 shuffle/random_state を使わず cv=KFold(seed)
    assert kfold.random_state == 7  # seed 配線（決定的な OOF）


def test_build_model_from_registry() -> None:
    m = build_model({"kind": "logreg"}, seed=7)
    assert m.get_params()["random_state"] == 7  # seed 配線（決定的）
    assert m.get_params()["max_iter"] == 1000  # 落ちない安全既定は焼き込み
    over = build_model({"kind": "logreg", "max_iter": 50}, seed=0)
    assert over.get_params()["max_iter"] == 50  # params は sklearn へ素通し（上書き）


def test_build_model_unknown() -> None:
    assert "logreg" in MODELS  # レジストリに既定モデルが載る
    with pytest.raises(ValueError, match="未知のモデル"):
        build_model({"kind": "nope"}, seed=0)


def test_build_model_task_mismatch() -> None:
    # 回帰モデルを分類 task に使うと config 段階で止まる（ModelEntry.task で検査）。
    assert MODELS["ridge"].task == "regression"
    with pytest.raises(ValueError, match="regression 用"):
        build_model({"kind": "ridge"}, seed=0, task="classification")
    # task 一致・task=None は通る（互換）。
    assert build_model({"kind": "ridge"}, seed=0, task="regression") is not None
    assert build_model({"kind": "ridge"}, seed=0) is not None
