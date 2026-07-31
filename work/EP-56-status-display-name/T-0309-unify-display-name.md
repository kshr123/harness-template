---
id: T-0309
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
  - tests/test_pm.py::test_display_name_falls_back_title_then_heading_then_id
title: 表示名の導出を 1 か所にまとめる（進捗一覧とガントで共通に）
---
# T-0309 表示名の導出を 1 か所にまとめる（進捗一覧とガントで共通に）

進捗一覧（status）とガント（WBS）で「作業名の決め方」が別々だった。ガントは本文の見出しに戻して読める名前を
出すのに、進捗一覧は素の ID のままだった。決め方を 1 つにまとめ、どちらも同じ読める名前を出す。

## 受け入れ基準
- title 無しの作業単位でも、進捗一覧・ガントの両方で本文の見出し（`# <ID> 名前`）から作られた名前が出る。
- title があればそれ、title も見出しも無ければ素の ID（従来どおり）になる。

## 技術メモ（エージェント向け）
- `pm.display_name(node)`（title→`# <ID> 名前` の見出しから ID を除く→ID）を新設し、`_HEADING_ID` の抽出を
  `deliver.wbs` から `pm` へ移す（唯一の出所）。status の render 群と `wbs._display_name` が委譲する。
- 誤った fallback（title→素の ID）だった `Item.display` を撤去（未使用化・単一の導出に一本化）。
