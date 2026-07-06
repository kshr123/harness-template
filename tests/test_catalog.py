"""部品カタログ（BLOCKS/ENCODERS）の発見性の検査。

レジストリの全項目に説明文（docstring）があることを固定する。説明文が無い＝一覧に載れない
＝エージェントが元コードを読まずに使えない＝「部品は入口まで作って完了」（DEC-0009）に反する。
"""

from __future__ import annotations

import pytest

from harness.ds.cli import (
    _data_blocks,
    _data_encoders,
    _data_metrics,
    _data_models,
    _data_selectors,
    _data_tuners,
    _data_unsupervised,
)
from harness.ds.eval import METRICS
from harness.ds.features import BLOCKS
from harness.ds.pipeline import ENCODERS, MODELS

pytestmark = pytest.mark.unit


# レジストリの項目は Entry。説明文（description）は register が factory 自前の docstring 1 行目から導出し、
# 空なら登録時に ValueError（親 docstring は継承しない＝test_registry.py で固定）。ここは全項目に
# description が実在することをカタログ視点で確かめる（Entry の __doc__ は常に真なので使わない）。
def test_blocks_have_docstrings() -> None:
    for kind, entry in BLOCKS.items():
        assert entry.description, f"BLOCKS['{kind}'] に説明文が無い（自前 docstring か description= が必須・DEC-0009）"


def test_encoders_have_docstrings() -> None:
    for kind, entry in ENCODERS.items():
        assert entry.description, f"ENCODERS['{kind}'] に説明文が無い（カタログに載れない）"


def test_selectors_have_docstrings() -> None:
    from harness.ds.pipeline import SELECTORS

    for kind, entry in SELECTORS.items():
        assert entry.description, f"SELECTORS['{kind}'] に説明文が無い（カタログに載れない）"


def test_models_have_docstrings_and_task() -> None:
    for kind, entry in MODELS.items():
        assert entry.description, f"MODELS['{kind}'] に説明文が無い（カタログに載れない）"
        assert entry.task in ("classification", "regression"), f"MODELS['{kind}'] の task が不正"


def test_ts_models_have_docstrings() -> None:
    from harness.ds.forecast import TS_MODELS

    for kind, entry in TS_MODELS.items():
        assert entry.description, f"TS_MODELS['{kind}'] に説明文が無い（カタログに載れない）"


def test_clusterers_have_docstrings() -> None:
    from harness.ds.unsupervised import CLUSTERERS

    for kind, entry in CLUSTERERS.items():
        assert entry.description, f"CLUSTERERS['{kind}'] に説明文が無い（カタログに載れない）"


def test_dimred_and_anomaly_have_docstrings() -> None:
    from harness.ds.unsupervised import ANOMALY, DIMRED

    for name, registry in (("DIMRED", DIMRED), ("ANOMALY", ANOMALY)):
        for kind, entry in registry.items():
            assert entry.description, f"{name}['{kind}'] に説明文が無い（カタログに載れない）"


def test_metrics_have_descriptions() -> None:
    # 指標も config の語彙（thresholds）＝カタログ対象。説明文が無いと一覧に載れない。
    for name, metric in METRICS.items():
        assert metric.description, f"METRICS['{name}'] に説明文が無い（カタログに載れない）"


def test_catalog_commands_run(capsys: pytest.CaptureFixture[str]) -> None:
    _data_blocks()
    _data_encoders()
    _data_models()
    _data_metrics()
    _data_unsupervised()
    _data_selectors()
    _data_tuners()
    out = capsys.readouterr().out
    # レジストリの項目が一覧に出る（エージェントが1コマンドで発見できる）。
    assert "columns" in out
    assert "onehot" in out
    assert "target" in out
    assert "anomaly_score" in out  # (B) 教師なしのエンコーダが自動で載る
    assert "svd" in out  # 疎対応の次元圧縮エンコーダ（T-0081・data encoders）
    assert "logreg" in out
    assert "poisson_reg" in out  # 件数ターゲットの線形基準（T-0081・data models）
    assert "quantile_reg" in out  # 分位ターゲットの線形基準（T-0081・data models）
    assert "selectkbest" in out  # 特徴選択カタログ（data selectors）
    assert "variance_threshold" in out
    assert "random" in out  # チューナーカタログ（data tuners）
    assert "halving" in out
    assert "roc_auc" in out  # 指標カタログ
    assert "pinball_q10" in out  # 分位変種（T-0080）が説明つきで載る（DEC-0009）
    assert "timeseries" in out  # 古典時系列（statsmodels 導入環境・all-extras）
    # (A) 教師なしカタログ（3 レジストリ）が data unsupervised に載る。
    for kind in ("pca", "tsne", "kmeans", "gmm", "hdbscan", "iforest", "lof"):
        assert kind in out, f"data unsupervised に {kind} が載っていない"
