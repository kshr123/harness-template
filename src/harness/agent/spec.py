"""AgentSpec（エージェントの宣言＝prompt＋model＋tools＋方針）と、宣言的 YAML の読み込み。

- 1 エージェント＝1 つの宣言（学習済みバイナリではない）。config が正本・コードは読むだけ（DEC-0004 と同型）。
- `temperature` は持たない：現行モデル（Opus 4.7/4.8・Sonnet 5・Fable 5）は temperature/top_p/top_k を
  受け付けない（送ると 400）。決定性は effort（宣言に固定）＋verify の無ネットワーク（dummy/cassette）で作る
  （DEC-0015）。
- 依存は stdlib＋pyyaml のみ（yaml は関数内で遅延取り込み・プロファイル経路を軽く保つ＝DEC-0013）。
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, get_args

# 推論の深さ（現行モデルの決定性軸。temperature の代替ではなく「宣言に固定する」ことが要点）。
Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AgentSpec:
    """エージェントの宣言。provider は PROVIDERS の kind（一覧は `uv run agent providers`）。

    output_schema は構造化出力（JSON Schema）を期待するときだけ書く（検証は guardrails＝T-0093 で足す）。
    """

    name: str
    provider: str
    model: str
    system_prompt: str
    tools: tuple[str, ...] = ()
    effort: Effort = "medium"
    max_turns: int = 8
    output_schema: Mapping[str, Any] | None = None


_FIELDS = {f.name for f in dataclasses.fields(AgentSpec)}
_EFFORTS = frozenset(get_args(Effort))


def load_agent_spec(path: Path) -> AgentSpec:
    """宣言的 YAML を AgentSpec に読み込む。未知キーは失敗（extra forbid・typo を黙って捨てない）。

    `temperature` は専用のエラーで弾く（現行モデルは 400＝DEC-0015。effort を使うよう案内する）。
    """
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: AgentSpec の YAML はキー→値の辞書であること（実際: {type(raw).__name__}）")
    if "temperature" in raw:
        raise ValueError(
            f"{path}: temperature は指定できない（現行モデルはパラメータごと廃止＝送ると 400・DEC-0015）。"
            "決定性は effort（low〜max）を宣言に固定し、verify は無ネットワーク（dummy/cassette）で作る"
        )
    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        raise ValueError(f"{path}: 未知のキー {unknown}（書けるのは {sorted(_FIELDS)}）")
    if "tools" in raw:
        raw["tools"] = tuple(str(t) for t in raw["tools"])
    effort = raw.get("effort")
    if effort is not None and effort not in _EFFORTS:
        raise ValueError(f"{path}: effort '{effort}' は不正（{sorted(_EFFORTS)} のいずれか）")
    return AgentSpec(**raw)
