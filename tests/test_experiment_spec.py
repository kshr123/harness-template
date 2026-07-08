"""ExperimentSpec（実験 config の型付け・ISS-0007）のテスト。

期待値はすべて config の構成から導く：正しい構造（現行 config.yaml 相当）は通り、
未知キー（typo）・型違い・空の variants/features・範囲外の値は ValidationError になる。
実値のコピー（ハードコード期待値）は書かない（検証するのは「通る/止まる」の構造だけ）。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from harness.ds.experiment import ExperimentSpec

pytestmark = pytest.mark.unit


def _valid_config() -> dict[str, Any]:
    """現行 config.yaml（E-0001）相当の dict。各テストはこれを 1 箇所だけ壊して境界を確かめる。"""
    return {
        "seed": 20260703,
        "n": 2000,
        "n_folds": 5,
        "data": {"kind": "synthetic"},
        "target": "y",
        "model": {"kind": "logreg"},
        "variants": {
            "baseline": {"features": [{"kind": "columns", "columns": ["x1", "x2"]}]},
            "interaction": {
                "features": [
                    {"kind": "columns", "columns": ["x1", "x2"]},
                    {"kind": "interactions", "pairs": [["x1", "x2"]]},
                ]
            },
        },
        "test_mode": {"n": 240, "n_folds": 3},
        "thresholds": {"roc_auc": 0.80},
    }


def test_current_config_shape_validates() -> None:
    # 現行 config.yaml 相当＝そのまま通る（変種 2・thresholds・model.kind が読める）。
    spec = ExperimentSpec.model_validate(_valid_config())
    assert spec.seed == 20260703
    assert spec.model["kind"] == "logreg"
    assert set(spec.variants) == {"baseline", "interaction"}
    assert len(spec.variants["interaction"].features) == 2
    assert spec.thresholds == {"roc_auc": 0.80}
    assert spec.test_mode is not None and spec.test_mode.n == 240 and spec.test_mode.n_folds == 3
    # optional の既定（config に書かなければ既定が入る）。
    assert spec.task == "classification"
    assert spec.id_column == "id"
    assert spec.metrics is None and spec.stratify_by is None and spec.order_by is None


def test_variant_level_model_and_select_are_allowed() -> None:
    # モデル比較の実験は variant 側に model（experiment スキル）・特徴選択は select 節（build_estimator）。
    cfg = _valid_config()
    cfg["variants"]["baseline"]["model"] = {"kind": "ridge"}
    cfg["variants"]["baseline"]["select"] = {"kind": "from_model"}
    spec = ExperimentSpec.model_validate(cfg)
    assert spec.variants["baseline"].model == {"kind": "ridge"}


def test_unknown_top_level_key_typo_rejected() -> None:
    # thresholds の typo（thresold）＝これまで黙って無視されていた実損パターンを起動時に止める。
    cfg = _valid_config()
    cfg["thresold"] = {"roc_auc": 0.80}
    with pytest.raises(ValidationError, match="thresold"):
        ExperimentSpec.model_validate(cfg)


def test_unknown_variant_key_typo_rejected() -> None:
    # variant 内の typo（feature）もネストの extra=forbid で止まる。
    cfg = _valid_config()
    cfg["variants"]["baseline"] = {
        "features": [{"kind": "columns", "columns": ["x1"]}],
        "feature": [{"kind": "columns", "columns": ["x2"]}],
    }
    with pytest.raises(ValidationError, match="feature"):
        ExperimentSpec.model_validate(cfg)


def test_test_mode_unknown_key_rejected() -> None:
    cfg = _valid_config()
    cfg["test_mode"] = {"n": 240, "folds": 3}  # n_folds の typo
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(cfg)


def test_threshold_string_value_rejected() -> None:
    # 合否の閾値が文字列（YAML の引用ミス等）＝float に黙って強制せず止める。
    cfg = _valid_config()
    cfg["thresholds"] = {"roc_auc": "0.80"}
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(cfg)


def test_empty_variants_rejected() -> None:
    cfg = _valid_config()
    cfg["variants"] = {}
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(cfg)


def test_variant_with_empty_features_rejected() -> None:
    cfg = _valid_config()
    cfg["variants"]["baseline"] = {"features": []}
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(cfg)


def test_n_folds_below_two_rejected() -> None:
    # n_folds=1 は交差検証にならない（範囲の下限で止める）。
    cfg = _valid_config()
    cfg["n_folds"] = 1
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(cfg)


def test_data_without_kind_rejected() -> None:
    cfg = _valid_config()
    cfg["data"] = {"table_id": "t1"}  # kind が無い
    with pytest.raises(ValidationError, match="kind"):
        ExperimentSpec.model_validate(cfg)


def test_model_without_kind_rejected() -> None:
    cfg = _valid_config()
    cfg["model"] = {"max_iter": 2000}  # kind が無い
    with pytest.raises(ValidationError, match="kind"):
        ExperimentSpec.model_validate(cfg)


def test_variant_model_without_kind_rejected() -> None:
    cfg = _valid_config()
    cfg["variants"]["baseline"]["model"] = {"max_iter": 2000}
    with pytest.raises(ValidationError, match="kind"):
        ExperimentSpec.model_validate(cfg)


def test_decision_threshold_is_not_a_config_key() -> None:
    # 決定境界は config キーでなく関数引数（run_experiment(..., decision_threshold=)）＝雛形は OOF から選ぶ。
    # config に書いても黙って無視されないよう extra=forbid で起動時に止める（float でも辞書でも同じく拒否）。
    for bad in (0.3, 1.5, {"roc_auc": 0.80}):  # 取り違えの本丸（合否辞書）も含め、キー自体を受け付けない
        cfg = _valid_config()
        cfg["decision_threshold"] = bad
        with pytest.raises(ValidationError):
            ExperimentSpec.model_validate(cfg)


def test_optional_keys_are_captured_not_ignored() -> None:
    # metrics/stratify_by/order_by/id_column は雛形が run_experiment へ流す（黙って無視されない＝ISS-0007 の要点）。
    cfg = _valid_config()
    cfg["metrics"] = ["roc_auc"]
    cfg["id_column"] = "row_id"
    cfg["stratify_by"] = "y"
    spec = ExperimentSpec.model_validate(cfg)
    assert spec.metrics == ["roc_auc"]
    assert spec.id_column == "row_id"
    assert spec.stratify_by == "y"
