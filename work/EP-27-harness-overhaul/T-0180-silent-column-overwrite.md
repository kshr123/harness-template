---
id: T-0180
kind: task
status: todo
title: cluster・anomaly_score 列の黙った上書きを止める（データ破壊）
created: 2026-07-10
depends_on: []
verified_by: []
---
# T-0180 予約列名の衝突を黙って通さない

## 何が問題か（再現済み）
`src/harness/ds/unsupervised.py` は結果列を固定名で `with_columns` する。
- `cluster_summary`：`.with_columns(cluster=pl.Series("cluster", labels))`（208 行付近）
- `top_anomalies`：`.with_columns(anomaly_score=col)`（440 行付近）

入力の `df` に既に `cluster` 列（または `anomaly_score` 列）があると、**警告なく上書きされる**。
polars の `with_columns` は同名列を置き換える。呼び手のデータが壊れ、しかも結果は正常に見える。

現実的に起きる：顧客セグメントの正解ラベルが `cluster` という列名で入っているデータに
`cluster_summary` を当てると、正解が予測で潰れる。

## 直し方
結果列の名前を引数にし（`label_column: str = "cluster"`・`score_column: str = "anomaly_score"`）、
**入力に同名の列があれば `ValueError`**（fail closed。黙って上書きしない・黙って改名もしない）。
呼び手は名前を変えるか、入力から落とすかを選べる。

`ClusterReport.profile_by_cluster` の集計も同じ名前を使うので、引数の名前で通す。

## 受け入れ基準
- 入力に `cluster` 列がある `df` を `cluster_summary` に渡すと `ValueError`（列名を名指しする）。
- `label_column="segment_id"` を渡せば `segment_id` で出る。既定は `cluster` のまま（既存の呼び手を壊さない）。
- `top_anomalies` も同様（`anomaly_score`）。
- 期待値はテストで仕込んだ入力の構成から導く（実装出力の写経をしない）。
- `uv run verify` 全成功。
