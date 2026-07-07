"""入出力のガードレール（入力の PII 検出スタブ・出力の JSON Schema 最小検証・stdlib のみ）。

エージェントの入出力を「通す前に確かめる」薄い層。共通の口は `Guard` Protocol（`check(text) -> GuardResult`）
＝実装は差し替え可能で、いまは骨組みの 2 つだけ：

- `PiiRegexGuard`：入力ガードの**正規表現スタブ**（email・電話番号）。実際の PII 検出はモデルへ委譲する
  （入口だけ作って委譲点を明示する DEC-0009 の作法）。
- `validate_output_schema`：出力を JSON として解釈し、JSON Schema の**最小部分集合**で検証する。
  完全検証は jsonschema へ委譲する（base 依存に無い＝推移的のみ。必要になったら extra として足す）。

Registry 化はしない（YAGNI・guards の 2 実装目が出たら昇格＝DEC-0012）。依存は stdlib のみ
（DEC-0013 の軽さ・agent プロファイルは ds を import しない＝DEC-0004）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GuardResult:
    """ガード 1 回の判定。ok=False のとき reason が理由・matches が検出片（伏字にするときのヒント）。"""

    ok: bool
    reason: str
    matches: tuple[str, ...] = ()


class Guard(Protocol):
    """入出力ガードの共通の口。text を確かめて GuardResult を返す（例外でなく判定で返す）。"""

    def check(self, text: str) -> GuardResult: ...


# email の素朴な形（ローカル部@ドメイン.TLD）。厳密な RFC 5322 は狙わない（スタブの範囲）。
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 電話番号：国内形式（0 始まり・ハイフン区切り。例 03-1234-5678・090-1234-5678）と
# 国際形式（+国番号。例 +81-90-1234-5678）。前後に数字が続くもの（桁の一部）は拾わない。
_PHONE = re.compile(r"(?<![\d+])(?:0\d{1,4}-\d{1,4}-\d{3,4}|\+\d{1,3}(?:[- ]\d{1,4}){2,4})(?!\d)")


class PiiRegexGuard:
    """入力の PII（email・電話番号）を正規表現で見つける**スタブ**（入力ガードの入口）。

    正規表現は取りこぼす（表記ゆれ・氏名・住所・番号の変則形は見ない）＝ここは入口だけで、
    実際の PII 検出は検出モデル（LLM/専用モデル）へ**委譲**する（DEC-0009 の作法＝委譲点を明示した骨組み。
    差し替えは Guard Protocol の別実装を足すだけ）。見つかれば ok=False＋matches（検出片）を返す。
    """

    def check(self, text: str) -> GuardResult:
        matches = tuple(m.group(0) for m in _EMAIL.finditer(text)) + tuple(m.group(0) for m in _PHONE.finditer(text))
        if matches:
            return GuardResult(
                ok=False,
                reason=f"PII らしき断片を {len(matches)} 件検出（email/電話の正規表現スタブ）",
                matches=matches,
            )
        return GuardResult(ok=True, reason="PII 検出なし（正規表現スタブの範囲）")


def _type_error(value: object, type_name: str, *, where: str) -> str | None:
    """JSON Schema の type 1 つ分の検査（違反の説明を返す・適合は None）。対応外の type 名は明示エラー。"""
    checks: dict[str, bool] = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        # JSON の number は int/float 両方（bool は int の派生だが number ではない＝除外）。
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if type_name not in checks:
        return f"{where}: type '{type_name}' は最小部分集合の対象外（完全検証は jsonschema へ委譲）"
    if not checks[type_name]:
        return f"{where}: type が '{type_name}' でない（実際: {type(value).__name__}）"
    return None


def validate_output_schema(output: str, schema: Mapping[str, Any]) -> GuardResult:
    """出力文字列を JSON として解釈し、JSON Schema の**最小部分集合**で検証する（出力ガード）。

    対応するのはトップレベルの `type`（object/array/string/number/boolean）・`required`（キーの存在）・
    `properties` の各キーの `type` だけ。ネストした schema・enum・format 等は見ない＝**完全検証は
    jsonschema へ委譲**する（jsonschema は base 依存に無い＝推移的のみ。必要になったら extra として足し、
    ここを呼び口のままに実装だけ差し替える）。`AgentSpec.output_schema`（Mapping | None）をそのまま渡せる。
    非 JSON・違反は ok=False で何が破れたかを reason に名指しする（黙って通さない）。
    """
    try:
        value = json.loads(output)
    except json.JSONDecodeError as exc:
        return GuardResult(ok=False, reason=f"JSON として読めない（{exc.msg}: line {exc.lineno} col {exc.colno}）")
    top = schema.get("type")
    if top is not None:
        error = _type_error(value, str(top), where="トップレベル")
        if error is not None:
            return GuardResult(ok=False, reason=error)
    required = schema.get("required")
    if isinstance(value, dict) and isinstance(required, list):
        missing = [str(k) for k in required if k not in value]
        if missing:
            return GuardResult(ok=False, reason=f"required のキーが無い: {', '.join(missing)}")
    properties = schema.get("properties")
    if isinstance(value, dict) and isinstance(properties, Mapping):
        for key, sub in properties.items():
            if key in value and isinstance(sub, Mapping) and "type" in sub:
                error = _type_error(value[key], str(sub["type"]), where=f"properties.{key}")
                if error is not None:
                    return GuardResult(ok=False, reason=error)
    return GuardResult(ok=True, reason="schema 適合（最小部分集合の範囲）")
