---
id: ISS-0003
kind: risk
state: resolved
found_in: 構造レビュー-2026-07
created: 2026-07-03
promoted_to: T-0068
title: 昇格済み learnings が指す DEC の実在を検査していない
---
# ISS-0003 昇格済み learnings が指す DEC の実在を検査していない

## 事象
DEC-0005（進化のラチェット）では、気づきを昇格したら `docs/learnings.md` の項目を「状態: 昇格済み → DEC-xxxx」に
更新する。しかしその `DEC-xxxx` が実在するか（`docs/decisions/` にあるか）を確かめる機械検査が無い。

## 根拠・影響
指す先の無い昇格（誤記・未作成）が黙って残ると、正本のたどり先が壊れる（下向き参照が切れる）。
`verified_by` の `::名` 実在検査（実装済み）と同じ発想で、`pm.lint` に「learnings の昇格先 DEC がファイルとして
実在するか」を足すと退行を止められる。対処すると決めたらタスク（T-…）へ昇格し、まず赤テストを書いてから実装する。
