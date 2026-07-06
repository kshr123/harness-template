"""ツール（TOOLS レジストリ）＝エージェントが呼べる純関数と、provider へ渡す宣言形。

- 1 ツール＝名前＋input_schema（JSON Schema）＋**純粋・決定的な** Python 関数（`fn(**args) -> str`）。
  description は factory の docstring 1 行目（DEC-0009・空は登録できない）。一覧は `uv run agent tools`。
- ネットワーク・ファイル I/O は禁止（verify の無ネットワーク契約＝DEC-0015 をツール実行でも守る）。
- スキーマ検証は required の充足＋未宣言キーの拒否だけ（jsonschema は入れない＝軽 import・DEC-0013。
  型の検証まで要る実ツールが出たら、その時に検証の厚みを決める＝YAGNI）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from harness.registry import Entry, Registry


@dataclass(frozen=True, kw_only=True)
class ToolEntry(Entry):
    """ツールの項目。factory() が実行する純関数を返し、input_schema が引数の契約（宣言と検証の正本）。

    input_schema は Anthropic の tool 宣言と同じ JSON Schema 形（{"type": "object", "properties": …,
    "required": …}）。to_provider_tools がそのまま provider へ渡し、run_tool が実行前に照合する。
    """

    input_schema: Mapping[str, Any]


TOOLS: Registry[ToolEntry] = Registry("ツール", catalog="agent tools")


def calculator() -> Callable[..., str]:
    """整数の加算・乗算（op=add | mul）を決定的に計算して数値文字列を返す（式の eval はしない）。"""

    def fn(*, a: int, b: int, op: str) -> str:
        if op == "add":
            return str(a + b)
        if op == "mul":
            return str(a * b)
        raise ValueError(f"calculator: 未知の op '{op}'（add | mul のいずれか）")

    return fn


TOOLS.register(
    "calculator",
    calculator,
    entry_cls=ToolEntry,
    input_schema={
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "左の整数"},
            "b": {"type": "integer", "description": "右の整数"},
            "op": {"type": "string", "enum": ["add", "mul"], "description": "演算（add=加算・mul=乗算）"},
        },
        "required": ["a", "b", "op"],
    },
)


def to_provider_tools(names: Sequence[str], *, registry: Registry[ToolEntry] = TOOLS) -> list[dict[str, Any]]:
    """ツール名の並びから provider へ渡す tool 宣言（{"name","description","input_schema"}）を組む。

    未登録名は registry.resolve が候補一覧つき ValueError で止める（spec の tools[] は lint も静的検査する）。
    """
    return [
        {"name": name, "description": entry.description, "input_schema": dict(entry.input_schema)}
        for name, entry in ((name, registry.resolve(name)) for name in names)
    ]


def run_tool(name: str, args: Mapping[str, Any], *, registry: Registry[ToolEntry] = TOOLS) -> str:
    """ツールを 1 回実行して文字列の結果を返す。未登録名・スキーマ不一致（required 欠け・未宣言キー）は ValueError。

    検証は input_schema の required 充足＋properties に無いキーの拒否だけ（黙って捨てず実行前に止める）。
    ツール本体が投げた例外はそのまま伝える（往復ループの再試行方針は監視 T-0093 で必要が見えてから）。
    """
    entry = registry.resolve(name)  # 未登録はここで候補一覧つき ValueError
    declared = set(entry.input_schema.get("properties", {}))
    missing = sorted(set(entry.input_schema.get("required", ())) - set(args))
    unknown = sorted(set(args) - declared)
    if missing or unknown:
        raise ValueError(
            f"ツール '{name}' の引数がスキーマと合わない（required 欠け: {missing}・未宣言キー: {unknown}・"
            f"書けるのは {sorted(declared)}）"
        )
    return str(entry.factory()(**args))
