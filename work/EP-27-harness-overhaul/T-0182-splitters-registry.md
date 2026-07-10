---
id: T-0182
kind: task
status: todo
title: 分割器を SPLITTERS レジストリにし、fold 割当の正本を membership の長表にする
created: 2026-07-10
depends_on: []
verified_by: []
---
# T-0182 唯一、拡張口の無い軸を塞ぐ

## 何が問題か
`src/harness/ds/cv.py` の `make_folds` は、分割器を `stratify_by` / `group_by` の有無から if/elif で
選んでいる（KFold・StratifiedKFold・GroupKFold・StratifiedGroupKFold）。**config が kind 文字列で
選べる軸になっていない**。このリポジトリで変わりうる軸はすべて Registry ＋条件登録＋カタログ CLI で
表す規約なのに、分割器だけがそこから外れている。

時系列の分割（`TimeSeriesSplit`・purged/embargo）や `RepeatedStratifiedKFold` を足す口が無い。

## 2 つ目の問題：割当表の形が足りない
現在の正本は `(id_column, fold)` の 1 行 1 実体の表。これは**「各行はちょうど 1 つの fold の valid に入る」**
という前提を構造に焼き込んでいる。次の 3 つはこの形に載らない。

- **purged / embargo**：train から除外されるが、どの fold の valid にも入らない行がある。
- **repeated**：同じ行が複数回 valid になる（繰り返し回ごとに別の割当）。
- **時系列の expanding window**：fold ごとに train の範囲が違う（fold 番号だけでは train を復元できない）。

正本を `(fold, role, id)` の**長表**（membership）にする。`role` は `train` | `valid` |（将来）`purged`。
1 行 1 実体ではなく 1 行 1 所属になるので、上の 3 つがそのまま載る。現在の `(id, fold)` は
この長表からの生成ビュー（`role == "valid"` を pivot したもの）として残せる。

## 構造
- `SPLITTERS: Registry[Entry]`（`catalog="data splitters"`・`uv run data splitters`）。
  kind は sklearn のクラス名の写しなので `require_source` は不要（名前は既に外にある）。
  住人：`kfold` / `stratified` / `group` / `stratified_group` / `time_series`。
- `make_folds(df, *, kind, n_folds, seed, ...) -> pl.DataFrame`（長表を返す）。
- `run_cv` は長表を読む。`(id, fold)` を期待する既存の呼び手は生成ビュー経由。

## 順序（判定を混ぜない）
1. 長表への移行を、分割器の選び方を変えずに行う（挙動不変。既存テスト無変更で緑が証拠）。
2. `SPLITTERS` を導入し、if/elif を resolve に置き換える（挙動不変）。
3. `time_series` を足す（初めて挙動が増える）。

## 受け入れ基準
- `uv run data splitters` に全 kind が説明つきで載る。未知 kind は候補一覧つき ValueError。
- 同じ `(df, kind, seed)` なら必ず同じ長表（決定性）。`seed` は明示引数（グローバル種を使わない）。
- 期待値は入力の構成から導く：各 fold の valid の和集合が全 id と一致、valid どうしは互いに素、
  `group` では同じグループが train と valid に跨がらない。
- `uv run verify` 全成功。
