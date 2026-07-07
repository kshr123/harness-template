---
id: T-0161
kind: task
status: todo
title: method.md のメタ模型から「決定（DEC）」層と DEC 起票フローを外す（変更の記録は git）
created: 2026-07-07
depends_on: [T-0160]
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0161 method.md の作り直し
7 層の「決定（DEC）」層を外し、ルール化の流れから DEC 起票の段を外す（観察→learnings→即ルール化）。
「変更の記録は git」に改める。verify 緑。
