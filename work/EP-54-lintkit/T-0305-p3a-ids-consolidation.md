---
id: T-0305
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
  - tests/test_doclint.py::test_missing_iss_reference_is_error
  - tests/test_doclint.py::test_req_reference_with_existing_home_and_missing_file_is_error
  - tests/test_lintkit.py::test_temp_unit_refs_collects_work_iss_learning_but_not_placeholders
---
# T-0305 P3a：doclint・doc_source_lint を lintkit.ids に載せ替え（重複解消・挙動不変）

P0 で `lintkit.ids` を作ったが、doc_source_lint と doclint が同じ文法をローカルに二重持ちしていた（レビュー N1＝
どちらも正しいが drift しうる）。両者を `lintkit.ids` に載せ替え、ローカルのコピーを削除した：

- doc_source_lint：`_WORK_REF_RE`/`_ISS_REF_RE`/`_LEARNING_REF_RE`/`_PLACEHOLDER_RE`・`_refs_in_line` を撤去し
  `ids.temp_unit_refs`／`ids.LEARNING_REF_RE` へ。未使用になった `import re` も削除。
- doclint：`_PLACEHOLDER_RE`/`_ID_HOMES`/`_ID_PREFIXES`/`_ID_REF_RE` を撤去し `ids.PLACEHOLDER_RE`／
  `ids.ID_HOMES`／`ids.ID_REF_RE` へ（path/command 系の `_PATH_RE`・`_CMD_RE`・`_ASCII_PATH_RE` は doclint 固有なので残す）。

パターンは byte 一致なので**旧テスト（test_doclint・test_doc_source_lint）を 1 行も変えず緑**＝挙動不変の証明。
ids.py が実運用で使われる状態になった（N1 解消）。core.md に「新しい検査は lintkit を使う」導線を追記（N3）。
