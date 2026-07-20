---
id: T-0235
kind: task
status: done
title: 思想の中核判断を複製で消えない正本へ移し、L-ID 根拠参照を撤去する（条件4の自己裏切り解消）
created: 2026-07-20
closed: 2026-07-20
depends_on: []
verified_by:
  - tests/test_doc_source_lint.py::test_durable_doc_referencing_learning_id_is_error
  - tests/test_doc_source_lint.py::test_learnings_md_itself_is_not_scanned
---
# T-0235 L-ID 根拠参照の撤去＋中核判断の正本化

AGENTS/method の条文が fork で白紙化される `docs/learnings.md` の L-ID（L-021 等）を根拠参照し、複製先で宙に浮いた。
恒久資産（AGENTS・docs・src・tests）の L-### 参照をすべて散文へ自足させて撤去（16 箇所）。doc_source_lint に
`L-###` パターンを追加（定義元 learnings.md は案件領域として走査対象外）。fail-closed 既定・0件判定を数える・
allowlist 優先・受け入れ基準は構成由来か検証可能な質問、を AGENTS 原則へ明文化（learnings 止まりだった中核判断を正本へ）。
