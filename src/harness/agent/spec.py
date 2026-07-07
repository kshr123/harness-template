"""AgentSpec（エージェントの宣言＝prompt＋model＋tools＋方針）と、宣言的 YAML の読み込み。

- 1 エージェント＝1 つの宣言（学習済みバイナリではない）。config が正本・コードは読むだけ（ と同型）。
- `temperature` は持たない：現行モデル（Opus 4.7/4.8・Sonnet 5・Fable 5）は temperature/top_p/top_k を
  受け付けない（送ると 400）。決定性は effort（宣言に固定）＋verify の無ネットワーク（dummy/cassette）で作る
  。
- 依存は stdlib＋pyyaml のみ（yaml は関数内で遅延取り込み・プロファイル経路を軽く保つ）。
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


def spec_from_mapping(raw: Mapping[str, Any], *, source: str = "<mapping>") -> AgentSpec:
    """キー→値の写像を検証して AgentSpec にする（検証の正本＝load_agent_spec と配信 T-0094 が共用）。

    - 未知キーは失敗（extra forbid・typo を黙って捨てない）。`temperature` は専用のエラーで弾く
      （現行モデルは 400。effort を使うよう案内する）。
    - tools は list（YAML・`dataclasses.asdict` 由来）でも tuple に正規化する。output_schema は
      dict/None をそのまま通す。呼び手の写像は変更しない（copy して扱う）。
    - source はエラー文言に出す出所（YAML ならファイルパス・保存済み宣言なら work/name/version）。
    """
    if not isinstance(raw, Mapping):
        raise ValueError(f"{source}: AgentSpec はキー→値の辞書であること（実際: {type(raw).__name__}）")
    data = dict(raw)  # 呼び手の写像（AgentRecord.spec 等）を変更しない
    if "temperature" in data:
        raise ValueError(
            f"{source}: temperature は指定できない（現行モデルはパラメータごと廃止＝送ると 400）。"
            "決定性は effort（low〜max）を宣言に固定し、verify は無ネットワーク（dummy/cassette）で作る"
        )
    unknown = sorted(set(data) - _FIELDS)
    if unknown:
        raise ValueError(f"{source}: 未知のキー {unknown}（書けるのは {sorted(_FIELDS)}）")
    if "tools" in data:
        data["tools"] = tuple(str(t) for t in data["tools"])
    effort = data.get("effort")
    if effort is not None and effort not in _EFFORTS:
        raise ValueError(f"{source}: effort '{effort}' は不正（{sorted(_EFFORTS)} のいずれか）")
    return AgentSpec(**data)


def load_agent_spec(path: Path) -> AgentSpec:
    """宣言的 YAML を AgentSpec に読み込む（検証は spec_from_mapping に委譲・挙動は従来どおり）。"""
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return spec_from_mapping(raw, source=str(path))
