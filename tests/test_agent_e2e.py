"""agent プロファイルの一巡スモーク（宣言→dummy→採点→合否）。**ネットワーク 0 が契約**。

- 期待値は cases の構成から導出する：dummy の replies に 2 件だけ一致を仕込み、残り 1 件は
  ハッシュ由来の "dummy:<hex16>" が返る（期待文字列は "dummy:" で始まらない＝構成上一致しえない）。
  よって exact_match の平均は 2/3（実装出力のコピーではない）。
- ネットワーク遮断は socket.socket 差し替え（どの HTTP クライアント経由でも socket に落ちる＝確実に検知）。
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

from harness.agent.experiment import run_agent_eval
from harness.agent.providers import PROVIDERS
from harness.agent.spec import AgentSpec

pytestmark = pytest.mark.e2e

# 3 件中 2 件一致になる golden set（replies が s1/s2 の一致を仕込む・s3 は dummy:<hex16> ≠ expected）。
_REPLIES = {"ping": "pong", "挨拶": "こんにちは"}
_CASES = [
    {"id": "s1", "input": "ping", "expected": "pong"},
    {"id": "s2", "input": "挨拶", "expected": "こんにちは"},
    {"id": "s3", "input": "miss", "expected": "dummy: では始まらない期待文字列"},
]


def _cut_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """socket 生成を失敗にする（テスト中にネットワークへ出ようとしたら即座に落とす）。"""

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("テストがネットワーク接続を試みた（agent の verify は無ネットワークが契約・DEC-0015）")

    monkeypatch.setattr(socket, "socket", _refuse)


def test_agent_eval_smoke_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _cut_network(monkeypatch)
    spec = AgentSpec(name="smoke", provider="dummy", model="dummy-model", system_prompt="そのまま返す")
    provider = PROVIDERS.resolve(spec.provider).factory(0, replies=_REPLIES)

    result = run_agent_eval(
        spec, _CASES, provider=provider, metrics=("exact_match",), thresholds={"exact_match": 0.5}, seed=0
    )
    assert result.n == 3
    assert result.metrics["exact_match"] == pytest.approx(2 / 3)  # 仕込んだ 2 件だけ一致（構成から導出）
    assert result.passed  # 2/3 >= 0.5

    strict = run_agent_eval(
        spec, _CASES, provider=provider, metrics=("exact_match",), thresholds={"exact_match": 0.9}, seed=0
    )
    assert strict.metrics["exact_match"] == pytest.approx(2 / 3)
    assert not strict.passed  # 2/3 < 0.9 ＝閾値どおり不合格（fail closed の向き）


def test_agent_run_test_flag_is_wired_and_offline(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # `agent run --test`（AGENTS「実験は --test 必須」の導線）も同じく無ネットワークで一巡する。
    _cut_network(monkeypatch)
    from harness.agent.cli import _agent_run

    _agent_run(test=True)
    out = capsys.readouterr().out
    assert "exact_match=0.667" in out  # CLI 内蔵スモークも 3 件中 2 件一致の構成（2/3 を 3 桁表示）
    assert "passed=True" in out


def test_dummy_provider_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    # 同じ入力・同じ seed → 同じ応答／seed を変えると応答が変わる（グローバル種に依存しない決定性）。
    _cut_network(monkeypatch)
    from harness.agent.providers import build_messages, reply_text

    spec = AgentSpec(name="smoke", provider="dummy", model="dummy-model", system_prompt="そのまま返す")
    messages = build_messages("miss")
    p0 = PROVIDERS.resolve("dummy").factory(0)
    p0_again = PROVIDERS.resolve("dummy").factory(0)
    p1 = PROVIDERS.resolve("dummy").factory(1)
    first = reply_text(p0.reply(messages=messages, tools=(), spec=spec))
    assert first == reply_text(p0_again.reply(messages=messages, tools=(), spec=spec))
    assert first.startswith("dummy:")
    assert first != reply_text(p1.reply(messages=messages, tools=(), spec=spec))
