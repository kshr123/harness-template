---
id: T-0023
kind: task
status: done
title: 使い方スキルと「部品は入口まで」規約（experiment/features＋DoD/AGENTS/method＋DEC-0009）
requirements: [REQ-004]
depends_on: [T-0021, T-0022]
verified_by:
  - tests/test_catalog.py::test_blocks_have_docstrings
  - tests/test_catalog.py::test_encoders_have_docstrings
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0023 使い方スキルと「部品は入口まで」規約

## 目的
エージェントが部品を発見して使う入口（スキル）と、それを毎回作らせる規約を用意する。プロセス自体を
「部品→エージェントが使える入口」まで含む形に是正する。DEC-0009。

## 受け入れ基準
- `.claude/skills/experiment/SKILL.md`（実験の回し方＝雛形コピー＋config・部品は書かない）・`.claude/skills/features/SKILL.md`（一覧から選ぶ→無ければ DEC-0008 で作る/使う）を新設（frontmatter の発火語・手順・してはいけないこと・20行前後）。
- **規約**：DoD に「部品は入口まで作って完了（レジストリ＋docstring＋スキル/雛形の導線）」を追加。AGENTS 原則に1行（機械検査＝説明文必須は pytest・導線はレビュー観点）。method.md E 節に「部品と入口は 1 タスク」＋ ML スキルを experiment/features に差し替え。
- `DEC-0009` 起票・learnings に L-008（状態 昇格済み→DEC-0009）・harvest に「入口の無い部品が無いか」点検を追記。
- 機械的裏付け＝レジストリ項目に説明文必須（test_catalog）。導線はレビュー観点。`uv run verify` 全成功。
