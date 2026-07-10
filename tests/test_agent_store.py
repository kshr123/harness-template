"""agent/store.py（宣言の保存・読込・一覧・昇格）のテスト。

時刻は `_utcnow` を差し替えて固定する（版＝時刻なので、再利用拒否・昇格の順序を構成で確かめられる）。
期待値は metrics・prompt の構成から導出する（実装出力の写経はしない）：prompt_fingerprint は
sha256(system_prompt) と定義どおり一致すること、昇格の合否は仕込んだ metrics と閾値の大小から導く。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from harness.agent import store
from harness.agent.spec import AgentSpec

_T1 = datetime(2026, 7, 6, 9, 0, 0, tzinfo=UTC)
_T2 = datetime(2026, 7, 6, 11, 0, 0, tzinfo=UTC)
_T3 = datetime(2026, 7, 6, 13, 0, 0, tzinfo=UTC)
_V1 = "20260706T090000000000Z"
_V2 = "20260706T110000000000Z"
_V3 = "20260706T130000000000Z"


def _clock(monkeypatch: pytest.MonkeyPatch, times: list[datetime]) -> None:
    # save_agent は _utcnow を 2 回呼ぶ（version・created）。各時刻を 2 回ずつ返し、
    # 尽きたら実時刻へフォールバック（昇格記録 decided など版に依らない呼び出し用・単調増加）。
    seq = iter([t for t in times for _ in range(2)])

    def _next() -> datetime:
        try:
            return next(seq)
        except StopIteration:
            return datetime.now(UTC)

    monkeypatch.setattr(store, "_utcnow", _next)


def _spec(prompt: str = "そのまま返す") -> AgentSpec:
    return AgentSpec(name="helper", provider="dummy", model="dummy-model", system_prompt=prompt)


@pytest.mark.integration
def test_promote_agent_absolute_and_relative_gates(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # exact_match は higher_is_better=True（AGENT_METRICS の登録どおり）＝閾値は >=・相対関門は > で判定。
    _clock(monkeypatch, [_T1, _T2, _T3])
    proj = make_project()
    store.save_agent(proj.root, _spec(), work="E-9001", name="helper", metrics={"exact_match": 0.8})
    store.save_agent(proj.root, _spec(), work="E-9001", name="helper", metrics={"exact_match": 0.9})
    store.save_agent(proj.root, _spec(), work="E-9001", name="helper", metrics={"exact_match": 0.6})

    # 絶対関門（champion 不在でも効く）：0.6 < 0.7 は不合格。
    with pytest.raises(ValueError, match="絶対関門"):
        store.promote_agent(
            proj.root, work="E-9001", name="helper", version=_V3, thresholds={"exact_match": 0.7}, primary="exact_match"
        )
    # 初回昇格は絶対関門のみ（0.8 >= 0.5 で champion に）。向きの記録はレジストリ由来（引数に無い）。
    promo1 = store.promote_agent(
        proj.root, work="E-9001", name="helper", version=_V1, thresholds={"exact_match": 0.5}, primary="exact_match"
    )
    assert promo1.higher_is_better is True  # AGENT_METRICS['exact_match'] の登録どおり
    assert promo1.previous_version is None
    champ1 = store.champion(proj.root, work="E-9001", name="helper")
    assert champ1 is not None and champ1.version == _V1

    # 相対関門：絶対関門は通る（0.6 >= 0.5）が champion（0.8）に負ける版は昇格しない。
    with pytest.raises(ValueError, match="相対関門"):
        store.promote_agent(
            proj.root, work="E-9001", name="helper", version=_V3, thresholds={"exact_match": 0.5}, primary="exact_match"
        )
    # 同点（0.8 vs 0.8＝champion 自身の再昇格）も昇格しない（> の判定＝同点は勝ちでない）。
    with pytest.raises(ValueError, match="相対関門"):
        store.promote_agent(
            proj.root, work="E-9001", name="helper", version=_V1, thresholds={"exact_match": 0.5}, primary="exact_match"
        )
    # 勝つ版（0.9 > 0.8）だけ昇格し、champion が最新昇格版へ移る。
    promo2 = store.promote_agent(
        proj.root, work="E-9001", name="helper", version=_V2, thresholds={"exact_match": 0.5}, primary="exact_match"
    )
    assert promo2.previous_version == _V1
    champ2 = store.champion(proj.root, work="E-9001", name="helper")
    assert champ2 is not None and champ2.version == _V2


@pytest.mark.unit
def test_save_load_roundtrip_and_prompt_fingerprint(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch, [_T1, _T2])
    proj = make_project()
    prompt_a = "そのまま返す"
    prompt_b = "丁寧語で返す"
    record_a = store.save_agent(proj.root, _spec(prompt_a), work="E-9002", name="helper", metrics={"exact_match": 0.5})
    record_b = store.save_agent(proj.root, _spec(prompt_b), work="E-9002", name="helper", metrics={"exact_match": 0.5})

    loaded = store.load_agent(proj.root, work="E-9002", name="helper", version=_V1)
    assert loaded.spec["system_prompt"] == prompt_a  # 宣言（config）が manifest に畳み込まれ往復する
    assert loaded.spec["provider"] == "dummy"
    assert loaded.metrics == {"exact_match": 0.5}
    # 指紋は定義（sha256(system_prompt)）から導出＝実装出力のコピーではない。
    assert loaded.prompt_fingerprint == hashlib.sha256(prompt_a.encode("utf-8")).hexdigest()
    assert record_b.prompt_fingerprint == hashlib.sha256(prompt_b.encode("utf-8")).hexdigest()
    assert record_a.prompt_fingerprint != record_b.prompt_fingerprint  # prompt を変えると必ず変わる

    versions = [r.version for r in store.list_agents(proj.root, work="E-9002")]
    assert versions == [_V1, _V2]  # 版は時刻（辞書順＝時刻順）
    with pytest.raises(FileNotFoundError, match="保存が無い"):
        store.load_agent(proj.root, work="E-9002", name="helper", version="20990101T000000000000Z")


@pytest.mark.unit
def test_same_version_is_rejected(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _clock(monkeypatch, [_T1, _T1])  # 2 回の save を同じ時刻にする＝版の再利用は拒否
    proj = make_project()
    store.save_agent(proj.root, _spec(), work="E-9003", name="helper", metrics={})
    with pytest.raises(ValueError, match="版は再利用しない"):
        store.save_agent(proj.root, _spec(), work="E-9003", name="helper", metrics={})


@pytest.mark.integration
def test_promote_rejects_when_champion_lacks_the_primary_metric(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 過去の昇格と違う primary（llm_judge）に切り替えると、現 champion 側にその指標が無い。
    # 比較できない＝昇格しない（KeyError で落ちてはいけない）。
    _clock(monkeypatch, [_T1, _T2])
    proj = make_project()
    store.save_agent(proj.root, _spec(), work="E-9005", name="helper", metrics={"exact_match": 0.8})
    store.save_agent(proj.root, _spec(), work="E-9005", name="helper", metrics={"llm_judge": 0.9})
    store.promote_agent(
        proj.root, work="E-9005", name="helper", version=_V1, thresholds={"exact_match": 0.5}, primary="exact_match"
    )
    with pytest.raises(ValueError, match="llm_judge"):
        store.promote_agent(
            proj.root, work="E-9005", name="helper", version=_V2, thresholds={"llm_judge": 0.5}, primary="llm_judge"
        )
    champ = store.champion(proj.root, work="E-9005", name="helper")
    assert champ is not None and champ.version == _V1  # champion は動いていない


@pytest.mark.unit
def test_promote_rejects_when_candidate_lacks_the_primary_metric(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 候補側に primary が無いときの分岐（これまでテストが無かった）。champion 不在でも昇格しない。
    _clock(monkeypatch, [_T1])
    proj = make_project()
    store.save_agent(proj.root, _spec(), work="E-9006", name="helper", metrics={"exact_match": 0.9})
    with pytest.raises(ValueError, match="llm_judge"):
        store.promote_agent(proj.root, work="E-9006", name="helper", version=_V1, thresholds={}, primary="llm_judge")
    assert store.champion(proj.root, work="E-9006", name="helper") is None


@pytest.mark.unit
def test_promote_rejects_unknown_primary(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _clock(monkeypatch, [_T1])
    proj = make_project()
    store.save_agent(proj.root, _spec(), work="E-9004", name="helper", metrics={"exact_match": 0.9})
    # AGENT_METRICS に無い primary は typo を黙って通さず ValueError（向きが解決できない）。
    with pytest.raises(ValueError, match="未登録"):
        store.promote_agent(proj.root, work="E-9004", name="helper", version=_V1, thresholds={}, primary="nope")


@pytest.mark.integration
def test_agent_experiments_cli_aggregates_metrics(
    make_project: Callable[..., Any], capsys: pytest.CaptureFixture[str]
) -> None:
    # 変種比較の CLI は ds.experiment.leaderboard の再利用＝metrics_*.yaml（1 ファイル 1 変種）を集約し、
    # 最初の指標の降順で並ぶ（0.9 の変種が 0.6 の変種より上＝構成から導出）。
    from harness.agent.cli import _agent_experiments

    proj = make_project()
    proj.add_file("results/metrics_good.yaml", "variant: good\npassed: true\nmetrics:\n  exact_match: 0.9\n")
    proj.add_file("results/metrics_bad.yaml", "variant: bad\npassed: false\nmetrics:\n  exact_match: 0.6\n")
    _agent_experiments(results=proj.root / "results", sort_by="exact_match")
    out = capsys.readouterr().out
    assert "exact_match" in out
    assert out.index("good") < out.index("bad")  # 降順＝高い変種が先
