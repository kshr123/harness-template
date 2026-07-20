---
id: T-0234
kind: task
status: done
title: プロファイル集合の導出点を1つにし、索引の陳腐化を検査する（stats 陳腐化クラスタの根治）
created: 2026-07-20
closed: 2026-07-20
depends_on: []
verified_by:
  - tests/test_profile_doc_lint.py::test_doc_exists_but_not_linked_in_index_is_error
  - tests/test_boundary_lint.py::test_core_import_of_nonexistent_profile_name_is_not_flagged
---
# T-0234 プロファイル集合の単一の出どころ＋索引被覆検査

stats はコード・boundary_lint・AGENTS に在るのに入口4文書（README・docs/README・core.md・template-copy）へ
言及 0 件で、実装が正しいのに索引が黙って古びていた。単一の出どころ `profiles.profile_names`（profile.py の走査）
を作り、boundary_lint がそれを消費（手書きの `_PROFILES` を撤去）。新 `profile_doc_lint` が「各プロファイルの
正本 docs/<名>.md が doc 索引から辿れるか」を verify で検査。doc_sync 前書きの列挙は削除（生成物の陳腐化源を断つ）。
template-copy の本体領域 docs は列挙でなく規則に。即時修正として stats を4文書へ追記。
