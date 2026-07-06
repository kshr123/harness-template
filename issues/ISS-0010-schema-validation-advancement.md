---
id: ISS-0010
kind: question
state: resolved
found_in: ds-review-2026-07-05
created: 2026-07-05
promoted_to: T-0050
title: schema の checks フィールドが未評価。手書き validate を続けるか pandera へ導出するか
---
# ISS-0010 schema 検証の高度化（checks 未評価・pandera 導出の判断）

## 事象
`Column.checks` / `TableSchema.checks` は pydantic でパースされるが、コード上どこでも評価されていない
（grep 済み・現行のテーブル定義は未使用）。`checks: ["amount >= 0"]` と書いた人は「効いている」と誤解する。
EP-12 で `validate()` の 4 つの穴（Datetime 型・NaN・複合鍵・null 一意）は手書きのまま塞いだが、これらは
`pandera.polars` が既に扱うエッジケースそのもの。

## 根拠・影響
`schema.py` の docstring は「実行器は正本（YAML）から導出する差し替え物・より本格的なら pandera 等を組み立てる」と
既に枠を示している。DEC-0006（標準を再発明しない）の観点では、cross-column の `checks` を自前評価器で作り込むより
pandera 実行器を YAML から導出する方が筋。一方で依存を1つ増やす判断でもある（今は不要かもしれない）。

## 対処の方針（決めてから）
二択：(a) `checks` を polars 式として `validate()` で評価し実装する、(b) 実装するまで `data_lint` が非空 `checks` を
本 ISS 参照付きで弾き「未評価の黙認」を止める。cross-column が実際に要る案件が出たら pandera 導出へ切り替える判断
（DESIGN か DEC で記録）。YAML を正本に保つ前提は変えない。
