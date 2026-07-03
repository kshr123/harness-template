---
id: T-0039
kind: task
status: done
title: 仕上げ＝marimo ビュー unsupervised.py＋e2e スモーク＋eda/features スキル導線
depends_on: [T-0038]
created: 2026-07-03
verified_by:
  - tests/test_e2e_unsupervised_notebook.py::test_unsupervised_notebook_runs_headless
---
# T-0039 仕上げ（T-d）

## 受け入れ基準（DESIGN §6）
- `notebooks/unsupervised.py`（marimo・薄いビュー）：`harness.ds.unsupervised` の同じ関数を呼んで
  2D 埋め込み（embed_2d・寄与率）／クラスタ（cluster_summary・sizes/silhouette/profile）／異常（anomaly_scores/rows）
  を図と表にするだけ。環境変数 `HARNESS_UNSUP_TABLE`／`_COLUMNS`／`_COLOR`。既定は数値列から id を除く（CLI と同じ）。
  抽出時は EmbedResult.sample_rows で色分け列を元 df と揃える。末尾 `app.run()` でヘッドレス実行。
- e2e スモーク `test_e2e_unsupervised_notebook.py`＝`python notebooks/unsupervised.py` を色分け有無・列指定で叩き
  例外なく通る（図の画素は比較しない・eda ビューと同型で腐り防止）。
- スキル導線：eda スキルに「目的変数なしで構造を掴む（cluster/embed/anomaly）」節・fit 済みの物を特徴にするなら
  encode 節へ、を追記。features スキルに「教師なしの量を特徴にする（cluster/anomaly_score・clone-per-fold で担保・
  t-SNE/HDBSCAN は載らない）」節を追記。**新スキルは作らない**（散文の二重化を避ける）。

## 結果
実装・verify 緑。EP-11 完了（(A)探索＋(B)特徴＋人のビューが揃う・追加依存ゼロ）。
