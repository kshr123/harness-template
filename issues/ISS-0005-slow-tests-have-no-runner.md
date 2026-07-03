---
id: ISS-0005
kind: question
state: open
found_in: 構造レビュー-2026-07
created: 2026-07-03
title: slow マーカーのテストを走らせる先が決まっていない
---
# ISS-0005 slow マーカーのテストを走らせる先が決まっていない

## 事象
`slow` マーカーは登録済みだが、`checks.toml` は全段階（fast/standard/full）で `not slow` を指定するため、
`uv run check` / `uv run verify` のどの段階でも slow は走らない。結果、slow を付けたテストを実際に回す経路が無い
（現状 slow のテストは 0 件）。

## 根拠・影響
重い本規模テストを門番に載せない判断（DEC・method C）は正しいが、「ではどこで回すか」（手動 `-m slow`／別の
定期実行／リリース前ゲート）が未定。slow のテストを最初に足す時に決めればよい（今は該当 0 件なので実害なし）。
対処すると決めたら回す経路を 1 つ選び、pyproject の slow 説明とスキルに反映する。
