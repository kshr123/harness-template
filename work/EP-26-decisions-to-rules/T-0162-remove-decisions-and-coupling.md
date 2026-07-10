---
id: T-0162
kind: task
status: done
title: docs/decisions/ を削除し機械結合を外す（doclint・索引・凡例・template-copy）
created: 2026-07-07
depends_on: [T-0161]
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0162 decisions 削除と機械結合の除去
doclint から decisions/ 走査と DEC-XXXX 参照検査を外す（＋テスト）。README/docs/README の凡例・文書地図から
DEC・decisions を外す。template-copy の「残す：docs/decisions/」を外す。`git rm docs/decisions/`。verify 緑。

## 後日の上書き（T-0165）
本タスクは「doclint は DEC-XXXX 参照を検査しない」を受け入れ基準にしたが、その後 T-0165 が
「置き場ディレクトリが存在しない接頭辞への参照はすべて error」という一般規則を入れたため、
DEC-XXXX 参照は再び error になる（撤去した仕組みへの参照が残り続けるのを止めるため）。
`verified_by` は、この上書き後も成立する `test_real_repo_docs_have_no_dead_links` だけを指す。
