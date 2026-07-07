---
id: T-0160
kind: task
status: done
title: DEC 参照を現在のルール（一節の理由）に畳む・落とす（method.md 以外の docs/skills）
created: 2026-07-07
depends_on: []
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0160 DEC 参照を畳む

AGENTS・profile docs（ds/serve/agent/ops）・skills・learnings から `DEC-xxxx` 参照を除去し、必要な理由は
一節インラインに残した。method.md（模型の作り直しは T-0161）と `docs/decisions/` 自体（削除は T-0162）は据え置き。
スクリプト置換の残骸（DEC ファイル名の断片・崩れた括弧）は目視で修正。verify 緑（残る DEC 参照は method.md
のみで decisions/ に解決）。
