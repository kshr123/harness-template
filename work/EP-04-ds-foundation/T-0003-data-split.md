---
id: T-0003
kind: task
status: done
title: 合成データの生成・固定分割・データ漏れ防止テスト
requirements: [REQ-002]
verified_by: [tests/test_ds_data.py]
owner: sakurada
---
# T-0003 合成データの生成・固定分割・データ漏れ防止

## 目的
外部ダウンロードに頼らず、決め打ちの種から再現できる合成データを作り、行ごとの安定した鍵で
学習・調整用と最終評価用に固定分割する。分割どうしに重複が無いことをテストで保証する（データ漏れの防止）。

## 受け入れ基準
- `generate_synthetic(seed)` が、同じ種なら必ず同じデータを返す（再現性）。
- `fixed_split(df)` が train/valid/test に分け、同じ入力なら必ず同じ分割になる。
- 3つの分割に同じ行（id）が重複しないことをテストが保証する。
- `uv run verify` にすべて成功する。
