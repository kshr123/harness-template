---
id: EP-11
kind: epic
status: done
title: 次元圧縮と教師なし学習（テーブル向け・探索と特徴）
plan: detailed
requirements: [REQ-004]
created: 2026-07-03
---
# EP-11 次元圧縮・教師なし学習（探索(A)と特徴(B)）

## 目的
目的変数なしでデータの構造を掴む部品（次元圧縮の2D埋め込み・クラスタリング・異常検知）を、(A)探索（構造化レポート＋
marimo）と(B)特徴（下流モデルの入力・fit-on-train）の2用途で汎用的に用意する。深層学習は使わない（sklearn のみ）。

## 進め方（詳細設計は Fable＝DESIGN.md）
- **モデルは全部「使う」**（sklearn・自作ゼロ・DEC-0008）。追加依存ゼロ（UMAP/HDBSCAN 独立版は先送り）。
- **(A) は新モジュール `ds/unsupervised.py`**（DIMRED/CLUSTERERS/ANOMALY レジストリ＋レポート関数＋marimo）。正本は
  構造化レポート・図は marimo の中だけ。(A) は記述的で全データに当てる（結論を学習に戻さない）。
- **(B) は既存 ENCODERS に "cluster"/"anomaly_score" の2行**（fit-on-train は clone-per-fold で構造担保）。transform 不可の
  手法（t-SNE/HDBSCAN）は ENCODERS に登録しない＝(B) に載らないを構造で守る。

**着手順（歩く骨組み）**：
1. **T-0036（T-a）骨組み**：unsupervised.py（CLUSTERERS=kmeans・cluster_summary）＋CLI `data cluster`/`data unsupervised`＋2塊を ARI=1.0 で当てるテスト。
2. **T-0037（T-b）(B)経路**：ENCODERS "cluster"（distance/label）・"anomaly_score"＋ClusterLabel/AnomalyScore の薄い包み＋run_cv 完走・決定性・カタログ検査。
3. **T-0038（T-c）(A)拡張**：iforest/lof＋`data anomaly`／pca/tsne＋`data embed`／k_scan・gmm・hdbscan。
4. **T-0039（T-d）仕上げ**：marimo ビュー `notebooks/unsupervised.py`＋e2e スモーク／eda・features スキル導線。

## やらないこと（DESIGN §先送り）
UMAP・DBSCAN・Agglomerative・EllipticEnvelope・ICA/RandomProjection/KernelPCA/MDS/LLE・深層（AE/RBM/GAN）・
行単位成果物の --save 保存（漏れ経路防止）。必要になった案件で足す。
