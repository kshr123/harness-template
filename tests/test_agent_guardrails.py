"""guardrails（入力の PII 正規表現スタブ・出力の JSON Schema 最小検証）のテスト。

期待値はすべて構成した文字列・schema から導出する（実装の出力をコピーしない）。PII は「入れた email/電話が
matches に出る」・schema は「壊した箇所（required 欠け・型違い・非 JSON）が reason に名指しされる」を見る。
"""

from __future__ import annotations

import pytest

from harness.agent.guardrails import Guard, GuardResult, PiiRegexGuard, validate_output_schema

# ---- PiiRegexGuard（入力ガードのスタブ：email＋電話。実検出はモデルへ委譲＝ここは入口の形だけ） ----


@pytest.mark.unit
def test_pii_guard_detects_constructed_email_and_phone() -> None:
    guard = PiiRegexGuard()
    result = guard.check("連絡は taro@example.com か 090-1234-5678 へお願いします")
    assert result.ok is False
    assert "taro@example.com" in result.matches  # 入れた email がそのまま検出片に出る
    assert "090-1234-5678" in result.matches  # 入れた電話番号も同様
    assert len(result.matches) == 2


@pytest.mark.unit
def test_pii_guard_passes_clean_text() -> None:
    result = PiiRegexGuard().check("今日は 3 件の実験を回した。結果は results/ にある。")
    assert result.ok is True
    assert result.matches == ()


@pytest.mark.unit
def test_pii_guard_satisfies_guard_protocol() -> None:
    guard: Guard = PiiRegexGuard()  # Protocol の口（check(text) -> GuardResult）に適合する
    assert isinstance(guard.check("clean"), GuardResult)


# ---- validate_output_schema（最小部分集合：トップ type・required・properties の型。完全検証は jsonschema へ委譲） ----

SCHEMA = {
    "type": "object",
    "required": ["name", "age"],
    "properties": {"name": {"type": "string"}, "age": {"type": "number"}, "active": {"type": "boolean"}},
}


@pytest.mark.unit
def test_output_schema_valid_json_matching_schema_is_ok() -> None:
    result = validate_output_schema('{"name": "taro", "age": 30, "active": true}', SCHEMA)
    assert result.ok is True


@pytest.mark.unit
def test_output_schema_missing_required_key_fails_with_reason() -> None:
    result = validate_output_schema('{"name": "taro"}', SCHEMA)  # age を欠く
    assert result.ok is False
    assert "age" in result.reason  # 何が欠けたかを名指しする（黙って落とさない）


@pytest.mark.unit
def test_output_schema_wrong_property_type_fails_with_reason() -> None:
    result = validate_output_schema('{"name": "taro", "age": "thirty"}', SCHEMA)  # age が str
    assert result.ok is False
    assert "age" in result.reason
    # bool は int の派生だが JSON の number ではない（true を数として通さない）
    result = validate_output_schema('{"name": "taro", "age": true}', SCHEMA)
    assert result.ok is False
    assert "age" in result.reason


@pytest.mark.unit
def test_output_schema_top_level_type_mismatch_fails() -> None:
    result = validate_output_schema("[1, 2, 3]", SCHEMA)  # object を期待して array
    assert result.ok is False
    assert "object" in result.reason


@pytest.mark.unit
def test_output_schema_non_json_fails_with_reason() -> None:
    result = validate_output_schema("これは JSON ではない", SCHEMA)
    assert result.ok is False
    assert "JSON" in result.reason
