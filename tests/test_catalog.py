"""部品カタログ（BLOCKS/ENCODERS）の発見性の検査。

レジストリの全項目に説明文（docstring）があることを固定する。説明文が無い＝一覧に載れない
＝エージェントが元コードを読まずに使えない＝「部品は入口まで作って完了」（DEC-0009）に反する。
"""

from __future__ import annotations

import pytest

from harness.cli import _data_blocks, _data_encoders, _data_metrics, _data_models, _data_unsupervised
from harness.ds.eval import METRICS
from harness.ds.features import BLOCKS
from harness.ds.pipeline import ENCODERS, MODELS

pytestmark = pytest.mark.unit


def test_blocks_have_docstrings() -> None:
    # cls.__doc__（自前の説明）で判定する。inspect.getdoc は親 FeatureBlock の説明を継承して空振りするため使わない。
    for kind, cls in BLOCKS.items():
        assert cls.__doc__, f"BLOCKS['{kind}'] に自前の docstring が無い（親の継承では入口にならない）"


def test_encoders_have_docstrings() -> None:
    for kind, factory in ENCODERS.items():
        assert factory.__doc__, f"ENCODERS['{kind}'] に docstring が無い（カタログに載れない）"


def test_models_have_docstrings_and_task() -> None:
    for kind, entry in MODELS.items():
        assert entry.factory.__doc__, f"MODELS['{kind}'] の factory に docstring が無い（カタログに載れない）"
        assert entry.task in ("classification", "regression"), f"MODELS['{kind}'] の task が不正"


def test_ts_models_have_docstrings() -> None:
    from harness.ds.forecast import TS_MODELS

    for kind, factory in TS_MODELS.items():
        assert factory.__doc__, f"TS_MODELS['{kind}'] に docstring が無い（カタログに載れない）"


def test_clusterers_have_docstrings() -> None:
    from harness.ds.unsupervised import CLUSTERERS

    for kind, factory in CLUSTERERS.items():
        assert factory.__doc__, f"CLUSTERERS['{kind}'] に docstring が無い（カタログに載れない）"


def test_dimred_and_anomaly_have_docstrings() -> None:
    from harness.ds.unsupervised import ANOMALY, DIMRED

    for name, registry in (("DIMRED", DIMRED), ("ANOMALY", ANOMALY)):
        for kind, factory in registry.items():
            assert factory.__doc__, f"{name}['{kind}'] に docstring が無い（カタログに載れない）"


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
    out = capsys.readouterr().out
    # レジストリの項目が一覧に出る（エージェントが1コマンドで発見できる）。
    assert "columns" in out
    assert "onehot" in out
    assert "target" in out
    assert "anomaly_score" in out  # (B) 教師なしのエンコーダが自動で載る
    assert "logreg" in out
    assert "roc_auc" in out  # 指標カタログ
    assert "timeseries" in out  # 古典時系列（statsmodels 導入環境・all-extras）
    # (A) 教師なしカタログ（3 レジストリ）が data unsupervised に載る。
    for kind in ("pca", "tsne", "kmeans", "gmm", "hdbscan", "iforest", "lof"):
        assert kind in out, f"data unsupervised に {kind} が載っていない"
