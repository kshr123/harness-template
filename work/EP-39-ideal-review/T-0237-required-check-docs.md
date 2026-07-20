---
id: T-0237
kind: task
status: done
title: branch protection / required check 化の手順を docs へ記載（宣言された唯一の不動点への到達路）
created: 2026-07-20
closed: 2026-07-20
depends_on: []
verified_by:
  - tests/test_ci_lint.py::test_required_check_procedure_is_documented_and_linked
---
# T-0237 required check 化の手順

AGENTS が「止まるのは作業ツリーの外だけ」と言う唯一の不動点（GitHub の branch protection）への手順が、
どの文書・雛形にも無かった（複製先は verify.yml をコピーしても required check 化しなければ CI 赤でもマージできる）。
docs/ops.md に「verify を required check にする」節（gh CLI 例・承認者≠作成者）を追加し、これは (c) 人の手順と明記。
verify.yml header と template-copy.md §1 から辿れるようリンク。CI 照会ジョブは観測事故まで作らない。
