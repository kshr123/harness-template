---
id: ISS-0004
kind: question
state: open
found_in: 構造レビュー-2026-07
created: 2026-07-03
title: 最終評価（holdout）の位置づけが実験ループから切れている
---
# ISS-0004 最終評価（holdout）の位置づけが実験ループから切れている

## 事象
`data.fixed_split`（id ハッシュの安定分割で train/valid/test を作る）と `cv.holdout_indices` は用意してあるが、
E-0001 の実験ループ（`run_cv` の全行 OOF で合否）からは呼ばれていない。実験の採択と、最後に触っていない
test（holdout）での最終評価の関係が、雛形にも experiment スキルにも書かれていない。

## 根拠・影響
「OOF で選んで holdout で最終確認する」という段取りを決めないと、案件で最終評価をどこでやるかがぶれる。
fixed_split / holdout_indices が入口の無い部品（DEC-0009 の観点で孤立）になっている。
対処すると決めたら、experiment スキルに最終評価の段取りを足すか、雛形に holdout 評価の 1 段を加えるかを設計してから
（DESIGN で）決める。今は「実験ループは全行 CV・holdout は別段」という現状を明示するだけでもよい。
