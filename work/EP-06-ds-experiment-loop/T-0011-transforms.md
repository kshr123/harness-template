---
id: T-0011
kind: task
status: done
title: ターゲット変換 transforms.py（Log1p/Identity/StandardScale＋Protocol）
requirements: [REQ-004]
depends_on: [T-0010]
verified_by:
  - tests/test_ds_transforms.py::test_log1p_roundtrip_on_nonnegative
  - tests/test_ds_transforms.py::test_standard_scale_uses_fitted_stats_not_input
  - tests/test_ds_transforms.py::test_all_transforms_satisfy_protocol
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0011 ターゲット変換 transforms.py

## 目的
学習の前後で target を往復変換する純粋な部品（numpy のみ）。参考リポ `domain/transforms.py` の移植。
学習系が予測を元スケールへ戻し忘れないよう、Protocol で型に載せる。

## 決定（汎用性のため）
- API 名は scikit-learn 慣習に合わせて `transform`／`inverse_transform`（当初案の `inverse` から変更・広く差し替え可能に）。
- Log1p の inverse は負値を 0 に切り上げる（非負ターゲットの下限）。ゆえに往復が厳密なのは y≥0 の範囲。
- 移植元は絶対パス `C:\Users\hj7745\Desktop\mlops\draft\reference\ml-competition-template-main`（MIT・README 記載）。

## 受け入れ基準（テスト先行で）
- `TargetTransform` Protocol（`transform(y)`／`inverse_transform(y)`）と実装：Identity・Log1p・StandardScale。
- 往復の性質テスト：`inverse(transform(y)) ≈ y`（hypothesis で生成入力に対し）。Log1p は非負域、StandardScale は fit した平均・分散で逆変換。
- numpy のみ・純粋（乱数なし）。mypy strict・ruff 通過。
- 出典ヘッダ（`ml-competition-template` / MIT）をファイル冒頭に付ける。
- `uv run verify` にすべて成功する。
