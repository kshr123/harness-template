---
id: T-0038
kind: task
status: done
title: (A)探索の横展開＝次元圧縮(pca/tsne)・異常検知(iforest/lof)・k_scan・gmm/hdbscan＋CLI
depends_on: [T-0037]
created: 2026-07-03
verified_by:
  - tests/test_ds_unsupervised_explore.py::test_k_scan_peaks_at_true_k
  - tests/test_ds_unsupervised_explore.py::test_gmm_recovers_two_blobs
  - tests/test_ds_unsupervised_explore.py::test_hdbscan_separates_blobs_and_marks_noise
  - tests/test_ds_unsupervised_explore.py::test_pca_embed_first_component_captures_variance
  - tests/test_ds_unsupervised_explore.py::test_tsne_embed_samples_when_over_max_rows
  - tests/test_ds_unsupervised_explore.py::test_iforest_ranks_planted_outliers_on_top
  - tests/test_ds_unsupervised_explore.py::test_lof_scores_have_direction
  - tests/test_catalog.py::test_dimred_and_anomaly_have_docstrings
  - tests/test_catalog.py::test_catalog_commands_run
  - tests/test_cli_unsupervised.py::test_cluster_cli_excludes_id_by_default
  - tests/test_cli_unsupervised.py::test_anomaly_cli_excludes_id_by_default
---
# T-0038 (A)探索の横展開（T-c）

## 受け入れ基準（DESIGN §3/§4/§5/§9）
- クラスタリング拡張：CLUSTERERS に `gmm`（GaussianMixture・n_components）／`hdbscan`（密度・k 不要・雑音 -1）。
  `k_scan(df, *, method, k_values, seed)`＝k・silhouette＋kmeans は inertia・gmm は bic（**門番にしない**）。
  `PARAM_FOR_K`（kmeans=n_clusters・gmm=n_components）で CLI の `--k` を橋渡し。
- 次元圧縮：DIMRED に `pca`（寄与率あり）／`tsne`（init="pca"・(A) 専用）。`embed_2d(...) -> EmbedResult`
  （coords＝dim1/dim2 の n 行・to_dict は寄与率/行数/抽出の有無の要約だけ・座標は marimo）。t-SNE は max_rows
  超で seed 決定的に等確率抽出し sampled=True（門番にしない）。
- 異常検知：ANOMALY に `iforest`（(A)(B)・標準化不要）／`lof`（(A) 専用・novelty=False）。
  `anomaly_scores(...) -> AnomalyReport`（scores＝大きいほど異常・分位 q50/q90/q99/max）。iforest は score_samples、
  lof は negative_outlier_factor_ から取り符号反転で向きを揃える。`anomaly_rows`＝df 全列＋anomaly_score の降順上位 n
  （analysis.worst_rows と同じ形）。
- CLI：`data unsupervised`（3 レジストリのカタログ）／`data embed`／`data cluster --k/--scan`／`data anomaly`。
- 期待値は構成から導出：3 塊で k_scan の silhouette 最大が k=3・仕込んだ外れ 5 行が anomaly_rows 上位・pca 第1成分>0.9。

## 結果
実装・verify 緑・独立レビュー合格。marimo ビュー＋スキル導線は T-0039。
