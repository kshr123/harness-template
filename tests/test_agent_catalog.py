"""agent の部品カタログ（PROVIDERS/AGENT_METRICS）の発見性の検査（test_catalog.py と同型）。"""

from __future__ import annotations

import pytest

from harness.agent.cli import _agent_metrics, _agent_providers
from harness.agent.eval import AGENT_METRICS
from harness.agent.providers import PROVIDERS

pytestmark = pytest.mark.unit


def test_providers_have_descriptions() -> None:
    for kind, entry in PROVIDERS.items():
        assert entry.description, f"PROVIDERS['{kind}'] に説明文が無い（カタログに載れない）"


def test_agent_metrics_have_descriptions_and_direction() -> None:
    for kind, entry in AGENT_METRICS.items():
        assert entry.description, f"AGENT_METRICS['{kind}'] に説明文が無い（カタログに載れない）"
        assert isinstance(entry.higher_is_better, bool)  # passes が向きを読む属性（MetricEntry）


def test_catalog_commands_run(capsys: pytest.CaptureFixture[str]) -> None:
    _agent_providers()
    _agent_metrics()
    out = capsys.readouterr().out
    # レジストリの項目が一覧に出る（エージェントが 1 コマンドで発見できる）。
    assert "dummy" in out
    assert "exact_match" in out
    assert "大きいほど良い" in out  # 向きの列（render_catalog が MetricEntry を見て付ける）
