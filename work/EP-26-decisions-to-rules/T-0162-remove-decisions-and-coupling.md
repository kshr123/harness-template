---
id: T-0162
kind: task
status: todo
title: docs/decisions/ を削除し機械結合を外す（doclint・索引・凡例・template-copy）
created: 2026-07-07
depends_on: [T-0161]
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links, tests/test_doclint.py::test_decisions_dir_absent_is_ok]
---
# T-0162 decisions 削除と機械結合の除去
doclint から decisions/ 走査と DEC-XXXX 参照検査を外す（＋テスト）。README/docs/README の凡例・文書地図から
DEC・decisions を外す。template-copy の「残す：docs/decisions/」を外す。`git rm docs/decisions/`。verify 緑。
