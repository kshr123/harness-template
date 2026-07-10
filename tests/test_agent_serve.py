"""agent/app.py（`agent serve`＝champion の FastAPI 配信）と spec_from_mapping のテスト。

champion は test_agent_store.py と同じ作法で用意する（`_clock` で時刻を固定 → save_agent → promote_agent）。
provider は dummy（決定的・無ネットワーク）＝期待は DummyProvider の構成から導出する（仕込み無しの入力には
"dummy:" 接頭のハッシュ応答・stop_reason="end_turn"・turns=1・usage は 0）。実装出力の写経はしない。
/invoke のログは monitor.read_agent_logs で読み戻す（配信→監視の結線＝AGENT_LOG_FIELDS 契約どおり）。
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from harness.agent import monitor, store
from harness.agent.app import create_app
from harness.agent.spec import AgentSpec, spec_from_mapping

_T1 = datetime(2026, 7, 6, 9, 0, 0, tzinfo=UTC)
_V1 = "20260706T090000000000Z"


def _clock(monkeypatch: pytest.MonkeyPatch, times: list[datetime]) -> None:
    # save_agent は _utcnow を 2 回呼ぶ（version・created）。各時刻を 2 回ずつ返し、尽きたら実時刻へ
    # フォールバック（promote_agent の decided 用・単調増加）。test_agent_store.py と同じ作法。
    seq = iter([t for t in times for _ in range(2)])

    def _next() -> datetime:
        try:
            return next(seq)
        except StopIteration:
            return datetime.now(UTC)

    monkeypatch.setattr(store, "_utcnow", _next)


def _spec(prompt: str = "そのまま返す") -> AgentSpec:
    return AgentSpec(name="helper", provider="dummy", model="dummy-model", system_prompt=prompt)


def _make_champion(proj: Any, monkeypatch: pytest.MonkeyPatch, *, work: str = "E-9101") -> None:
    """provider=dummy の champion を 1 版つくる（保存 → value_threshold だけで初回昇格）。"""
    _clock(monkeypatch, [_T1])
    store.save_agent(proj.root, _spec(), work=work, name="helper", metrics={"exact_match": 0.9})
    store.promote_agent(
        proj.root, work=work, name="helper", version=_V1, thresholds={"exact_match": 0.5}, primary="exact_match"
    )


@pytest.mark.integration
def test_invoke_runs_agent_and_appends_run_log(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = make_project()
    _make_champion(proj, monkeypatch)
    app = create_app(proj.root, work="E-9101", name="helper")
    client = TestClient(app)

    resp = client.post("/invoke", json={"input": "ping"})
    assert resp.status_code == 200
    body = resp.json()
    # 期待は dummy の構成から導出：仕込み（replies）が無い入力にはハッシュ由来テキストを end_turn で返す
    # ＝1 ターン・ツール無し・usage は 0（DummyProvider の定義）。output の具体ハッシュは写経しない。
    assert body["output"].startswith("dummy:")
    assert body["stop_reason"] == "end_turn"
    assert body["turns"] == 1
    assert body["tools_used"] == []
    assert body["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert body["request_id"]
    assert body["agent"] == {"name": "helper", "work": "E-9101", "version": _V1}

    # 既定の置き場（artifacts/agent/runs/<name>/<YYYYMMDD>.jsonl）に 1 行残る＝monitor がそのまま読める。
    files = sorted((proj.root / "artifacts" / "agent" / "runs" / "helper").glob("*.jsonl"))
    assert len(files) == 1
    logs = monitor.read_agent_logs(files)
    assert logs.n_rows == 1
    assert logs.n_skipped == 0  # 行は AGENT_LOG_FIELDS 契約どおり（消費キーの欠け・型違いが無い）
    assert logs.rows[0].stop_reason == "end_turn"
    assert logs.rows[0].turns == 1


@pytest.mark.integration
def test_health_and_metadata_return_champion_provenance(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = make_project()
    _make_champion(proj, monkeypatch)
    client = TestClient(create_app(proj.root, work="E-9101", name="helper"))

    health = client.get("/health").json()
    assert health == {"status": "ok", "agent": {"name": "helper", "work": "E-9101", "version": _V1}}

    meta = client.get("/metadata").json()
    assert meta["name"] == "helper"
    assert meta["work"] == "E-9101"
    assert meta["version"] == _V1
    assert meta["spec"]["provider"] == "dummy"  # 宣言（config）が manifest から往復する
    assert meta["spec"]["system_prompt"] == "そのまま返す"
    assert meta["metrics"] == {"exact_match": 0.9}
    assert meta["prompt_fingerprint"]
    assert meta["created"]
    assert "path" not in meta  # ローカル事情は出さない


@pytest.mark.integration
def test_invoke_empty_input_is_422(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    proj = make_project()
    _make_champion(proj, monkeypatch)
    client = TestClient(create_app(proj.root, work="E-9101", name="helper"))
    resp = client.post("/invoke", json={"input": "  "})
    assert resp.status_code == 422
    # 422 のとき実行ログは残らない（run_agent に到達しない）。
    assert not (proj.root / "artifacts" / "agent" / "runs").exists()


@pytest.mark.integration
def test_create_app_fails_without_champion(make_project: Callable[..., Any]) -> None:
    proj = make_project()
    with pytest.raises(ValueError, match="champion が無い"):
        create_app(proj.root, work="E-9101", name="helper")


@pytest.mark.integration
def test_invoke_logs_to_custom_log_dir(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    proj = make_project()
    _make_champion(proj, monkeypatch)
    log_dir = proj.root / "custom-logs"
    client = TestClient(create_app(proj.root, work="E-9101", name="helper", log_dir=log_dir))
    assert client.post("/invoke", json={"input": "ping"}).status_code == 200
    assert len(sorted(log_dir.glob("*.jsonl"))) == 1  # log_dir 直下（名前のディレクトリを掘らない）


@pytest.mark.unit
def test_spec_from_mapping_roundtrips_asdict() -> None:
    # 保存経路（dataclasses.asdict → manifest → dict）の往復＝配信が champion の宣言を復元する経路。
    original = AgentSpec(
        name="helper",
        provider="dummy",
        model="dummy-model",
        system_prompt="計算はツールで行う",
        tools=("calculator",),
        effort="high",
        max_turns=4,
        output_schema={"type": "object"},
    )
    raw = dataclasses.asdict(original)
    raw["tools"] = list(raw["tools"])  # manifest（YAML）経由では list になる（save_agent と同じ形）
    restored = spec_from_mapping(raw)
    assert restored == original  # tools は tuple に正規化される
    assert raw["tools"] == ["calculator"]  # 呼び手の写像は変更しない（copy して扱う）


@pytest.mark.unit
def test_spec_from_mapping_rejects_bad_mappings() -> None:
    base = {"name": "a", "provider": "dummy", "model": "m", "system_prompt": "s"}
    with pytest.raises(ValueError, match="temperature"):
        spec_from_mapping({**base, "temperature": 0.2})
    with pytest.raises(ValueError, match="未知のキー"):
        spec_from_mapping({**base, "unknown_key": 1})
    with pytest.raises(ValueError, match="effort"):
        spec_from_mapping({**base, "effort": "extreme"})
    # source はエラー文言の出所に出る（配信では work/name/version を渡す）。
    with pytest.raises(ValueError, match="E-9101/helper/v1"):
        spec_from_mapping({**base, "temperature": 0.2}, source="E-9101/helper/v1")
