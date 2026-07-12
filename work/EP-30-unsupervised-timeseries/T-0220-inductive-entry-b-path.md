---
id: T-0220
kind: task
status: done
title: 帰納性（inductive）を Entry の属性にし、(B) 特徴経路に method 軸を通す（直書きの除去）
created: 2026-07-11
depends_on: [T-0180, T-0219]
verified_by:
  - tests/test_inductive_contract.py::test_inductive_clusterer_predicts_new_rows
  - tests/test_inductive_contract.py::test_inductive_anomaly_scores_new_rows
  - tests/test_inductive_contract.py::test_b_cluster_rejects_non_inductive_method
  - tests/test_inductive_contract.py::test_b_anomaly_rejects_non_inductive_method
  - tests/test_inductive_contract.py::test_b_cluster_default_is_kmeans_and_transforms_new_rows
---
# T-0220 (B) 経路を既存の軸へ接続する

## 何が問題か（コードで確認済み 2026-07-11）
`src/harness/ds/pipeline.py` の `_cluster`（124 行付近）と `_anomaly_score`（148 行付近）は KMeans と
IsolationForest を**直接 import** しており、どの手法を使うかの軸（method）が無い。一方
`unsupervised.py` には `CLUSTERERS`／`ANOMALY`／`DIMRED` が既に在る（新設ではない）。
さらに、手法には「学習後に新しい行を変換・採点できるか（帰納的か）」の差がある：
hdbscan・sklearn の tsne・lof（novelty=False）は帰納的でない。この差を構造で持たないと、
(B) 経路（cross-validation で fold ごとに fit → 未知行を transform）に非帰納の手法を繋いだとき
実行時に黙って壊れる。

## やること
- `UnsupervisedEntry(Entry)` に `inductive: bool` を足す（`register(entry_cls=…, inductive=…)` の拡張点は
  `MetricEntry.higher_is_better` が先例。`registry.py` で確認済み）。既存住人へ付与する：
  kmeans／gmm／pca／iforest＝True、hdbscan／tsne／lof（novelty=False）＝False。
- `pipeline.py` の `_cluster`／`_anomaly_score` を、`method` 引数で `CLUSTERERS`／`ANOMALY` から工場を
  引く形に変える（KMeans／IsolationForest の直書きを除去）。`inductive=False` の kind を指定したら
  登録情報から導いて `ValueError`（実行時に黙って壊れない・fail closed）。
- レジストリ駆動の帰納性テスト：`inductive=True` の全 kind は fit 後に**学習に使っていない新規行**を
  変換／採点できることを実測で確かめる（宣言の真偽を挙動で検証する。対象集合は登録から機械的に導出
  ＝申告漏れも嘘の申告も、住人が増えた瞬間に自動で検査対象になる）。

## やらないこと
- 住人の追加（T-0221〜T-0223）。
- `SPLITTERS`（T-0182）・DIMRED の (B) 接続の新設（pca は既に ENCODERS に別途あり、重ねない）。
- 既定の変更：method 未指定の既定は kmeans／iforest のまま（既存 config を壊さない）。

## 受け入れ基準
- method 未指定の既存 config の挙動が変わらない（既存テスト無変更で全成功）。
- `method: hdbscan` を (B) の cluster エンコーダに指定すると kind を名指しした `ValueError`。
- `inductive=True` の全 kind が新規 3 行を変換・採点できる（テスト対象集合は `sorted(レジストリ)` から
  導出。kind 名のハードコード列挙が無い）。
- `uv run verify` 全成功。
