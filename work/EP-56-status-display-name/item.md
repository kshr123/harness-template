---
id: EP-56
kind: epic
status: done
plan: detailed
requirements: []
depends_on: []
title: 進捗一覧でも作業名が読めるように（表示名の導出を 1 か所に統一）
---
# EP-56 進捗一覧でも作業名が読めるように（表示名の導出を 1 か所に統一）

`uv run status` は表示名（title）の無いタスクを素の ID（`T-1234`）で出していた。ガント（WBS）は本文の見出しに
戻して読める名前を出すのに、進捗一覧は戻さず ID のまま＝同じ「表示名の決め方」が 2 か所で食い違っていた。
表示名の決め方を 1 か所にまとめ、進捗一覧でもガントでも同じ読める名前が出るようにする。

## 含む作業
- T-0309 表示名の導出（title→本文の見出し→ID）を 1 つの関数にまとめ、進捗一覧とガントの両方から使う。

## 技術メモ（エージェント向け）
- `pm.display_name(node)` を新設（title→`# <ID> 名前` の見出しから ID を除く→ID）。`uv run status` の描画
  （`pm` の render 群）と `deliver.wbs._display_name` の両方がこれを呼ぶ。誤った fallback を持っていた
  `Item.display`（title→ID）は撤去。fable レビュー（EP-55）で指摘された積み残し（N3）の解消。
