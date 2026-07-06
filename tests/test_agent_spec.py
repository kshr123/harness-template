"""AgentSpec の宣言 YAML 読み込み（load_agent_spec）の検査。未知キー・temperature は失敗（extra forbid）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.agent.spec import AgentSpec, load_agent_spec

pytestmark = pytest.mark.unit

_VALID = """\
name: support-bot
provider: dummy
model: claude-opus-4-8
system_prompt: 丁寧に答える
tools: [echo]
effort: high
max_turns: 4
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "agent.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_agent_spec_reads_declarative_yaml(tmp_path: Path) -> None:
    spec = load_agent_spec(_write(tmp_path, _VALID))
    assert spec == AgentSpec(
        name="support-bot",
        provider="dummy",
        model="claude-opus-4-8",
        system_prompt="丁寧に答える",
        tools=("echo",),
        effort="high",
        max_turns=4,
    )
    assert spec.output_schema is None  # 省略キーは既定値


def test_unknown_key_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID + "unknown_key: 1\n")
    with pytest.raises(ValueError, match="unknown_key"):
        load_agent_spec(path)


def test_temperature_key_raises_with_clear_message(tmp_path: Path) -> None:
    # 現行モデルは temperature を受け付けない（送ると 400）＝宣言の段階で明示エラーにする（DEC-0015）。
    path = _write(tmp_path, _VALID + "temperature: 0.0\n")
    with pytest.raises(ValueError, match="temperature") as exc_info:
        load_agent_spec(path)
    assert "effort" in str(exc_info.value)  # 代替（effort＋cassette）を案内する


def test_invalid_effort_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("effort: high", "effort: hottest"))
    with pytest.raises(ValueError, match="effort"):
        load_agent_spec(path)


def test_non_mapping_yaml_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="辞書"):
        load_agent_spec(_write(tmp_path, "- 1\n- 2\n"))
