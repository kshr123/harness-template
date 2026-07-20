---
id: T-0240
kind: task
status: done
title: 検査列の名前を「不変条件の検査 / INVARIANT_CHECKS」に一括改名する
created: 2026-07-20
closed: 2026-07-20
depends_on: []
verified_by:
  - tests/test_doc_sync.py::test_doc_sync_is_registered_in_invariant_checks
  - tests/test_profiles.py::test_load_profiles_wires_declared_profile
---
# T-0240 検査列の一括改名（PM_CHECKS → INVARIANT_CHECKS）

## なぜ
`checks.py` が束ねる検査列は12件あり、うち作業単位・課題の管理系は3件（`pm.lint`・`pm.spec_lint`・`issues`）だけ。
残り9件は文書↔コード整合（`doclint`・`coverage_lint`・`code_doc_lint`・`profile_doc_lint`・`doc_sync`）と
構造・ドリフト不変条件（`doc_source_lint`・`boundary_lint`・`conventions`・`retraction_lint`）。この集合を
「プロジェクト管理の検査 / PM_CHECKS」と呼ぶのは少数派3件で全体を名づける陳腐化で、「概念に2つ目の名前を作らない」
原則にも反する（`PM_CHECKS`・`pm_checks`・散文が同じ概念の別名になっていた）。共通するのは「リポジトリ自身の規則が
常に成り立つ」こと＝標準用語 invariant（不変条件）。言語ツール（ruff/mypy/pytest）との対比も明確になる。

## 何を
- **識別子**：`PM_CHECKS`→`INVARIANT_CHECKS`、`PmCheck`→`InvariantCheck`、`Profile.pm_checks`→`invariant_checks`、
  `_pm_checks`→`_run_invariant_checks`（checks.py）／`_invariant_checks`（doc_sync.py）。src・tests 全域。
- **散文**：「プロジェクト管理の検査」→「不変条件の検査」。初出（AGENTS・core.md・checks.py docstring）に
  「不変条件＝invariant＝常に成り立つべき性質」を1文で添える（意味の説明を初出で置く方針）。
- **生成物**：`docs/core.md` の見出し・表を `uv run doc-sync` で再生成（`INVARIANT_CHECKS` から導出）。
- `pm.py`＝作業単位モジュールの「プロジェクト管理」は本来の意味なので残す（改名の対象外）。

## 検証
`uv run verify` 全成功（不変条件の検査 17 件すべて通過＋ruff・mypy・pytest）。改名後の識別子を参照する配線テスト
（`test_doc_sync_is_registered_in_invariant_checks`＝`doc_sync.run_checks in checks.INVARIANT_CHECKS`、
`test_load_profiles_wires_declared_profile`＝`schema.data_lint in loaded[0].invariant_checks`）が緑＝旧名なら
import 不能／属性欠落で必ず落ちる。LIVE 資産に旧名の残骸ゼロ（grep で確認）。maker≠checker（別 fable）で差分確認。
