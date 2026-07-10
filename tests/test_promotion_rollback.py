"""切り戻し（rollback）と却下記録の挙動を固定するテスト。

- 切り戻しは昇格ではないので判定（change_threshold）を通さない＝劣る旧良版へ戻せる（機能であって欠陥ではない）。
- 却下された昇格も記録として残る（status: rejected）が、champion は approved の記録だけを見るので動かない。
- 切り戻しは戻り先（rollback_to）の連鎖を 1 段ずつ辿る（スタックの pop）＝ping-pong しない。

期待値は仕込んだ metrics と閾値の大小から導ける（実装の出力は写経しない）。時刻は monkeypatch で単調増加に
固定し、版名・決定名の順序を決めうちにする（グローバル種を使わない・呼ぶ場所で決める）。ds と agent は
中核 harness.promotion を共有するが、呼び手（薄いラッパ）は別なので両方で固定する。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness import gates
from harness.agent import store as agent_store
from harness.agent.spec import AgentSpec
from harness.ds import data
from harness.ds import models as model_store
from harness.ds.features import Columns, FeaturePipeline

pytestmark = pytest.mark.integration


def _increasing(monkeypatch: pytest.MonkeyPatch, module: Any) -> None:
    """`_utcnow` を単調増加に固定する（呼ぶたび 1 分後）。版名・決定名が一意かつ昇順になる。"""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    counter = {"n": 0}

    def _next() -> datetime:
        n = counter["n"]
        counter["n"] += 1
        return base + timedelta(minutes=n)

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


# --- ds プロファイル ---


def _save_ds(proj: Any, **metrics: float) -> str:
    return model_store.save_model(proj.root, _fitted(), name="m", work="E-0001", metrics=dict(metrics)).version


def _promote_ds(proj: Any, version: str) -> Any:
    return model_store.promote_model(
        proj.root, work="E-0001", name="m", version=version, thresholds={}, primary="roc_auc"
    )


def _champion_ds(proj: Any) -> Any:
    return model_store.champion(proj.root, work="E-0001", name="m")


def test_ds_rollback_restores_worse_previous_champion_without_a_gate(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # v1(0.85) を champion にし、勝つ v2(0.90) を昇格。切り戻すと、劣る v1 へ戻れる（判定を通さない証拠）。
    _increasing(monkeypatch, model_store)
    proj = make_project()
    v1 = _save_ds(proj, roc_auc=0.85)
    v2 = _save_ds(proj, roc_auc=0.90)
    _promote_ds(proj, v1)
    _promote_ds(proj, v2)
    assert _champion_ds(proj).version == v2  # 勝った版が champion

    rolled = model_store.rollback_model(proj.root, work="E-0001", name="m", reason="v2 が本番で劣化")
    assert rolled.kind == "rollback" and rolled.version == v1 and rolled.reason == "v2 が本番で劣化"
    champ = _champion_ds(proj)
    # v1(0.85) は v2(0.90) より劣るのに champion に戻った＝change_threshold を課していない。
    assert champ.version == v1 and champ.metrics == {"roc_auc": 0.85}


def test_ds_promote_after_rollback_still_obeys_the_gate(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 切り戻しは判定を免除するが、promote は免除しない。戻したあと baseline は v1 になる。
    _increasing(monkeypatch, model_store)
    proj = make_project()
    v1 = _save_ds(proj, roc_auc=0.85)
    v2 = _save_ds(proj, roc_auc=0.90)
    bad = _save_ds(proj, roc_auc=0.50)
    _promote_ds(proj, v1)
    _promote_ds(proj, v2)
    model_store.rollback_model(proj.root, work="E-0001", name="m", reason="戻す")
    assert _champion_ds(proj).version == v1

    # baseline は v1(0.85)。劣る bad(0.50) は promote では却下される（免除されない）。
    with pytest.raises(gates.PromotionError):
        _promote_ds(proj, bad)
    # 勝つ v2(0.90>0.85) は再昇格でき、その previous_version は v1（baseline が v1 に戻っている証拠）。
    promo = _promote_ds(proj, v2)
    assert promo.previous_version == v1
    assert _champion_ds(proj).version == v2


def test_ds_second_rollback_has_no_target_and_does_not_ping_pong(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _increasing(monkeypatch, model_store)
    proj = make_project()
    v1 = _save_ds(proj, roc_auc=0.85)
    v2 = _save_ds(proj, roc_auc=0.90)
    _promote_ds(proj, v1)
    _promote_ds(proj, v2)
    model_store.rollback_model(proj.root, work="E-0001", name="m", reason="1 回目")  # v2 → v1
    assert _champion_ds(proj).version == v1
    # v1 は初回昇格＝戻り先が無い。2 回目の rollback は v2 へ往復せず ValueError。
    with pytest.raises(ValueError):
        model_store.rollback_model(proj.root, work="E-0001", name="m", reason="2 回目")
    assert _champion_ds(proj).version == v1  # champion は動かない


def test_ds_rollback_requires_a_reason(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _increasing(monkeypatch, model_store)
    proj = make_project()
    v1 = _save_ds(proj, roc_auc=0.85)
    v2 = _save_ds(proj, roc_auc=0.90)
    _promote_ds(proj, v1)
    _promote_ds(proj, v2)
    with pytest.raises(ValueError):
        model_store.rollback_model(proj.root, work="E-0001", name="m", reason="   ")


def test_ds_rollback_fails_if_the_target_version_is_gone(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _increasing(monkeypatch, model_store)
    proj = make_project()
    v1 = _save_ds(proj, roc_auc=0.85)
    v2 = _save_ds(proj, roc_auc=0.90)
    _promote_ds(proj, v1)
    _promote_ds(proj, v2)
    # 戻り先の版 v1 の manifest を消す＝実体が無い。黙って壊れた champion を指さず ValueError。
    (proj.root / "data" / "work" / "E-0001" / "models" / "m" / v1 / "manifest.yaml").unlink()
    with pytest.raises(ValueError):
        model_store.rollback_model(proj.root, work="E-0001", name="m", reason="戻す")


def test_ds_rejected_promotion_is_recorded_but_champion_does_not_move(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _increasing(monkeypatch, model_store)
    proj = make_project()
    v1 = _save_ds(proj, roc_auc=0.85)
    bad = _save_ds(proj, roc_auc=0.50)
    _promote_ds(proj, v1)
    with pytest.raises(gates.PromotionError):
        _promote_ds(proj, bad)  # 0.50 は champion 0.85 に負ける＝却下
    # 却下は記録として残る（監査）。だが approved でないので champion は動かない。
    hist = model_store.promotions(proj.root, work="E-0001", name="m")
    rejected = [r for r in hist if r["status"] == "rejected"]
    assert len(rejected) == 1 and rejected[0]["version"] == bad and rejected[0]["kind"] == "promote"
    assert _champion_ds(proj).version == v1


def test_ds_rollback_without_champion_is_rejected(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _increasing(monkeypatch, model_store)
    proj = make_project()
    _save_ds(proj, roc_auc=0.85)
    with pytest.raises(ValueError):  # まだ昇格していない＝戻す先が無い
        model_store.rollback_model(proj.root, work="E-0001", name="m", reason="戻す")


# --- agent プロファイル（薄いラッパを独立に固定する） ---


def _spec() -> AgentSpec:
    return AgentSpec(name="helper", provider="dummy", model="dummy-model", system_prompt="そのまま返す")


def _save_agent(proj: Any, **metrics: float) -> str:
    return agent_store.save_agent(proj.root, _spec(), work="E-9001", name="helper", metrics=dict(metrics)).version


def _promote_agent(proj: Any, version: str) -> Any:
    return agent_store.promote_agent(
        proj.root, work="E-9001", name="helper", version=version, thresholds={}, primary="exact_match"
    )


def test_agent_rollback_restores_worse_previous_champion_without_a_gate(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _increasing(monkeypatch, agent_store)
    proj = make_project()
    v1 = _save_agent(proj, exact_match=0.60)
    v2 = _save_agent(proj, exact_match=0.80)
    _promote_agent(proj, v1)
    _promote_agent(proj, v2)
    champ = agent_store.champion(proj.root, work="E-9001", name="helper")
    assert champ is not None and champ.version == v2

    rolled = agent_store.rollback_agent(proj.root, work="E-9001", name="helper", reason="v2 を戻す")
    assert rolled.kind == "rollback" and rolled.version == v1
    champ = agent_store.champion(proj.root, work="E-9001", name="helper")
    assert champ is not None and champ.version == v1 and champ.metrics == {"exact_match": 0.60}


def test_agent_second_rollback_has_no_target(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _increasing(monkeypatch, agent_store)
    proj = make_project()
    v1 = _save_agent(proj, exact_match=0.60)
    v2 = _save_agent(proj, exact_match=0.80)
    _promote_agent(proj, v1)
    _promote_agent(proj, v2)
    agent_store.rollback_agent(proj.root, work="E-9001", name="helper", reason="1 回目")
    with pytest.raises(ValueError):
        agent_store.rollback_agent(proj.root, work="E-9001", name="helper", reason="2 回目")
