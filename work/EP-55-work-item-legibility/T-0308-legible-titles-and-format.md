---
id: T-0308
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
  - tests/test_pm.py::test_epic_title_required_when_not_done
  - tests/test_pm.py::test_epic_title_present_passes_and_done_and_tasks_are_grandfathered
title: 作業単位に平易な表示名を必須化し、本文の書き方の型を整える
---
# T-0308 作業単位に平易な表示名を必須化し、本文の書き方の型を整える

作業単位の表示名（title）と本文が専門用語で書かれていて、オーナー・コンサル（と WBS を見るクライアント）に
読めなかった。平易な表示名を機械で担保し、書き方の型・雛形・レビュー観点をそろえる。

## 受け入れ基準
- done でないエピックが平易な表示名（title）を持たなければ `uv run verify`（task-lint）が失敗する。
- done のエピック・タスク・実験は従来どおり通る（歴史の grandfather・タスクの title は推奨）。
- 書き方の型・雛形・レビュー観点が恒久資産（複製後も残る場所）に置かれている。

## 技術メモ（エージェント向け）
- 検査：`src/harness/pm.py` の `lint` に「done でない `kind=epic` は非空 `title` 必須」を追加（タスク・実験は
  対象外＝雛形と review スキルで担保。散文の平易さは機械化しない＝method §I）。
- 型・置き場：AGENTS「作業単位」に `title` 行＋「本文の書き方」（method §I へリンク）／`.harness/templates/epic.md`・
  `task.md` の雛形（既存 demand.md 等と同じ作法）＋ tasks スキルから参照／review スキルに作業単位の可読性の観点。
- 移行：既存 done の本文は書き直さない。仕掛かりだった EP-53 を done＋平易 title に整えた（1 件のみ）。
