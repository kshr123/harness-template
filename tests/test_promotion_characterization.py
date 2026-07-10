"""昇格判定の挙動を固定するテスト（characterization test）。

このファイルは**判定の挙動と記録の構造だけ**を固定し、例外のメッセージ文字列には一切依存しない
（`pytest.raises(ValueError)` のみ・`match=` を使わない）。目的は 2 つ：

1. 判定ロジックを ds／agent の 2 か所から中核へ抽出するとき、抽出が等価であることの機械的な証拠にする
   （このファイルと既存テストが無変更で緑なら、挙動は変わっていない）。
2. その後にエラーメッセージの語を標準用語へ差し替えるとき、挙動を守り続ける側として残る
   （文言を固定した既存の `match=` だけが差し替わる）。

期待値はすべて、仕込んだ metrics と閾値の大小から導ける。実装の出力は写経しない。
ds と agent は独立した実装なので、同じ性質を両方について書く（片方だけ直る退行を捕まえる）。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness.agent import store as agent_store
from harness.agent.spec import AgentSpec
from harness.ds import data
from harness.ds import models as model_store
from harness.ds.features import Columns, FeaturePipeline

pytestmark = pytest.mark.integration

_T1 = datetime(2026, 7, 3, 9, 0, 0, tzinfo=UTC)
_T2 = datetime(2026, 7, 3, 11, 0, 0, tzinfo=UTC)
_T3 = datetime(2026, 7, 3, 13, 0, 0, tzinfo=UTC)
_V1 = "20260703T090000000000Z"
_V2 = "20260703T110000000000Z"
_V3 = "20260703T130000000000Z"

# 昇格記録に残るフィールド（ds・agent で同一。抽出後もこの構造を保つ）。
_PROMOTION_FIELDS = ("work", "name", "version", "decided", "primary", "higher_is_better", "metrics", "previous_version")


def _clock(monkeypatch: pytest.MonkeyPatch, module: Any, times: list[datetime]) -> None:
    """保存 1 回あたり `_utcnow` が 2 回呼ばれる。尽きたら実時刻（昇格記録の decided 用・単調増加）。"""
    seq = iter([t for t in times for _ in range(2)])

    def _next() -> datetime:
        try:
            return next(seq)
        except StopIteration:
            return datetime.now(UTC)

    monkeypatch.setattr(module, "_utcnow", _next)


def _fitted() -> Pipeline:
    df = data.generate_synthetic(n=40, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    est = Pipeline(
        [
            ("features", FeaturePipeline([("columns", Columns(["x1", "x2"]))])),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )
    est.fit(df, y)
    return est


def _spec() -> AgentSpec:
    return AgentSpec(name="helper", provider="dummy", model="dummy-model", system_prompt="そのまま返す")


# --- ds プロファイル ---


def _save_ds(proj: Any, **metrics: float) -> None:
    model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics=dict(metrics))


def _promote_ds(proj: Any, version: str, *, primary: str, **thresholds: float) -> Any:
    return model_store.promote_model(
        proj.root, work="E-0001", name="m", version=version, thresholds=dict(thresholds), primary=primary
    )


def _champion_ds(proj: Any) -> Any:
    return model_store.champion(proj.root, work="E-0001", name="m")


def test_ds_threshold_failure_does_not_move_the_champion(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, model_store, [_T1])
    proj = make_project()
    _save_ds(proj, roc_auc=0.85)  # 閾値 0.95 に届かない
    with pytest.raises(ValueError):
        _promote_ds(proj, _V1, primary="roc_auc", roc_auc=0.95)
    assert _champion_ds(proj) is None  # champion 不在でも閾値は効く


def test_ds_first_promotion_is_decided_by_thresholds_alone(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, model_store, [_T1])
    proj = make_project()
    _save_ds(proj, roc_auc=0.85)
    promo = _promote_ds(proj, _V1, primary="roc_auc", roc_auc=0.80)  # 0.85 >= 0.80
    assert promo.previous_version is None
    champ = _champion_ds(proj)
    assert champ is not None and champ.version == _V1


def test_ds_only_a_strict_improvement_promotes(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # champion 0.85 に対し、負ける 0.80 と同点 0.85 は昇格せず、勝つ 0.90 だけが昇格する。
    _clock(monkeypatch, model_store, [_T1, _T2, _T3])
    proj = make_project()
    _save_ds(proj, roc_auc=0.85)
    _save_ds(proj, roc_auc=0.80)
    _save_ds(proj, roc_auc=0.90)
    _promote_ds(proj, _V1, primary="roc_auc", roc_auc=0.50)

    with pytest.raises(ValueError):  # 負ける
        _promote_ds(proj, _V2, primary="roc_auc", roc_auc=0.50)
    with pytest.raises(ValueError):  # 同点（champion 自身の再昇格）
        _promote_ds(proj, _V1, primary="roc_auc", roc_auc=0.50)
    champ = _champion_ds(proj)
    assert champ is not None and champ.version == _V1  # ここまで champion は動かない

    promo = _promote_ds(proj, _V3, primary="roc_auc", roc_auc=0.50)  # 勝つ
    assert promo.previous_version == _V1
    champ = _champion_ds(proj)
    assert champ is not None and champ.version == _V3


def test_ds_direction_comes_from_the_metric_registry(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # log_loss は小さいほど良い。呼び手は向きを渡さないのに、大きい方が負ける。
    _clock(monkeypatch, model_store, [_T1, _T2])
    proj = make_project()
    _save_ds(proj, log_loss=0.50)
    _save_ds(proj, log_loss=0.60)
    promo = _promote_ds(proj, _V1, primary="log_loss", log_loss=0.70)  # 0.50 <= 0.70
    assert promo.higher_is_better is False
    with pytest.raises(ValueError):
        _promote_ds(proj, _V2, primary="log_loss", log_loss=0.70)  # 0.60 は 0.50 より悪い


def test_ds_nan_candidate_fails_both_the_threshold_and_the_comparison(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, model_store, [_T1, _T2])
    proj = make_project()
    _save_ds(proj, roc_auc=0.85)
    _save_ds(proj, roc_auc=math.nan)
    _promote_ds(proj, _V1, primary="roc_auc", roc_auc=0.50)

    with pytest.raises(ValueError):  # 閾値を課したとき（NaN >= 0.50 は False）
        _promote_ds(proj, _V2, primary="roc_auc", roc_auc=0.50)
    with pytest.raises(ValueError):  # 閾値を課さなくても比較で落ちる（NaN > 0.85 は False）
        _promote_ds(proj, _V2, primary="roc_auc")
    champ = _champion_ds(proj)
    assert champ is not None and champ.version == _V1


def test_ds_nan_champion_blocks_every_promotion(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # champion 側が NaN だと、どんな候補も「勝った」と言えない（0.90 > NaN は False）＝fail closed。
    _clock(monkeypatch, model_store, [_T1, _T2])
    proj = make_project()
    _save_ds(proj, roc_auc=math.nan)
    _save_ds(proj, roc_auc=0.90)
    _promote_ds(proj, _V1, primary="roc_auc")  # 閾値なしなので NaN でも初回昇格できる
    with pytest.raises(ValueError):
        _promote_ds(proj, _V2, primary="roc_auc")


def test_ds_unknown_primary_is_rejected(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _clock(monkeypatch, model_store, [_T1])
    proj = make_project()
    _save_ds(proj, roc_auc=0.90)
    with pytest.raises(ValueError):
        _promote_ds(proj, _V1, primary="nope")


def test_ds_contradicting_direction_argument_is_rejected(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # ds だけが higher_is_better を受け取る。レジストリと矛盾したら呼び手の思い違いとして止める。
    _clock(monkeypatch, model_store, [_T1])
    proj = make_project()
    _save_ds(proj, log_loss=0.40)
    with pytest.raises(ValueError):
        model_store.promote_model(
            proj.root,
            work="E-0001",
            name="m",
            version=_V1,
            thresholds={},
            primary="log_loss",
            higher_is_better=True,  # 実際は False
        )


def test_ds_promotion_record_has_the_expected_fields(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, model_store, [_T1])
    proj = make_project()
    _save_ds(proj, roc_auc=0.85)
    promo = _promote_ds(proj, _V1, primary="roc_auc", roc_auc=0.50)
    for field in _PROMOTION_FIELDS:
        assert hasattr(promo, field), field
    assert promo.work == "E-0001" and promo.name == "m" and promo.version == _V1
    assert promo.primary == "roc_auc" and promo.metrics == {"roc_auc": 0.85}


# --- agent プロファイル（同じ性質を独立に固定する） ---


def _save_agent(proj: Any, **metrics: float) -> None:
    agent_store.save_agent(proj.root, _spec(), work="E-9001", name="helper", metrics=dict(metrics))


def _promote_agent(proj: Any, version: str, *, primary: str, **thresholds: float) -> Any:
    return agent_store.promote_agent(
        proj.root, work="E-9001", name="helper", version=version, thresholds=dict(thresholds), primary=primary
    )


def _champion_agent(proj: Any) -> Any:
    return agent_store.champion(proj.root, work="E-9001", name="helper")


def test_agent_threshold_failure_does_not_move_the_champion(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, agent_store, [_T1])
    proj = make_project()
    _save_agent(proj, exact_match=0.60)
    with pytest.raises(ValueError):
        _promote_agent(proj, _V1, primary="exact_match", exact_match=0.70)
    assert _champion_agent(proj) is None


def test_agent_only_a_strict_improvement_promotes(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, agent_store, [_T1, _T2, _T3])
    proj = make_project()
    _save_agent(proj, exact_match=0.80)
    _save_agent(proj, exact_match=0.60)
    _save_agent(proj, exact_match=0.90)
    promo1 = _promote_agent(proj, _V1, primary="exact_match", exact_match=0.50)
    assert promo1.previous_version is None and promo1.higher_is_better is True

    with pytest.raises(ValueError):  # 負ける
        _promote_agent(proj, _V2, primary="exact_match", exact_match=0.50)
    with pytest.raises(ValueError):  # 同点
        _promote_agent(proj, _V1, primary="exact_match", exact_match=0.50)
    champ = _champion_agent(proj)
    assert champ is not None and champ.version == _V1

    promo2 = _promote_agent(proj, _V3, primary="exact_match", exact_match=0.50)
    assert promo2.previous_version == _V1


def test_agent_nan_candidate_and_nan_champion_are_fail_closed(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, agent_store, [_T1, _T2])
    proj = make_project()
    _save_agent(proj, exact_match=math.nan)
    _save_agent(proj, exact_match=0.90)
    with pytest.raises(ValueError):  # 候補 NaN は閾値で落ちる
        _promote_agent(proj, _V1, primary="exact_match", exact_match=0.50)
    _promote_agent(proj, _V1, primary="exact_match")  # 閾値なしなら NaN でも初回昇格
    with pytest.raises(ValueError):  # champion が NaN だと 0.90 > NaN は False
        _promote_agent(proj, _V2, primary="exact_match")


def test_agent_unknown_primary_is_rejected(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _clock(monkeypatch, agent_store, [_T1])
    proj = make_project()
    _save_agent(proj, exact_match=0.90)
    with pytest.raises(ValueError):
        _promote_agent(proj, _V1, primary="nope")


def test_agent_promotion_record_has_the_expected_fields(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, agent_store, [_T1])
    proj = make_project()
    _save_agent(proj, exact_match=0.80)
    promo = _promote_agent(proj, _V1, primary="exact_match", exact_match=0.50)
    for field in _PROMOTION_FIELDS:
        assert hasattr(promo, field), field
    assert promo.metrics == {"exact_match": 0.80}
