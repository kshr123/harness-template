---
id: T-0036
kind: task
status: done
title: 教師なしの骨組み（unsupervised.py・kmeans・cluster_summary・data cluster）
depends_on: [EP-11]
created: 2026-07-03
verified_by:
  - tests/test_ds_unsupervised.py::test_kmeans_recovers_two_blobs
  - tests/test_ds_unsupervised.py::test_cluster_summary_to_dict_serializable
  - tests/test_catalog.py::test_clusterers_have_docstrings
---
# T-0036 教師なしの骨組み（T-a）

## 受け入れ基準
- 新モジュール `ds/unsupervised.py`：`CLUSTERERS`（kmeans・中央値埋め＋標準化前置＋seed）＋`cluster_summary`
  （ClusterReport＝labels/sizes/silhouette/profile_by_cluster・to_dict は数表だけ）。正本は構造化レポート。
- 入口：`uv run data cluster <表> --k N [--method]`（YAML）＋`uv run data unsupervised`（カタログ）＋test_catalog 検査。
- 期待値は構成から導出（離れた2塊を ARI=1.0 で当てる・高シルエット）。

## 結果
実装・verify 緑。(B) 特徴経路は T-0037・(A) 拡張は T-0038・marimo は T-0039。
