---
id: T-0303
kind: task
status: done
created: 2026-07-31
closed: 2026-07-31
start: 2026-07-31
due: 2026-07-31
effort_days: 1
requirements: []
depends_on: []
verified_by:
  - tests/test_lintkit.py::test_exemptions_require_a_reason
  - tests/test_doc_source_lint.py::test_blank_exempt_reason_raises
  - tests/test_boundary_lint.py::test_blank_exempt_reason_raises
---
# T-0303 P1：免除表の検証を lintkit へ集約（挙動不変）

4 か所（doc_source_lint・code_doc_lint・coverage_lint・boundary_lint）に同型で重複していた `_validated_exempt`
の「理由必須・fail-closed」検査を `lintkit.exempt.validate_exemptions` に 1 度だけ実装し、各 `_validated_exempt` は
1 行の委譲にした。`_EXEMPT` は各モジュールで dict のまま（テストが monkeypatch で項目を差し込む＝旧テストを
1 行も変えない＝挙動不変の証明）。メッセージは既存の `理由が空…（{owner}）` を踏襲＝`match="理由が空"` が緑のまま。

ids／語境界の集約は P3（doclint＋doc_source＋code_doc を共有 Corpus/ids へ）でまとめて行う（ここでは触らない）。
