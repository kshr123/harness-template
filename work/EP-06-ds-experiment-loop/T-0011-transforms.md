---
id: T-0011
kind: task
status: todo
title: ターゲット変換 transforms.py（Log1p/Identity/StandardScale＋Protocol）
requirements: [REQ-004]
depends_on: [T-0010]
created: 2026-07-03
owner: sakurada
---
# T-0011 ターゲット変換 transforms.py

## 目的
学習の前後で target を往復変換する純粋な部品（numpy のみ）。参考リポ `domain/transforms.py` の移植。
学習系が予測を元スケールへ戻し忘れないよう、Protocol で型に載せる。

## 受け入れ基準（テスト先行で）
- `TargetTransform` Protocol（`transform(y)`／`inverse(y)`）と実装：Identity・Log1p・StandardScale。
- 往復の性質テスト：`inverse(transform(y)) ≈ y`（hypothesis で生成入力に対し）。Log1p は非負域、StandardScale は fit した平均・分散で逆変換。
- numpy のみ・純粋（乱数なし）。mypy strict・ruff 通過。
- 出典ヘッダ（`ml-competition-template` / MIT）をファイル冒頭に付ける。
- `uv run verify` にすべて成功する。
