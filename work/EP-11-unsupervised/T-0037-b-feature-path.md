---
id: T-0037
kind: task
status: done
title: (B)特徴経路＝ENCODERS に cluster/anomaly_score を足す（薄い包み・fit-on-train は clone-per-fold）
depends_on: [T-0036]
created: 2026-07-03
verified_by:
  - tests/test_ds_unsupervised_encoders.py::test_cluster_distance_runs_through_cv
  - tests/test_ds_unsupervised_encoders.py::test_cluster_label_single_column
  - tests/test_ds_unsupervised_encoders.py::test_anomaly_score_runs_through_cv
  - tests/test_ds_unsupervised_encoders.py::test_cluster_and_anomaly_deterministic
  - tests/test_catalog.py::test_encoders_have_docstrings
---
# T-0037 (B)特徴経路（T-b）

## 受け入れ基準（DESIGN §4/§5/§9）
- ENCODERS に 2 行追加：
  - `"cluster"`＝`_cluster(seed, *, n_clusters, output="distance", **params)`。
    - `output="distance"`（既定）＝`Pipeline([impute(median), scale, KMeans])`。KMeans.transform で各中心への距離 n_clusters 列（素通し）。
    - `output="label"`＝KMeans を `ClusterLabel`（unsupervised.py の薄い包み）で後置。整数 1 列。
    - 未知 output は ValueError。
  - `"anomaly_score"`＝`_anomaly_score(seed, **params)`＝`Pipeline([impute(median), AnomalyScore(IsolationForest(seed))])`。
    「大きいほど異常」に符号反転した 1 列（木なので標準化不要）。
- 薄い包み（unsupervised.py・sklearn に無い隙間だけ・DEC-0008 の「作る」側）：
  - `ClusterLabel`：predict を transform として 1 列出す。get_feature_names_out=["cluster_label"]。
  - `AnomalyScore`：`-score_samples` を 1 列出す。get_feature_names_out=["anomaly_score"]。
- fit-on-train は run_cv の clone-per-fold で構造担保（新規コードに漏れ対策の分岐を書かない・既存 pca と同一経路）。
- 期待値は構成から導出：離れた 2 塊＋外れ行を仕込み、run_cv 完走・列名が get_feature_names_out で追える・同 seed で決定的。

## 結果
実装・verify 緑。(A) 拡張（iforest/lof・pca/tsne・k_scan 等）は T-0038、marimo は T-0039。
