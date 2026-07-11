---
id: T-0193
kind: task
status: done
title: 複製を fork と規定し、本体領域と案件領域をファイルレベルで排他に定義する
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0189]
verified_by:
  - tests/test_template_copy.py::test_template_copy_defines_ownership_boundary
---
# T-0193 fork と所有境界

## 何を
`docs/template-copy.md` を書き直し、案件＝テンプレートの `git clone`（fork）と規定する。本体領域（upstream が
所有）と案件領域（案件が所有）を**ファイルレベルで排他**に定義し、`git merge upstream/main` が案件のファイルに
触れずに本体の改良だけを取り込めるようにする（競合源は `pyproject.toml`・`uv.lock` の 2 つだけと正直に規定）。

## なぜ
これが merge を機械化する前提。境界が排他でないと「差分監視」のような機構が要る。排他なら merge が
機械的になり、差分という概念が消える（L-017：機構を増やさずに済ませる）。派生元の版記録ファイルは作らない
（`git merge-base upstream/main HEAD` が発生源で真実を持つ＝写しは古びる）。

## 受け入れ基準
- template-copy.md が本体領域・案件領域を名指しで排他に定義し、fork/upstream 手順を持つ。
- `uv run verify` 全成功。
