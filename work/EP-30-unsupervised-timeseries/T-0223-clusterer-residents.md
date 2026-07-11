---
id: T-0223
kind: task
status: todo
title: CLUSTERERS に住人を増やす（kmedoids・kmodes の条件登録・predict の体系差を包みで吸収）
created: 2026-07-11
depends_on: [T-0220]
verified_by: []
---
# T-0223 クラスタリングの住人

## 何が問題か
`CLUSTERERS` の住人は kmeans・gmm・hdbscan の 3 つだけ。中央値ベース（外れ値に頑健）とカテゴリ変数向けの
手法が無い。契約差（計画時の調査。**着手時に実測で確かめること**）：
`kmedoids.predict` は `labels_` と別の体系（medoid の行番号）を返すとされる。そのまま繋ぐと
クラスタ番号の意味が壊れる。

## やること
- kmedoids・kmodes を optional extra にし、条件登録で住人を足す。
- kmedoids は包みで `predict` の出力を `labels_` と同じ体系（0..k-1 のクラスタ番号）に揃える。
  **着手時にまず実測**し、体系差が実在しなければ包みを作らない（計画の主張を鵜呑みにしない＝L-020）。
- `inductive` の値は実測で決める（predict が新規行に使えるなら True）。

## やらないこと
- kprototypes 等の網羅（実需要が来た分だけ）。
- カテゴリ列の自動判別（どの列をカテゴリとして渡すかは呼び手の宣言）。

## 受け入れ基準
- 学習に使ったデータへの `predict` が `fit_predict` の結果と一致する（同一データなら同じ割当、は
  手法の定義から導ける。体系差が包まれずに残っていればここで落ちる）。
- 構成から導けるクラスタ構造（例：遠く離した 2 つの塊）で、同じ塊の行が同じクラスタ番号になる。
- 新住人が T-0220 の帰納性テストにテスト側の変更なしで合格する（inductive=True にした場合）。
- 未導入環境で import 成功・カタログに出ない（条件登録・extras_hint）。
- `uv run verify` 全成功。
